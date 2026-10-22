#!/usr/bin/env python3
"""Resumable Getter Japanese-to-Simplified-Chinese machine baseline.

Default: dry run, with no network or file writes. Use --write to translate to
a separate JSONL output, --probe N for a small preview, or --smoke for a small
synthetic service check. The original corpus is never modified. No API key or
account is used. This service has no availability or throughput guarantee.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import http.client
import json
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = 'google-public-dict-chrome-ex-ja-zh-CN/getter-v1'
BASE = 'https://translate.googleapis.com/translate_a/t'
CONTROL = re.compile(
    r'<[^<>]*>|\{[^{}]*\}|\[[^\[\]\r\n]*\]|'
    r'%%\d+|%%|%(?:\d+\$)?[-+#0 ]*\d*(?:\.\d+)?[hlL]?[diuoxXfFeEgGaAcspn]|'
    r'\$[A-Za-z0-9]+|\$/|%\d+(?![A-Za-z0-9])|@\d+|'
    r'\\(?:x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|[nrt0\\])|[\x00-\x1f\x7f]'
)
ASSET = re.compile(
    r'https?://[^\s<>]+|\b[A-Za-z0-9_./\\-]+\.(?:PAC|VFS|BIN|TIM|XA|STR|EXE|ISO|CUE)\b|'
    r'(?<![A-Za-z0-9_])(?:SLPS[-_ ]?\d+(?:[._-]\d+)?|[A-Z]{1,8}[-_]\d+[A-Z0-9_-]*)(?![A-Za-z0-9_])', re.I
)
READABLE = re.compile(r'[\u3040-\u30ff\u3400-\u9fffA-Za-z]')
JAPANESE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def atomic_text(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(value, encoding='utf-8')
    tmp.replace(path)


def load_records(path):
    path = Path(path)
    if path.suffix.lower() == '.jsonl':
        raw = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    else:
        raw = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(raw, dict):
            raw = raw.get('rows', raw.get('records'))
    if not isinstance(raw, list):
        raise ValueError('Input must be JSONL or a JSON array/rows/records list')
    seen = set()
    result = []
    for number, row in enumerate(raw, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Row {number} is not an object')
        uid = row.get('id', row.get('uid'))
        text = row.get('ja', row.get('text', row.get('jp')))
        if not isinstance(uid, (str, int)) or isinstance(uid, bool):
            raise ValueError(f'Row {number} has no string/integer id or uid')
        uid = str(uid)
        if uid in seen:
            raise ValueError(f'Duplicate input ID: {uid}')
        if not isinstance(text, str):
            raise ValueError(f'Row {uid} has no ja/text/jp string')
        if any(0xd800 <= ord(c) <= 0xdfff for c in text):
            raise ValueError(f'Row {uid} has undecoded surrogate characters')
        if row.get('source_language', 'ja') not in ('ja', 'en', 'auto'):
            raise ValueError(f'Unsupported source language: {uid}')
        seen.add(uid)
        result.append((uid, text, row))
    return result


def control_literals(row):
    """Extract only explicitly displayed strings, never offsets or raw bytes."""
    result = []
    for item in row.get('controls', []) or []:
        if isinstance(item, str) and item:
            result.append(item)
        elif isinstance(item, dict):
            for key in ('token', 'placeholder', 'display', 'text'):
                if isinstance(item.get(key), str) and item[key]:
                    result.append(item[key])
                    break
    for item in row.get('placeholders', []) or []:
        if isinstance(item, str) and item:
            result.append(item)
    return result


def control_pattern(row):
    # Extractor-specified tokens take priority over printf-like interpretations.
    # Getter "%0$s13" means two commands, not a positional printf "%0$s".
    exact = sorted(set(control_literals(row)), key=lambda value: (-len(value), value))
    return re.compile('|'.join(re.escape(value) for value in exact) +
                      ('|' if exact else '') + CONTROL.pattern)


class Tokenizer:
    MARKER = re.compile(r'ZXQGETTER[0-9]{4}QXZ')
    NONSEMANTIC = re.compile(r'\$[fsm][A-Za-z0-9]+|\$/|%%?\d+|@\d+|\\[nrt]|[\x00-\x1f\x7f]')
    SPEAKERS = {
        '早乙女': '早乙女', '竜馬': '龙马', '隼人': '隼人', '武蔵': '武藏',
        '弁慶': '弁庆', '竜二': '龙二', '達人': '达人', '信一': '信一',
        'ラセツ': '罗刹', 'ランドウ': '兰多', 'ランドウ兵': '兰多士兵',
        '魔王ゴール': '魔王高尔', 'ニオン': '尼昂', '橘': '橘',
        '楓': '枫', '茜': '茜', '椿': '椿', '號': '号', '翔': '翔',
        '研究員': '研究员', '艦長': '舰长', '艦内放送': '舰内广播',
        'テキサスクルー': '得克萨斯船员', 'ロシア司令官': '俄罗斯司令官',
        'ロシア兵Ａ': '俄罗斯士兵A', 'ロシア兵Ｂ': '俄罗斯士兵B',
        '百鬼兵': '百鬼士兵', '一本鬼': '一本鬼', '五本鬼': '五本鬼', '十方鬼': '十方鬼',
    }

    def __init__(self, glossary, canonical_entities=False, overrides=None):
        self.doc = glossary
        self.exact = dict(glossary['exact_field_map'])
        self.overrides = overrides or {}
        self.exact.update(self.overrides)
        self.canonical_entities = canonical_entities
        self.entities = {e['ja']: e for e in glossary['entries']
                         if e['category'] in ('character', 'unit', 'organization')}
        self.inline = {}
        self.pending_names = set()
        for ja, entry in self.entities.items():
            if canonical_entities and entry['auto_eligible']:
                self.inline[ja] = entry['zh_CN']
            else:
                self.inline[ja] = ja
                self.pending_names.add(ja)
        if canonical_entities:
            self.inline.update({'ゲッターロボ號': '盖塔机器人号', 'ゲッターロボ': '盖塔机器人',
                                'ゲッターチーム': '盖塔小队', 'ゲッター': '盖塔'})
            self.inline.update(self.SPEAKERS)
            # The disc map is complete-field by default. Only long, specific
            # named labels enter prose masking; generic short attack words do not.
            self.inline.update({k: v for k, v in self.overrides.items() if len(k) >= 6})
            self.inline['真ドリルハリケーン'] = '真·钻头飓风'
            self.inline.update({'神 隼人': '神隼人', '流 竜馬': '流龙马'})
        # Unconfirmed short speaker names must survive MT unchanged.
        self.pending_speakers = {'ミチル', '剴', 'メリー', 'ジャック', 'シャトナー',
                                 'ボブ', 'サム', 'リンダ', 'シュワルツ', 'ランバート', 'ギィムバグ'}
        for name in self.pending_speakers:
            self.inline.setdefault(name, name)
            self.pending_names.add(name)
        for token in glossary.get('protected_tokens', []):
            self.inline.setdefault(token, token)
        self.config = digest(json.dumps({
            'glossary': glossary, 'canonical_entities': canonical_entities,
            'overrides': self.overrides, 'inline': self.inline,
            'tokenization_version': 'getter-context-markers-sentence-boundaries-v5',
            'control_regex': CONTROL.pattern, 'nonsemantic_regex': self.NONSEMANTIC.pattern,
        }, ensure_ascii=False, sort_keys=True))

    def plan(self, text, row):
        if text in self.exact:
            return [('literal', self.exact[text])], [], []
        # Remove visual/timing controls before translation: Japanese hard wraps
        # may split a verb (e.g. もら\nう), so never MT each side independently.
        cp = control_pattern(row)
        visible, controls, at = '', [], 0
        for match in cp.finditer(text):
            visible += text[at:match.start()]
            token = match.group()
            if self.NONSEMANTIC.fullmatch(token):
                controls.append((len(visible), token))
            else:
                visible += token  # Variables remain semantic anchors, masked below.
            at = match.end()
        visible += text[at:]
        if not READABLE.search(visible):
            return [('literal', text)], [], []
        if visible in self.exact:
            context = {'visible': visible, 'controls': controls, 'markers': [],
                       'direct': self.exact[visible]}
            return [('context', context)], [], []
        names = dict(self.inline)
        for match in re.finditer(r'%2([^%]+)%0', text):
            name = match.group(1)
            if name in self.pending_speakers or name == '$n':
                names[name] = name
        choices = '|'.join(re.escape(value) for value in sorted(names, key=lambda value: (-len(value), value)))
        pattern = re.compile(cp.pattern + '|' + ASSET.pattern + ('|' + choices if choices else ''))
        markers, request, at, pending, applied = [], '', 0, set(), set()
        for match in pattern.finditer(visible):
            request += visible[at:match.start()]
            value = match.group()
            marker = f'ZXQGETTER{len(markers):04d}QXZ'
            target = names.get(value, value)
            markers.append({'token': marker, 'start': match.start(), 'end': match.end(),
                            'source': value, 'target': target})
            request += marker
            if value in self.pending_names:
                pending.add(value)
            elif value in names and target != value:
                applied.add(value)
            at = match.end()
        request += visible[at:]
        requests, current = [], ''
        for sentence in re.split(r'(?<=[。！？!?])', request):
            if current and len(current) + len(sentence) > 250:
                requests.append(current)
                current = ''
            current += sentence
        if current:
            requests.append(current)
        context = {'visible': visible, 'controls': controls, 'markers': markers,
                   'request': request, 'requests': requests}
        return [('context', context)], sorted(pending), sorted(applied)

    def restore(self, context, translated):
        translated = ''.join(c for c in translated if unicodedata.category(c) != 'Cf')
        if 'direct' in context:
            target = context['direct']
            marker_spans = []
        else:
            expected = [m['token'] for m in context['markers']]
            found = self.MARKER.findall(translated)
            if Counter(found) != Counter(expected):
                raise ValueError('Entity/variable marker count changed in translation')
            target, positions, at = '', {}, 0
            lookup = {m['token']: m for m in context['markers']}
            for match in self.MARKER.finditer(translated):
                marker = lookup[match.group()]
                target += translated[at:match.start()]
                begin = len(target)
                target += marker['target']
                positions[marker['token']] = (begin, len(target))
                at = match.end()
            target += translated[at:]
            marker_spans = [(m['start'], m['end'], *positions[m['token']]) for m in context['markers']]
        # CP932 originals have no Unicode format characters. Drop service-added
        # zero-width spaces/BOMs before measuring positions or building glyphs.
        target = ''.join(c for c in target if unicodedata.category(c) != 'Cf')
        # Match source/target named entities and dynamic variables as anchors.
        # Interpolate only nonsemantic formatting/timing controls between them.
        anchors = [(0, 0)]
        for a, b, c, d in marker_spans:
            # Japanese and Chinese can reorder named noun phrases. Their exact
            # names remain intact, while only monotonic anchors position styles.
            if c >= anchors[-1][1]:
                anchors.extend(((a, c), (b, d)))
        anchors.append((len(context['visible']), len(target)))
        def mapped(pos):
            if pos <= 0:
                return 0
            if pos >= len(context['visible']):
                return len(target)
            for index in range(1, len(anchors)):
                a, c = anchors[index-1]
                b, d = anchors[index]
                if a <= pos <= b:
                    return c if b == a else round(c + (pos-a)*(d-c)/(b-a))
            raise ValueError('Unmapped formatting control position')
        inserts = [(mapped(pos), token) for pos, token in context['controls']]
        if any(inserts[i][0] > inserts[i+1][0] for i in range(len(inserts)-1)):
            raise ValueError('Formatting control placement became nonmonotonic')
        out, at = '', 0
        for pos, token in inserts:
            out += target[at:pos] + token
            at = pos
        return out + target[at:]


class Cache:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS segments '
                        '(key TEXT PRIMARY KEY, lang TEXT, source TEXT, target TEXT, engine TEXT, created REAL)')
        self.db.commit()

    def key(self, lang, text):
        return digest(ENGINE + '\0' + lang + '\0' + text)

    def get(self, lang, text):
        with self.lock:
            row = self.db.execute('SELECT target FROM segments WHERE key=?', (self.key(lang, text),)).fetchone()
        return row[0] if row else None

    def put(self, lang, sources, targets):
        with self.lock:
            self.db.executemany('INSERT OR REPLACE INTO segments VALUES (?,?,?,?,?,?)', [
                (self.key(lang, source), lang, source, target, ENGINE, time.time())
                for source, target in zip(sources, targets)
            ])
            self.db.commit()

    def close(self):
        self.db.close()


class Translator:
    def __init__(self, cache, interval, retries, timeout):
        self.cache, self.interval, self.retries, self.timeout = cache, interval, retries, timeout
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.next_request, self.requests, self.splits = 0., 0, 0

    def request(self, lang, texts):
        payload = urllib.parse.urlencode([('client', 'dict-chrome-ex'), ('sl', lang), ('tl', 'zh-CN')]
                                         + [('q', value) for value in texts])
        for attempt in range(self.retries + 1):
            if self.stop.is_set():
                raise RuntimeError('Service rate-limit breaker open; resume later from cache')
            with self.lock:
                now = time.monotonic()
                delay = max(0., self.next_request - now)
                self.next_request = max(now, self.next_request) + self.interval
                self.requests += 1
            if delay:
                time.sleep(delay)
            try:
                req = urllib.request.Request(BASE + '?' + payload, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    try:
                        raw = response.read()
                    except http.client.IncompleteRead as error:
                        raw = error.partial
                data = json.loads(raw)
                if not isinstance(data, list) or len(data) != len(texts):
                    raise ValueError('Translation response count mismatch')
                targets = [item if isinstance(item, str) else item[0]
                           if isinstance(item, list) and item and isinstance(item[0], str) else None
                           for item in data]
                if any(not isinstance(target, str) or (source.strip() and not target.strip())
                       for source, target in zip(texts, targets)):
                    raise ValueError('Invalid or empty translation response')
                if any(CONTROL.search(target) for target in targets):
                    raise ValueError('Service invented a control/placeholder; rejecting output')
                return targets
            except urllib.error.HTTPError as error:
                if error.code in (400, 413, 414):
                    raise ValueError(f'Service rejected batch size (HTTP {error.code})') from error
                if error.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    if error.code == 429:
                        self.stop.set()
                    raise
                retry_after = error.headers.get('Retry-After', '')
                delay = min(30., float(retry_after)) if retry_after.isdigit() else min(30., 5 * 2**attempt)
            except (urllib.error.URLError, http.client.HTTPException, json.JSONDecodeError,
                    UnicodeDecodeError, TimeoutError, ConnectionError):
                if attempt == self.retries:
                    raise
                delay = min(30., 2**attempt)
            with self.lock:
                self.next_request = max(self.next_request, time.monotonic() + delay)
            time.sleep(delay)
        raise RuntimeError('Translation retries exhausted')

    def batch(self, lang, texts):
        try:
            targets = self.request(lang, texts)
            self.cache.put(lang, texts, targets)
            return len(texts)
        except ValueError:
            if len(texts) == 1:
                raise
            with self.lock:
                self.splits += 1
            middle = len(texts) // 2
            return self.batch(lang, texts[:middle]) + self.batch(lang, texts[middle:])


def jobs_for(segments, max_items, max_chars):
    by_lang = {}
    for lang, text in segments:
        by_lang.setdefault(lang, []).append(text)
    jobs = []
    for lang, texts in by_lang.items():
        batch, size = [], 0
        for text in texts:
            encoded_size = len(urllib.parse.urlencode([('q', value) for value in batch + [text]]))
            if batch and (len(batch) >= max_items or size + len(text) > max_chars or encoded_size > 14000):
                jobs.append((lang, batch))
                batch, size = [], 0
            batch.append(text)
            size += len(text)
        if batch:
            jobs.append((lang, batch))
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'work/translation/zh_CN.machine.jsonl')
    parser.add_argument('--glossary', type=Path, default=ROOT/'work/glossary/canonical_zh.json')
    parser.add_argument('--overrides', type=Path, default=ROOT/'work/glossary/disc_exact_overrides.zh_CN.json')
    parser.add_argument('--review-overrides', type=Path, default=ROOT/'work/glossary/prose_review_overrides.zh_CN.json')
    parser.add_argument('--cache', type=Path, default=ROOT/'work/translation/mt_cache.sqlite')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--probe', type=int, default=0)
    parser.add_argument('--preview-file', type=Path)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--canonical-entities', action='store_true',
                        help='Explicitly allow verified glossary names within prose; provisional names stay original')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--batch-items', type=int, default=80)
    parser.add_argument('--batch-chars', type=int, default=3000)
    parser.add_argument('--request-interval', type=float, default=.67)
    parser.add_argument('--retries', type=int, default=4)
    parser.add_argument('--timeout', type=float, default=35.)
    args = parser.parse_args()
    if sum((args.write, bool(args.probe), args.smoke)) > 1:
        parser.error('Choose only one of --write, --probe N, --smoke')
    if not 1 <= args.workers <= 4 or args.batch_items < 1 or args.batch_chars < 1:
        parser.error('workers must be 1–4 and batch limits must be positive')
    if args.request_interval < .1 or args.retries < 0 or args.probe < 0 or (args.limit is not None and args.limit < 0):
        parser.error('Invalid request/retry/probe limits')
    protected_paths = {args.glossary.resolve()}
    if args.input:
        protected_paths.add(args.input.resolve())
    if args.output.resolve() in protected_paths or args.cache.resolve() in protected_paths:
        parser.error('Output/cache must not replace input or glossary')
    if args.preview_file and args.preview_file.resolve() in protected_paths:
        parser.error('Preview must not replace input or glossary')
    if args.cache.resolve() == args.output.resolve():
        parser.error('Output and SQLite cache must have separate paths')
    if args.smoke:
        records = [('synthetic-smoke-1', '流竜馬、出撃する！<WAIT>{HP}を確認。',
                    {'id': 'synthetic-smoke-1', 'ja': '流竜馬、出撃する！<WAIT>{HP}を確認。',
                     'source': 'synthetic service check; not game script', 'controls': ['<WAIT>', '{HP}']})]
    else:
        if not args.input:
            parser.error('--input is required except with --smoke')
        if args.input.resolve() == args.output.resolve():
            parser.error('Output must be separate from original corpus')
        records = load_records(args.input)
    if args.limit is not None:
        records = records[:args.limit]
    if args.probe:
        records = records[:args.probe]
    overrides = json.loads(args.overrides.read_text(encoding='utf-8')) if args.overrides.exists() else {}
    if args.review_overrides.exists():
        overrides.update(json.loads(args.review_overrides.read_text(encoding='utf-8')))
    if not isinstance(overrides, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in overrides.items()):
        parser.error('Overrides must be a flat string-to-string map')
    tokenizer = Tokenizer(json.loads(args.glossary.read_text(encoding='utf-8')), args.canonical_entities, overrides)
    plans, segments = [], {}
    for uid, text, row in records:
        pieces, pending, applied = tokenizer.plan(text, row)
        lang = row.get('source_language', 'ja')
        plans.append((uid, text, row, lang, pieces, pending, applied))
        for kind, value in pieces:
            if kind == 'mt':
                segments[(lang, value)] = None
            elif kind == 'context' and 'request' in value:
                for request in value['requests']:
                    segments[(lang, request)] = None
    summary = {'engine': ENGINE, 'status': 'dry_run', 'input_rows': len(records),
               'source_characters': sum(len(text) for _, text, _ in records),
               'unique_mt_segments': len(segments),
               'rows_with_protected_names': sum(bool(plan[5]) for plan in plans),
               'canonical_entities_in_prose': args.canonical_entities,
               'output': str(args.output), 'glossary_sha256': tokenizer.config}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not (args.write or args.probe or args.smoke):
        return

    cache = Cache(args.cache)
    try:
        missing = [key for key in segments if cache.get(*key) is None]
        jobs = jobs_for(missing, args.batch_items, args.batch_chars)
        translator = Translator(cache, args.request_interval, args.retries, args.timeout)
        errors, done, started = [], 0, time.monotonic()
        with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            tasks = {pool.submit(translator.batch, lang, texts): (lang, texts) for lang, texts in jobs}
            for task in futures.as_completed(tasks):
                try:
                    done += task.result()
                except Exception as error:
                    lang, texts = tasks[task]
                    errors.append({'language': lang, 'source_hashes': [digest(text) for text in texts],
                                   'error': type(error).__name__ + ': ' + str(error)})
                print(json.dumps({'new_segments': done, 'http_requests': translator.requests,
                                  'failed_batches': len(errors), 'seconds': round(time.monotonic()-started, 1)}), flush=True)

        existing = {}
        if args.write and args.output.exists():
            for uid, _, old in load_records(args.output):
                existing[uid] = old
        output, incomplete = [], []
        for uid, text, row, lang, pieces, pending, applied in plans:
            source_hash = digest(text)
            old = existing.get(uid)
            if old and old.get('mt', {}).get('source_sha256') == source_hash and old.get('mt', {}).get('config_sha256') == tokenizer.config:
                if not isinstance(old.get('zh_CN'), str) or not old.get('mt', {}).get('controls_verified'):
                    raise ValueError(f'Existing output lacks verified translation for {uid}')
                output.append({**row, 'zh_CN': old['zh_CN'], 'mt': old['mt']})
                continue
            if old:
                raise ValueError(f'Existing output differs from source/config for {uid}; choose a new --output')
            try:
                target_parts = []
                for kind, value in pieces:
                    if kind == 'literal':
                        target_parts.append(value)
                    elif kind == 'context':
                        if 'direct' in value:
                            translated = value['direct']
                        else:
                            translations = [cache.get(lang, request) for request in value['requests']]
                            translated = ''.join(translations) if all(v is not None for v in translations) else None
                        target_parts.append(tokenizer.restore(value, translated) if translated is not None else None)
                    else:
                        target_parts.append(cache.get(lang, value))
            except ValueError as error:
                incomplete.append({'id': uid, 'reason': str(error)})
                continue
            if any(value is None for value in target_parts):
                incomplete.append({'id': uid, 'reason': 'translation segments missing; resume from cache'})
                continue
            target = ''.join(target_parts)
            controls = control_pattern(row)
            if controls.findall(target) != controls.findall(text):
                incomplete.append({'id': uid, 'reason': 'control/placeholder stream mismatch'})
                continue
            explicit = control_literals(row)
            if any(target.count(value) != text.count(value) for value in explicit):
                incomplete.append({'id': uid, 'reason': 'explicit control/placeholder count mismatch'})
                continue
            if any(token in text and target.count(token) != text.count(token)
                   for token in tokenizer.doc.get('protected_tokens', [])):
                incomplete.append({'id': uid, 'reason': 'protected technical token count mismatch'})
                continue
            output.append({**row, 'zh_CN': target, 'mt': {
                'status': 'machine_unreviewed', 'engine': ENGINE, 'source_language': lang,
                'source_sha256': source_hash, 'config_sha256': tokenizer.config,
                'controls_verified': True, 'pending_entity_review': pending,
                'applied_canonical_entities': applied,
                'control_placement': 'nonsemantic_controls_interpolated_between_semantic_anchors',
            }})
        # Keep existing rows outside --limit/probe selection; original metadata survives.
        if args.write:
            selected = {uid for uid, _, _ in records}
            output.extend(old for uid, old in existing.items() if uid not in selected)
            atomic_text(args.output, ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in output))
        summary.update({'status': 'complete_machine_unreviewed' if not incomplete else 'incomplete',
                        'completed_rows': len(output), 'incomplete_rows': incomplete,
                        'cached_segments_before_run': len(segments)-len(missing), 'new_segments': done,
                        'http_requests': translator.requests, 'split_batches': translator.splits,
                        'request_errors': errors, 'seconds': round(time.monotonic()-started, 2)})
        preview = {'summary': summary, 'rows': output}
        if args.preview_file:
            if args.input and args.preview_file.resolve() == args.input.resolve():
                raise ValueError('Preview cannot replace original corpus')
            atomic_text(args.preview_file, json.dumps(preview, ensure_ascii=False, indent=2) + '\n')
        if args.write:
            atomic_text(args.output.with_suffix(args.output.suffix+'.manifest.json'),
                        json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(preview if args.smoke or args.probe else summary, ensure_ascii=False, indent=2), flush=True)
        if incomplete:
            raise SystemExit(2)
    finally:
        cache.close()


if __name__ == '__main__':
    main()

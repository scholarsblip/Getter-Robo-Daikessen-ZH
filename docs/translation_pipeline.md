# Getter machine-translation pipeline

The current audited output is **v3**; see [mt_v3_audit.md](mt_v3_audit.md) for the full-prose marker method, exact disc-label overrides, targeted manual repairs and remaining limits. Earlier v2 fragmented-name/softwrap results are superseded. The original prototype details below describe the service and resume interface; the current tokenizer joins soft wraps, masks entities within complete prose, and restores nonsemantic controls between semantic anchors.

`tools/translate_corpus.py` prepares a resumable Japanese → Simplified Chinese machine baseline. It uses the same credential-free Google public `dict-chrome-ex` translation endpoint already available in the local STT helper, independently of that game's data. No key, login or stored credential is required. The public endpoint may throttle or become unavailable.

## Input and output

Input is JSONL with one record per extracted text field, for example `{ "id": "member:offset", "ja": "…", "source": "…", "controls": [] }`. The corpus agent's `source`, container/member identifiers, offset, raw hex, encoding, controls and references are copied intact. `uid` and `text`/`jp` are also accepted. Duplicate IDs and undecoded surrogate characters are rejected.

The separate output retains every input field and adds `zh_CN` and `mt` (machine status, engine, source/config hashes, control verification and pending entity review). It is **machine_unreviewed**. This file is neither a patch nor proof that translated text fits the game's font, pointers, memory buffers or battle UI.

## Commands

Run from the repository root, using an available Python 3 interpreter. Default is a dry run with no network requests or file writes:

```sh
python3 tools/translate_corpus.py --input work/source/scenario_corpus.jsonl
```

Translate a five-row preview to a separate file:

```sh
python3 tools/translate_corpus.py --input work/source/scenario_corpus.jsonl --probe 5 --canonical-entities --preview-file work/translation/preview.json
```

After extraction is verified, translate to the separate machine output:

```sh
python3 tools/translate_corpus.py --input work/source/scenario_corpus.jsonl --write --canonical-entities
```

Rerun the same command to resume from `work/translation/mt_cache.sqlite`; completed segments are committed per successful batch. Existing output rows with matching source/config hashes retain their translations. If an existing row's source or glossary configuration changed, choose a fresh `--output` path. Failed segments remain absent and are listed in the manifest, so a later run can retry them. Output writes are atomic.

## Protection and terminology

Complete fields matching `exact_field_map` receive the researched Chinese name. In prose, names are protected from machine translation by default. Explicit `--canonical-entities` enables known, non-provisional **character/unit/organization** entries in prose; longest names are matched first. This is a deliberate opt-in because the glossary normally permits complete-field matching. Provisional names remain in the source spelling and are listed under `pending_entity_review` for human resolution. Unverified weapon spellings are not automatically applied.

The service only receives ordinary prose segments. `<…>`, `{…}`, `[…]`, printf placeholders, escaped newlines/hex, actual newlines/tabs/control characters, asset names and protected technical IDs remain local. String values in `controls`, or object `token`/`placeholder`/`display`/`text` values, are also protected. For a different control representation, extend `control_literals()` before running. The final generic control stream, explicit control counts and protected-token counts must match the original, or the row is excluded and reported.

Public requests are batched, with three workers and a global minimum interval of 0.67 seconds. Requests retry transient network/HTTP errors, reduce rejected batches, and open a stop breaker if rate limiting persists. Single long prose segments split at punctuation to fit request limits. These operations prioritize a quick first pass; splitting around placeholders and names can reduce fluency, so review remains required.

## Checks performed

On 2026-10-22 a synthetic Japanese sentence, not extracted game script, translated successfully in **2.42 seconds**, using one HTTP batch for two prose segments. “流竜馬” became “流龙马”; `<WAIT>` and `{HP}` were unchanged. Repeating it reused two cached segments with **zero HTTP requests**. This small latency check is not a whole-game completion estimate.

Local checks passed for exact labels, protected names/controls/technical IDs, longest-name matching, provisional exclusion, long-segment splitting, persistent SQLite reuse and duplicate rejection. No real game corpus was translated during pipeline preparation.

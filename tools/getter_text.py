#!/usr/bin/env python3
"""Extract bounded, NUL-terminated CP932 text candidates from Getter resources."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

RUN = re.compile(rb"(?:(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])|[\x09\x0a\x0d\x20-\x7e\xa1-\xdf]){3,}")
CONTROL = re.compile(r"\$[A-Za-z0-9]+|\$/|%%[0-9A-Za-z]|%[0-9A-Za-z]|@[0-9A-Za-z]{2}|\\[nrt]|\\x[0-9A-Fa-f]{2}")


def extract_strings(data, source, source_kind="overlay"):
    result = []
    for match in RUN.finditer(data):
        start, end = match.span()
        # A complete C string ends in NUL; binary fragments are not insertable.
        if end >= len(data) or data[end] != 0:
            continue
        raw = match.group()
        try:
            text = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        japanese = sum(0x3040 <= ord(c) <= 0x30FF or 0x3400 <= ord(c) <= 0x9FFF for c in text)
        if japanese < 2 or len(text) > 10000:
            continue
        if start and data[start - 1] != 0 and start % 4:
            continue
        controls = list(dict.fromkeys(CONTROL.findall(text)))
        if japanese / max(1, len(text)) < 0.35 and not controls:
            continue
        result.append({"id": f"{source}:{start:06X}", "ja": text,
                       "source": source, "source_kind": source_kind,
                       "offset": start, "end": end + 1, "raw_hex": raw.hex(),
                       "encoding": "cp932", "controls": controls,
                       "references": [], "original_byte_budget": len(raw),
                       "source_sha256": hashlib.sha256(data).hexdigest(),
                       "extraction_confidence": "complete_cp932_cstring_candidate"})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-exe", action="store_true")
    args = parser.parse_args()
    entries = []
    candidates = sorted(args.source.rglob("*.bin"))
    if args.include_exe:
        candidates += sorted(args.source.rglob("*.exe"))
    for source in candidates:
        entries += extract_strings(source.read_bytes(), str(source.relative_to(args.source)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in entries))
    print(json.dumps({"entries": len(entries), "unique_texts": len({x['ja'] for x in entries}),
                      "japanese_chars": sum(len(x['ja']) for x in entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Extract verified bounded EXE/overlay CP932 fields without changing sources.

Offsets are file offsets. Named fixed arrays and manually inspected data
regions are specific to Japanese SLPS-02232. Scan candidates outside these
regions are deliberately kept separate from the insertable corpus.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
BASES = {"battle.bin": 0x800A97A8, "briefing.bin": 0x800A97A8,
         "debug.bin": 0x8008B7A8, "game.bin": 0x8008B7A8,
         "title.bin": 0x8008B7A8, "flight.bin": 0x800C67A8}
REGIONS = {"battle.bin": [(0, 0x13D0)], "briefing.bin": [(0, 0x2550)],
           "debug.bin": [(0, 0x1EC0)], "game.bin": [(0, 0xCC8), (0x183C, 0x1F50)],
           "title.bin": [(0, 0xA44)], "flight.bin": [(0x21FB0, 0x223AC)],
           "map04.bin": [(0, 0xB8)], "map10.bin": [(0, 0xFC)],
           "map16.bin": [(0, 0xB0)], "map18.bin": [(0, 0x22C)]}
RUN = re.compile(rb"(?:(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])|[\x09\x0a\x0d\x20-\x7e\xa1-\xdf])+")
CONTROL = re.compile(r"%%[0-9A-Za-z]|%(?:[-+#0 ]*(?:\d+|\*)?(?:\.\d+)?(?:hh|ll|[hlLjzt])?[diuoxXfFeEgGaAcspn%])|\$[A-Za-z0-9]+|\$/|%[0-9A-Za-z]|@[0-9A-Za-z]{2}|\\[nrt]|[\n\r\t]")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def text_value(raw):
    try:
        text = raw.decode("cp932")
    except UnicodeDecodeError:
        return None
    if not text or len(text) > 4000:
        return None
    if any(not (c in "\t\n\r" or 0x20 <= ord(c) <= 0x7E or
                    ord(c) in (0xB0, 0xB1, 0xD7, 0xF7) or 0x2000 <= ord(c) <= 0x30FF or 0x3400 <= ord(c) <= 0x9FFF or
                    0xFF01 <= ord(c) <= 0xFF60) for c in text):
        return None
    japanese = sum(0x3040 <= ord(c) <= 0x30FF or 0x3400 <= ord(c) <= 0x9FFF for c in text)
    if not japanese or (japanese / len(text) < 0.25 and not CONTROL.search(text)):
        return None
    if text.encode("cp932") != raw:
        return None
    return text


def pointer_references(data, source):
    """Static aligned u32 and nearby LUI+ADDIU/ORI address constructions.

    These are evidence of references, not an exhaustive relocation table.
    No control-flow or runtime-pointer completeness claim is made.
    """
    words = struct.unpack_from(f"<{len(data)//4}I", data)
    found = defaultdict(list)
    for i, word in enumerate(words):
        if 0x80010000 <= word < 0x80200000:
            found[word].append({"source": source, "offset": i * 4, "kind": "u32_le"})
        if word >> 26 != 15:
            continue
        register, high = word >> 16 & 31, (word & 0xFFFF) << 16
        for j in range(i + 1, min(i + 7, len(words))):
            lowword = words[j]
            opcode, src, dst = lowword >> 26, lowword >> 21 & 31, lowword >> 16 & 31
            if opcode in (9, 13) and src == register:
                low = lowword & 0xFFFF
                address = (high + (low if opcode == 13 or low < 0x8000 else low - 0x10000)) & 0xFFFFFFFF
                if 0x80010000 <= address < 0x80200000:
                    found[address].append({"source": source, "offset": i * 4,
                                           "low_offset": j * 4,
                                           "kind": "mips_lui_addiu" if opcode == 9 else "mips_lui_ori"})
            if dst == register and opcode in (8, 9, 12, 13, 14, 15, 32, 33, 35, 36, 37):
                break
    return found


def make_row(source, data, offset, end, kind, base, references, width=None, index=None):
    raw = data[offset:end]
    text = raw.decode("cp932")
    field_end = offset + width if width else end + 1
    row = {"id": f"{source}:{offset:06X}", "ja": text, "source": source,
           "source_kind": "exe" if source == "SLPS_022.32" else "overlay",
           "offset": offset, "end": end + 1, "max_bytes": width - 1 if width else len(raw),
           "original_byte_budget": len(raw), "field_end": field_end,
           "raw_hex": raw.hex(), "field_original_hex": data[offset:field_end].hex(),
           "encoding": "cp932", "kind": kind, "controls": list(dict.fromkeys(CONTROL.findall(text))),
           "references": references.get(base + offset, []), "virtual_address": base + offset,
           "source_sha256": sha(data), "source_language": "ja",
           "extraction_confidence": "structured_fixed_array" if width else "bounded_data_region_cstring",
           "safe_reinsertion": "fixed_field" if width else "in_place_original_capacity",
           "exact_glossary_field_eligible": kind in ("weapon_name", "unit_name", "scenario_title", "ui_label", "character_name"),
           "pointer_changes_required": False}
    if width:
        row.update(field_width=width, record_index=index,
                   record_stride=0x34 if kind == "weapon_name" else 0x3A)
    if source == "SLPS_022.32":
        row["synchronized_mirror"] = "gr.exe"
    interior = [{"target_offset": target - base, "references": refs}
                for target, refs in references.items() if base + offset < target < base + end]
    row["interior_references"] = interior
    if interior:
        row["safe_reinsertion"] = "review_interior_references"
    return row


def infer_kind(source, offset, text):
    if source == "SLPS_022.32" and 0x2730 <= offset < 0x28D0:
        return "scenario_title"
    if "$" in text or "「" in text or "\n" in text or len(text) > 28:
        return "dialogue" if "$f" in text or "$m" in text or "「" in text else "ui_message"
    if source == "bin/title.bin" and offset == 0x924:
        return "character_name"
    if source == "bin/briefing.bin" and 0x188C <= offset < 0x18F4:
        return "unit_name"
    return "ui_label" if not CONTROL.search(text) else "ui_message"


def extract(source_root):
    exe = source_root / "disc.provisional/SLPS_022.32"
    paths = [("SLPS_022.32", exe)] + [("bin/" + p.name, p) for p in sorted((source_root / "unpacked_vfs/bin").glob("*.bin"))]
    files = {source: path.read_bytes() for source, path in paths}
    allrefs = defaultdict(list)
    localrefs = {}
    for source, data in files.items():
        localrefs[source] = pointer_references(data, source)
        for address, refs in localrefs[source].items():
            allrefs[address] += refs
    rows, candidates = [], []
    data = files["SLPS_022.32"]
    for start, count, stride, width, kind in [(0x2EF4, 259, 0x34, 32, "weapon_name"), (0x63A8, 111, 0x3A, 24, "unit_name")]:
        for index in range(count):
            offset = start + index * stride
            slot = data[offset:offset + width]
            end = slot.find(b"\0")
            if end < 0 or any(slot[end:]):
                raise ValueError(f"Invalid {kind} slot {index}")
            if end == 0:
                continue
            text = slot[:end].decode("cp932")
            if text.encode("cp932") != slot[:end]:
                raise ValueError("Fixed field CP932 roundtrip mismatch")
            rows.append(make_row("SLPS_022.32", data, offset, offset + end, kind, 0x8000F800, allrefs, width, index))
    for source, data in files.items():
        name = Path(source).name
        base = 0x8000F800 if source == "SLPS_022.32" else BASES.get(name, 0x800F87A8)
        refs = allrefs if source == "SLPS_022.32" else localrefs[source]
        regions = [(0x9A8, 0xABE4), (0x72A10, 0x72A68), (0x7354C, 0x73554), (0x73690, 0x737DC)] if source == "SLPS_022.32" else REGIONS.get(name, [])
        spans = {(match.start(), match.end()) for match in RUN.finditer(data)
                 if match.end() < len(data) and data[match.end()] == 0}
        # Pointer targets recover real strings that follow binary metadata and
        # short one-character labels rejected by a generic long-run scan.
        for address in refs:
            offset = address - base
            if 0 <= offset < len(data):
                end = data.find(b"\0", offset, min(offset + 8001, len(data)))
                if end > offset:
                    spans.add((offset, end))
        accepted = []
        for offset, end in sorted(spans, key=lambda item: (item[0], -item[1])):
            if source == "SLPS_022.32" and (0x2EF4 <= offset < 0x6390 or 0x63A8 <= offset < 0x7CCE):
                continue
            text = text_value(data[offset:end])
            if text is None:
                continue
            if any(a <= offset < b for a, b in accepted):
                continue
            # This literal follows a pointer table with no separating NUL;
            # its aligned start and complete CP932/NUL field were inspected.
            inspected_literal = source == "bin/debug.bin" and offset == 0x1DA0
            bounded_start = offset == 0 or data[offset - 1] == 0 or base + offset in refs or inspected_literal
            known_region = any(a <= offset and end < b for a, b in regions)
            row = make_row(source, data, offset, end, infer_kind(source, offset, text), base, refs)
            if source == "bin/title.bin" and 0x500 <= offset < 0x8A0:
                row.update(extraction_confidence="name_entry_character_table", safe_reinsertion="preserve_original",
                           exact_glossary_field_eligible=False, translation_policy="preserve",
                           candidate_reason="name_entry_charset_is_not_translatable_prose")
                candidates.append(row)
                continue
            if bounded_start and known_region:
                rows.append(row)
                accepted.append((offset, end))
            else:
                row.update(extraction_confidence="scan_candidate_only", safe_reinsertion="not_authorized_by_extraction",
                           exact_glossary_field_eligible=False,
                           candidate_reason="outside_verified_text_data" if not known_region else "start_not_bounded")
                candidates.append(row)
    rows.sort(key=lambda row: (row["source"], row["offset"]))
    checks = []
    for source, data in files.items():
        output = bytearray(data)
        source_rows = [row for row in rows if row["source"] == source]
        for row in source_rows:
            encoded = row["ja"].encode("cp932")
            old = bytes.fromhex(row["field_original_hex"])
            replacement = encoded + b"\0" * (len(old) - len(encoded))
            if replacement != old:
                raise ValueError(f"Field no-op mismatch: {row['id']}")
            output[row["offset"]:row["field_end"]] = replacement
        if bytes(output) != data:
            raise ValueError(f"Source no-op rebuild changed: {source}")
        checks.append({"source": source, "fields": len(source_rows), "bytes": len(data), "source_sha256": sha(data),
                       "rebuilt_sha256": sha(output), "byte_exact": True})
    mirror = (source_root / "unpacked_vfs/gr.exe").read_bytes()
    if mirror != files["SLPS_022.32"]:
        raise ValueError("SLPS_022.32 and GR.EXE differ")
    return rows, candidates, {"entries": len(rows), "unique_texts": len({r['ja'] for r in rows}),
                              "kind_counts": dict(Counter(row["kind"] for row in rows)),
                              "candidate_only": len(candidates),
                              "interior_reference_fields": [r["id"] for r in rows if r["interior_references"]],
                              "noop_rebuild_checks": checks, "exe_mirror_byte_exact": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "work/source")
    parser.add_argument("--output", type=Path, default=ROOT / "work/source/core_corpus.jsonl")
    args = parser.parse_args()
    rows, candidates, report = extract(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for path, values in [(args.output, rows), (args.output.with_name("core_candidates.jsonl"), candidates)]:
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in values))
    args.output.with_name("core_extraction_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != "noop_rebuild_checks"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Extract Getter PAC scenario pools and deduplicate Japanese text for MT."""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
from getter_text import CONTROL, extract_strings


def script_pool(data):
    entrypoints = []
    pos = 0
    while pos + 4 <= len(data):
        value = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if value == 0:
            break
        if value >= len(data) or value % 4 or pos > 1024:
            raise ValueError("Invalid scenario entrypoint table")
        entrypoints.append(value)
    if not entrypoints:
        raise ValueError("Empty scenario entrypoint table")
    text_start = pos
    strings = []
    while pos < min(entrypoints):
        end = data.find(b"\0", pos)
        if end < 0:
            break
        raw = data[pos:end]
        if not raw:
            pos = end + 1
            continue
        try:
            text = raw.decode("cp932")
        except UnicodeDecodeError:
            break
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            break
        strings.append({"offset": pos, "end": end + 1, "ja": text,
                        "raw_hex": raw.hex(), "controls": list(dict.fromkeys(CONTROL.findall(text)))})
        pos = end + 1
    return {"entrypoints": entrypoints, "pool_start": text_start,
            "pool_end": pos, "strings": strings}


def matching_u32_references(data, starts, scan_start, scan_end=None):
    found = defaultdict(list)
    limit = len(data) if scan_end is None else scan_end
    for field in range((scan_start + 3) & ~3, limit - 3, 4):
        value = struct.unpack_from("<I", data, field)[0]
        if value in starts:
            before = data[max(0, field - 8):field]
            found[value].append({"field_offset": field, "kind": "absolute_u32_offset_candidate",
                                 "preceding_8_hex": before.hex(),
                                 "verified_vm_instruction": False})
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unpacked_root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())["entries"]
    groups = {}
    occurrences = []
    assets = []
    for member in manifest:
        if member.get("status") != "extracted" or not member["name"].endswith((".bin", ".dat")):
            continue
        relative = member["output"]
        data = (args.unpacked_root / relative).read_bytes()
        source_hash = hashlib.sha256(data).hexdigest()
        strict_pool = member["source"].startswith("mapef/") and member["name"].endswith(".bin")
        if strict_pool:
            pool = script_pool(data)
            rows = []
            for string in pool["strings"]:
                if any(0x3040 <= ord(c) <= 0x30FF or 0x3400 <= ord(c) <= 0x9FFF
                       for c in string["ja"]):
                    rows.append(string)
            references = matching_u32_references(data, {x["offset"] for x in rows}, pool["pool_end"])
            for row in rows:
                row["references"] = references[row["offset"]]
                row["extraction_confidence"] = "sequential_validated_cp932_scenario_pool"
            format_info = {"format": "scenario_entrypoints_and_cstrings", **{
                k: pool[k] for k in ("entrypoints", "pool_start", "pool_end")}}
        else:
            rows = extract_strings(data, relative, "pac_asset")
            format_info = {"format": "cp932_cstring_candidates"}
        if not rows:
            continue
        assets.append({"output": relative, "source": member["source"],
                       "member_name": member["name"], "member_index": member["index"],
                       "container_chain": member["container_chain"],
                       "sha256": source_hash, "entries": len(rows), **format_info})
        for row in rows:
            raw = bytes.fromhex(row["raw_hex"])
            if row["ja"].encode("cp932") != raw:
                raise ValueError(f"CP932 round trip mismatch: {relative}:{row['offset']:#x}")
            digest = hashlib.sha256(raw).hexdigest()
            canonical_id = "getter_" + digest[:20]
            occurrence = {"id": f"{relative}:{row['offset']:06X}", "canonical_id": canonical_id,
                          "source": member["source"], "member": member["name"],
                          "member_index": member["index"], "container_chain": member["container_chain"],
                          "asset": relative, "offset": row["offset"], "end": row["end"],
                          "original_byte_budget": len(raw), "source_sha256": source_hash,
                          "references": row.get("references", []),
                          "extraction_confidence": row["extraction_confidence"]}
            occurrences.append(dict(occurrence, ja=row["ja"], raw_hex=row["raw_hex"], controls=row["controls"]))
            if digest not in groups:
                groups[digest] = {"id": canonical_id, "ja": row["ja"], "source": member["source"],
                                  "member": member["name"], "offset": row["offset"],
                                  "raw_hex": row["raw_hex"], "encoding": "cp932",
                                  "controls": row["controls"], "references": row.get("references", []),
                                  "occurrences": []}
            groups[digest]["occurrences"].append(occurrence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in groups.values()))
    occurrence_path = args.output.with_name(args.output.stem + "_occurrences.jsonl")
    occurrence_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in occurrences))
    report = {"unique_texts": len(groups), "occurrences": len(occurrences),
              "unique_characters_total": sum(len(row["ja"]) for row in groups.values()),
              "assets_with_text": len(assets),
              "formats": dict(Counter(a["format"] for a in assets)),
              "all_cp932_roundtrips_exact": True,
              "note": "All existing text bytes preserved. VM reference candidates are not safe to rewrite until verified; bounded in-place replacement does not require changing them.",
              "assets": assets}
    args.output.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "assets"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

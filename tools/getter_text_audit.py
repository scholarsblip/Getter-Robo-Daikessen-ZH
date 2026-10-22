#!/usr/bin/env python3
"""Conservatively classify extracted PAC text against original data structures.

CP932 decoding alone is not evidence of text. In particular a candidate in
KT11 native MIPS code happens to decode as Japanese and must never be changed.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

STRICT = "sequential_validated_cp932_scenario_pool"
NATIVE_FALSE_ID = "getter_f3736888e17ebef4c534"


def _u32(data, offset=0):
    return struct.unpack_from("<I", data, offset)[0]


def audit_occurrences(unpacked_root, occurrences):
    """Return source-bound allow/deny evidence for every original occurrence."""
    by_asset = defaultdict(list)
    for row in occurrences:
        by_asset[row["asset"]].append(row)
    report = {"method": "Original fixed-field schemas, VM layout and string references",
              "assets": [], "excluded_occurrences": [], "excluded_canonical": [],
              "runtime_verified": False}
    allowed = set()
    excluded = {}
    for asset, rows in by_asset.items():
        data = (Path(unpacked_root) / asset).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        for row in rows:
            if row["source_sha256"] != digest:
                raise ValueError(f"Audit source hash differs: {asset}")
            raw = bytes.fromhex(row["raw_hex"])
            if data[row["offset"]:row["end"]] != raw + b"\0":
                raise ValueError(f"Audit original span differs: {row['id']}")
        evidence = {"asset": asset, "source_sha256": digest, "occurrences": len(rows),
                    "approved": [], "excluded": []}
        if all(row["extraction_confidence"] == STRICT for row in rows):
            # The original extractor strictly parsed entrypoint and contiguous
            # C-string pools; repeat that parse instead of trusting its label.
            from getter_scenarios import script_pool
            pool = script_pool(data)
            spans = {(r["offset"], r["end"], r["raw_hex"]) for r in pool["strings"]}
            for row in rows:
                if (row["offset"], row["end"], row["raw_hex"]) not in spans:
                    raise ValueError(f"Strict scenario pool reparse differs: {row['id']}")
            reason = "reparsed_strict_scenario_pool"
            for row in rows:
                evidence["approved"].append({"offset": row["offset"], "reason": reason})
                allowed.add(row["id"])
            report["assets"].append(evidence)
            continue
        # Collect aligned relative values only as supporting evidence. Numeric
        # constants may coincide with text offsets, so no relocation is inferred.
        references = defaultdict(list)
        for offset in range(0, len(data) - 3, 4):
            references[_u32(data, offset)].append(offset)
        sorted_rows = sorted(rows, key=lambda r: r["offset"])
        direct = {row["offset"] for row in rows if references[row["offset"]]}
        for position, row in enumerate(sorted_rows):
            offset, end = row["offset"], row["end"]
            reason = None
            if row["canonical_id"] == NATIVE_FALSE_ID:
                reason = "excluded_native_mips_instruction_bytes"
                if data[0x958:0x960].hex() != "0800838e21904000" or offset != 0x95A:
                    raise ValueError("Known native-code false-positive evidence differs")
            elif asset == "mapsys/mcn_prm.pac.members/0000_mcn_prm2.bin":
                # Header gives two indexed record arrays: 237 weapon records of
                # 52 bytes, then 102 unit records of 58 bytes. Names occupy the
                # first 32 and 24 bytes respectively, with NUL padding.
                if [_u32(data, i) for i in (0, 4, 8, 12)] != [0x10, 0x3024, 0x3034, 0x171C]:
                    raise ValueError("Machine/weapon table header differs")
                field_size = 32 if 0x10 <= offset < 0x3034 and (offset - 0x10) % 52 == 0 else (
                    24 if 0x3034 <= offset < len(data) and (offset - 0x3034) % 58 == 0 else 0)
                if field_size and end <= offset + field_size and not any(data[end:offset + field_size]):
                    reason = "verified_indexed_weapon_or_unit_name_field"
            elif asset in ("mapsys/mapalway.pac.members/0104_pil_prm.bin",
                           "mapsys/mcn_prm.pac.members/0001_pil_prm.bin"):
                count = _u32(data)
                fields = struct.unpack_from(f"<{count}I", data, 4)
                if count not in (53, 56) or fields[0] != 4 + count * 4:
                    raise ValueError("Pilot parameter pointer table differs")
                if offset in fields and end <= offset + 20 and not any(data[end:offset + 20]):
                    reason = "verified_pilot_pointer_table_20byte_name_field"
            else:
                is_battle_vm = ("tmv.pac.members/" in asset or asset == "prog00/kt15v.pac.members/0016_ht15v.bin")
                is_briefing_vm = asset == "mapsys/briefing.pac.members/0038_briefing.bin"
                is_unit_vm = asset == "prog00/unit.pac.members/0000_unit.bin"
                valid_layout = (is_battle_vm and _u32(data) == 8 and 0x108 <= offset < end <= _u32(data, 4)) or is_briefing_vm or is_unit_vm
                if valid_layout and offset % 4 == 0:
                    if offset in direct:
                        reason = "aligned_coherent_vm_cstring_with_relative_value_reference"
                    else:
                        # Four coherent legacy strings have no own reference.
                        # They are directly contiguous with referenced Japanese
                        # strings in the same NUL/padding text sequence.
                        neighbours = []
                        if position:
                            previous = sorted_rows[position - 1]
                            if previous["offset"] in direct and 0 <= offset - previous["end"] <= 3 and not any(data[previous["end"]:offset]):
                                neighbours.append(previous["offset"])
                        if position + 1 < len(sorted_rows):
                            following = sorted_rows[position + 1]
                            if following["offset"] in direct and 0 <= following["offset"] - end <= 3 and not any(data[end:following["offset"]]):
                                neighbours.append(following["offset"])
                        if neighbours:
                            reason = "contiguous_vm_cstring_next_to_referenced_text"
            if reason and not reason.startswith("excluded_"):
                allowed.add(row["id"])
                evidence["approved"].append({"offset": offset, "reason": reason,
                                             "supporting_relative_value_fields": references[offset]})
            else:
                reason = reason or "unverified_nonstrict_cp932_candidate"
                item = {"id": row["id"], "canonical_id": row["canonical_id"], "ja": row["ja"],
                        "asset": asset, "offset": offset, "source_sha256": digest, "reason": reason}
                excluded[row["id"]] = item
                evidence["excluded"].append(item)
                report["excluded_occurrences"].append(item)
        report["assets"].append(evidence)
    report["excluded_canonical"] = sorted({row["canonical_id"] for row in excluded.values()})
    report["approved_occurrences"] = len(allowed)
    report["total_occurrences"] = len(occurrences)
    report["nonstrict_assets"] = sum(any(r["extraction_confidence"] != STRICT for r in rows) for rows in by_asset.values())
    report["approval_reasons"] = dict(Counter(x["reason"] for asset in report["assets"] for x in asset["approved"]))
    report["limits"] = "Static data-structure audit; relative numeric coincidences are not certified VM pointers and are never rewritten. Runtime rendering remains unverified."
    return allowed, excluded, report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "work/source"
    rows = [json.loads(line) for line in (source / "scenario_corpus_occurrences.jsonl").read_text().splitlines()]
    _, _, report = audit_occurrences(source / "unpacked_pac", rows)
    (source / "scenario_safety_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "assets"}, ensure_ascii=False, indent=2))

#!/usr/bin/env python3
"""Assemble a source-verified, explicitly experimental Getter Chinese image.

Dry run is the default. --write writes a new versioned output directory and
never changes the Japanese source, unpacked original assets, or font inputs.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
BIN_SHA = "08f189c914fa753af0ba690579712636f1d8b21eb7777c89b6fc10041c725807"
EXE_SHA = "edc4b01e09708d64db21430ed341e4fb222799089a2ca360f329a8fe15f5bb8b"
VFS_SHA = "e1e300dd53388b7da2d47bac1a25cc3b4adf20d8e2120314b8bf3faab9f1192b"
SECTOR = 2352
PRINTF = re.compile(r"%(?:[-+ #0]*\d*(?:\.\d+)?[hlLzjt]*[diuoxXfFeEgGaAcspn]|%)")
RUNTIME_LITERALS = {
    "SLPS_022.32:073690": ("げんき", "82b082f182ab00", "runtime_name_trigger"),
    "SLPS_022.32:07354C": ("ななし", "82c882c882b500", "japanese_name_entry_default"),
    "SLPS_022.32:0737D4": ("ななし", "82c882c882b500", "japanese_name_entry_default"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validated_translations(source_rows, translated_rows, label):
    """Merge compact hash-bound or legacy JA rows with authoritative extraction.

    Public rows need only id, zh_CN and source_text_sha256. The original text,
    controls, field budgets, raw bytes and occurrences remain local authority.
    """
    from getter_text import CONTROL
    source = {row["id"]: row for row in source_rows}
    if len(source) != len(source_rows):
        raise ValueError(f"Duplicate authoritative {label} IDs")
    translations = {}
    for row in translated_rows:
        identity = row["id"]
        if identity not in source or identity in translations:
            raise ValueError(f"Unknown/duplicate {label} translation ID: {identity}")
        original = source[identity]
        if "ja" not in row and "source_text_sha256" not in row:
            raise ValueError(f"Missing source text/hash binding: {identity}")
        if "ja" in row and row["ja"] != original["ja"]:
            raise ValueError(f"Translated source text differs: {identity}")
        if "source_text_sha256" in row and row["source_text_sha256"] != sha(original["ja"].encode("utf-8")):
            raise ValueError(f"Translated source text hash differs: {identity}")
        value = row.get("zh_CN")
        if value:
            if not isinstance(value, str) or "\0" in value:
                raise ValueError(f"Invalid {label} translated text: {identity}")
            if CONTROL.findall(value) != CONTROL.findall(original["ja"]):
                raise ValueError(f"Control sequence differs: {identity}")
            if PRINTF.findall(original["ja"]) and PRINTF.findall(value) != PRINTF.findall(original["ja"]):
                raise ValueError(f"Printf format sequence differs: {identity}")
            if any(ord(ch) in (0x200B, 0xFEFF) for ch in value):
                raise ValueError(f"Invisible MT formatting character: {identity}")
        translations[identity] = row
    merged = []
    for original in source_rows:
        row = dict(original)
        translated = translations.get(row["id"], {})
        row.update({key: translated[key] for key in ("zh_CN", "mt") if key in translated})
        merged.append(row)
    return merged, {"expected_rows": len(source_rows), "supplied_rows": len(translations),
                    "missing_ids": sorted(set(source) - set(translations))}


def read_user(stream, lba, size):
    out = bytearray()
    for i in range(math.ceil(size / 2048)):
        stream.seek((lba + i) * SECTOR)
        sector = stream.read(SECTOR)
        if len(sector) != SECTOR or sector[15] != 2 or sector[18] & 0x20:
            raise ValueError(f"Expected complete Mode2 Form1 sector {lba+i}")
        out += sector[24:2072]
    return bytes(out[:size])


def iso_root(stream):
    pvd = read_user(stream, 16, 2048)
    if pvd[:7] != b"\x01CD001\x01":
        raise ValueError("Unexpected ISO primary volume descriptor")
    root_lba, root_size = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
    root = read_user(stream, root_lba, root_size)
    files = {}
    pos = 0
    while pos < len(root):
        length = root[pos]
        if not length:
            pos = (pos // 2048 + 1) * 2048
            continue
        record = root[pos:pos + length]
        name = record[33:33 + record[32]]
        if name not in (b"\0", b"\1"):
            files[name.decode("ascii").split(";", 1)[0]] = {
                "lba": struct.unpack_from("<I", record, 2)[0],
                "size": struct.unpack_from("<I", record, 10)[0], "record_offset": pos}
        pos += length
    return root_lba, root, files, pvd


def merge_disjoint(original, font_exe, text_exe):
    if len(original) != len(font_exe) or len(original) != len(text_exe):
        raise ValueError("EXE merge changed executable length")
    out = bytearray(font_exe)
    for i, (old, new) in enumerate(zip(original, text_exe)):
        if old != new:
            if font_exe[i] != old and font_exe[i] != new:
                raise ValueError(f"Font/text EXE patch overlap at {i:#x}")
            out[i] = new
    return bytes(out)


def patch_setup_reservation(original, merged_exe, setup_pac_size):
    """Grow only SetupMan's fixed load buffer when its rebuilt PAC needs it.

    Two control-flow paths reach the same ORI: one supplies LUI in a jump delay
    slot. Both high-immediate sites are checked and patched together.
    """
    base = 0x8000F800
    sites = {0x80051F54: 0x3C040004, 0x80051F64: 0x3C040004,
             0x80051F68: 0x3484000C}
    for address, expected in sites.items():
        offset = address - base
        if struct.unpack_from("<I", original, offset)[0] != expected:
            raise ValueError(f"Unexpected original SetupMan allocation instruction: {address:#x}")
        if merged_exe[offset:offset + 4] != original[offset:offset + 4]:
            raise ValueError(f"SetupMan allocation overlaps another EXE patch: {address:#x}")
    old_size = 0x4000C
    new_size = max(old_size, (setup_pac_size + 12 + 15) & ~15)
    # The verified rebuild needs about 27KiB extra. Reject materially different
    # future growth rather than silently taking a large fraction of PS1 RAM.
    if new_size > old_size + 65536:
        raise ValueError("Rebuilt setup.pac exceeds the reviewed 64KiB allocation growth bound")
    output = bytearray(merged_exe)
    for address in (0x80051F54, 0x80051F64):
        struct.pack_into("<I", output, address - base, 0x3C040000 | (new_size >> 16))
    struct.pack_into("<I", output, 0x80051F68 - base, 0x34840000 | (new_size & 0xFFFF))
    for address in (0x80051F54, 0x80051F64):
        high = struct.unpack_from("<I", output, address - base)[0] & 0xFFFF
        low = struct.unpack_from("<I", output, 0x80051F68 - base)[0] & 0xFFFF
        if (high << 16 | low) != new_size:
            raise ValueError("SetupMan allocation instruction readback differs")
    report = {"original_request_bytes": old_size, "rebuilt_pac_bytes": setup_pac_size,
              "loader_prefix_bytes": 12, "alignment": 16,
              "patched_request_bytes": new_size, "increase_bytes": new_size - old_size,
              "maximum_reviewed_growth_bytes": 65536,
              "instruction_sites": [hex(address) for address in sites],
              "both_control_flow_paths_verified": True,
              "original_allocation_function": "0x8002DE20",
              "original_load_function": "0x8002E958",
              "other_heap_reservations_changed": False}
    return bytes(output), report


def patch_pac_reservations(originals, replacements):
    """Patch verified fixed PAC buffers, preserving all call flow."""
    specs = [
        {"source": "bin/title.bin", "base": 0x8008B7A8,
         "files": ["demo/title.pac", "demo/title2.pac"], "old_size": 0x33000,
         "high_address": 0x8008C604, "low_address": 0x8008C608,
         "high_opcode": 0x3C040003, "low_opcode": 0x34843000,
         "register": "a0", "load_call": "0x8008C650",
         "allocation_call": "0x8008C610"},
        {"source": "bin/briefing.bin", "base": 0x800A97A8,
         "files": ["mapsys/briefing.pac"], "old_size": 0x1E000,
         "high_address": 0x800BE010, "low_address": 0x800BE018,
         "high_opcode": 0x3C070001, "low_opcode": 0x34E7E000,
         "register": "a3", "load_call": "0x800BEA60",
         "allocation_call": "0x800BEA2C"},
        {"source": "bin/battle.bin", "base": 0x800A97A8,
         "files": sorted(name for name in replacements if name.startswith("prog00/") and name.endswith(".pac")),
         "old_size": 0x15000,
         "high_address": 0x800ACB40, "low_address": 0x800ACB44,
         "high_opcode": 0x3C040001, "low_opcode": 0x34845000,
         "register": "a0", "load_call": "0x800ACB78",
         "allocation_call": "0x800ACB4C"},
    ]
    reports = []
    for spec in specs:
        source = spec["source"]
        original = originals[source]
        current = replacements.get(source, original)
        output = bytearray(current)
        actual_sizes = {name: len(replacements[name]) for name in spec["files"]}
        required = max(actual_sizes.values())
        new_size = max(spec["old_size"], (required + 15) & ~15)
        if new_size > spec["old_size"] + 65536:
            raise ValueError(f"{source} fixed PAC buffer exceeds reviewed 64KiB growth bound")
        for address_key, opcode_key in (("high_address", "high_opcode"), ("low_address", "low_opcode")):
            address, expected = spec[address_key], spec[opcode_key]
            offset = address - spec["base"]
            if struct.unpack_from("<I", original, offset)[0] != expected or current[offset:offset + 4] != original[offset:offset + 4]:
                raise ValueError(f"Unexpected/overlapping PAC allocation opcode: {source}:{address:#x}")
        high_off, low_off = spec["high_address"] - spec["base"], spec["low_address"] - spec["base"]
        struct.pack_into("<I", output, high_off, spec["high_opcode"] & 0xFFFF0000 | new_size >> 16)
        struct.pack_into("<I", output, low_off, spec["low_opcode"] & 0xFFFF0000 | new_size & 0xFFFF)
        decoded = ((struct.unpack_from("<I", output, high_off)[0] & 0xFFFF) << 16 |
                   struct.unpack_from("<I", output, low_off)[0] & 0xFFFF)
        if decoded != new_size or len(output) != len(original):
            raise ValueError("Fixed PAC buffer patch readback/length differs")
        changed = [i for i, (a, b) in enumerate(zip(current, output)) if a != b]
        permitted = set(range(high_off, high_off + 2)) | set(range(low_off, low_off + 2))
        if set(changed) - permitted:
            raise ValueError("Fixed PAC buffer patch changed non-immediate instruction bytes")
        replacements[source] = bytes(output)
        reports.append({"source": source, "files_and_rebuilt_sizes": actual_sizes,
                        "original_request_bytes": spec["old_size"], "patched_request_bytes": new_size,
                        "increase_bytes": new_size - spec["old_size"], "loader_prefix_bytes": 0,
                        "alignment": 16, "maximum_reviewed_growth_bytes": 65536,
                        "instruction_sites": [hex(spec["high_address"]), hex(spec["low_address"])],
                        "argument_register": spec["register"], "load_call": spec["load_call"],
                        "allocation_call": spec["allocation_call"], "changed_byte_offsets": changed,
                        "unrelated_instruction_bytes_preserved": True})
    return reports


def apply_core(originals, rows, encode):
    output = {name: bytearray(data) for name, data in originals.items()}
    seen = defaultdict(list)
    report = {"applied": [], "skipped": []}
    for row in rows:
        source = row["source"]
        if source not in originals:
            raise ValueError(f"Unknown core source {source}")
        original = originals[source]
        if sha(original) != row["source_sha256"]:
            raise ValueError(f"Core source hash mismatch: {row['id']}")
        start, end = row["offset"], row["field_end"]
        if not 0 <= start < end <= len(original) or row["max_bytes"] > end - start - 1:
            raise ValueError(f"Invalid authoritative core field bounds: {row['id']}")
        field = bytes.fromhex(row["field_original_hex"])
        if original[start:end] != field:
            raise ValueError(f"Core original field mismatch: {row['id']}")
        reason = None
        if row["id"] in RUNTIME_LITERALS:
            expected_ja, expected_hex, reason = RUNTIME_LITERALS[row["id"]]
            if row["ja"] != expected_ja or field.hex() != expected_hex:
                raise ValueError(f"Runtime literal original differs: {row['id']}")
        elif row.get("translation_policy") == "preserve":
            reason = "preserve_original_policy"
        elif row.get("interior_references") or row.get("safe_reinsertion") == "review_interior_references":
            reason = "ambiguous_interior_reference"
        elif not isinstance(row.get("zh_CN"), str) or not row["zh_CN"]:
            reason = "missing_machine_translation"
        if reason:
            report["skipped"].append({"id": row["id"], "reason": reason})
            continue
        encoded = encode(row["zh_CN"])
        if b"\0" in encoded:
            raise ValueError(f"NUL in encoded core string {row['id']}")
        if len(encoded) > row["max_bytes"]:
            report["skipped"].append({"id": row["id"], "reason": "overflow",
                                       "budget": row["max_bytes"], "encoded_bytes": len(encoded),
                                       "ja": row["ja"], "zh_CN": row["zh_CN"]})
            continue
        for a, z in seen[source]:
            if a < end and start < z:
                raise ValueError(f"Overlapping core fields: {row['id']}")
        seen[source].append((start, end))
        output[source][start:end] = encoded + b"\0" * (end - start - len(encoded))
        report["applied"].append({"id": row["id"], "bytes": len(encoded), "budget": row["max_bytes"]})
    report["skipped_reasons"] = dict(Counter(r["reason"] for r in report["skipped"]))
    return {name: bytes(data) for name, data in output.items()}, report


def make_build(args):
    from getter_font import encode as encode_font, decode as decode_font, patch_exe as font_patch_exe
    from getter_reinsert import patch_text_asset, rebuild_affected_pacs
    from getter_text_audit import audit_occurrences
    from getter_vfs import parse as parse_vfs, rebuild as rebuild_vfs
    source = args.source
    original_bin = source / "original.bin"
    if file_sha(original_bin) != BIN_SHA:
        raise ValueError("Japanese BIN SHA256 does not match the verified original")
    if original_bin.stat().st_size != 663111120:
        raise ValueError("Unexpected Japanese BIN byte count")
    exe = (source / "disc.provisional/SLPS_022.32").read_bytes()
    vfs = (source / "disc.provisional/GR.VFS").read_bytes()
    if sha(exe) != EXE_SHA or sha(vfs) != VFS_SHA:
        raise ValueError("Unpacked core sources differ from verified extraction")
    vfs_manifest = parse_vfs(vfs)
    vf = {r["path"]: r for r in vfs_manifest["records"] if not r["is_directory"]}
    mirror = vf["gr.exe"]
    if vfs[mirror["offset"]:mirror["offset"] + mirror["size"]] != exe:
        raise ValueError("The two original EXE copies differ")
    with original_bin.open("rb") as stream:
        root_lba, root, iso, pvd = iso_root(stream)
        if read_user(stream, iso["GR.VFS"]["lba"], iso["GR.VFS"]["size"]) != vfs:
            raise ValueError("VFS in the fully downloaded BIN differs from extraction")
        if read_user(stream, iso["SLPS_022.32"]["lba"], iso["SLPS_022.32"]["size"]) != exe:
            raise ValueError("EXE in the fully downloaded BIN differs from extraction")
    font_plan = json.loads((args.font_build / "plan.json").read_text())
    if font_plan.get("original_exe_sha256") != EXE_SHA:
        raise ValueError("Font build does not name the verified original EXE")
    font_exe = (args.font_build / "SLPS_022.32.font-only").read_bytes()
    if font_patch_exe(exe, dict(font_plan)) != font_exe:
        raise ValueError("Font EXE differs from the declared custom-font hook patch")
    bss_file_start = 0x800833B0 - 0x8000F800
    if font_exe[bss_file_start:] != exe[bss_file_start:]:
        raise ValueError("Font hook overlaps startup-cleared BSS bytes")
    def encode(text):
        result = encode_font(text, font_plan)
        if decode_font(result, font_plan) != text:
            raise ValueError("Custom font encoding failed a round trip")
        return result
    core_rows, core_input = validated_translations(jsonl(source / "core_corpus.jsonl"), jsonl(args.core_mt), "core")
    scenario_rows, scenario_input = validated_translations(jsonl(source / "scenario_corpus.jsonl"), jsonl(args.scenario_mt), "scenario")
    originals = {"SLPS_022.32": exe}
    for name in {r["source"] for r in core_rows} - {"SLPS_022.32"}:
        original = vf[name]
        originals[name] = vfs[original["offset"]:original["offset"] + original["size"]]
    patched_core, core_report = apply_core(originals, core_rows, encode)
    merged_exe = merge_disjoint(exe, font_exe, patched_core["SLPS_022.32"])
    for identity, (_, expected_hex, _) in RUNTIME_LITERALS.items():
        offset = int(identity.rsplit(":", 1)[1], 16)
        expected = bytes.fromhex(expected_hex)
        if merged_exe[offset:offset + len(expected)] != expected:
            raise ValueError(f"Preserved runtime literal changed: {identity}")
    replacements = {name: data for name, data in patched_core.items() if name != "SLPS_022.32" and data != originals[name]}
    replacements["gr.exe"] = merged_exe
    occurrences = jsonl(source / "scenario_corpus_occurrences.jsonl")
    safe_occurrences, unsafe_occurrences, safety_audit = audit_occurrences(source / "unpacked_pac", occurrences)
    safe_canonical = {row["canonical_id"] for row in occurrences if row["id"] in safe_occurrences}
    encoded_map = {}
    for row in scenario_rows:
        if row["id"] in safe_canonical and isinstance(row.get("zh_CN"), str) and row["zh_CN"]:
            encoded_map[row["id"]] = encode(row["zh_CN"])
    by_asset = defaultdict(list)
    for row in occurrences:
        if row["id"] in safe_occurrences:
            by_asset[row["asset"]].append(row)
    patched_assets = {}
    scenario_reports = {}
    for asset, rows in by_asset.items():
        original = (source / "unpacked_pac" / asset).read_bytes()
        patched, report = patch_text_asset(original, rows, encoded_map)
        scenario_reports[asset] = report
        if patched != original:
            patched_assets[asset] = patched
    pac_manifest = json.loads((source / "unpacked_pac_manifest.json").read_text())["entries"]
    font_replacements = []
    for row in pac_manifest:
        if row["name"] not in ("font12j0.tim", "font12j1.tim", "font12j2.tim"):
            continue
        if row["source"] not in ("bin/setup.pac", "demo/title.pac", "demo/title2.pac"):
            continue
        patched_assets[row["output"]] = (args.font_build / row["name"]).read_bytes()
        font_replacements.append({"source": row["source"], "member": row["name"], "index": row["index"]})
    if len(font_replacements) != 5:
        raise ValueError("Expected three setup fonts and two duplicate title fonts")
    replacements.update(rebuild_affected_pacs(source / "unpacked_vfs", pac_manifest, patched_assets))
    setup_pac = replacements.get("bin/setup.pac")
    if setup_pac is None:
        raise ValueError("Expected rebuilt setup PAC with Chinese font assets")
    merged_exe, setup_allocation = patch_setup_reservation(exe, merged_exe, len(setup_pac))
    setup_allocation["original_pac_bytes"] = vf["bin/setup.pac"]["size"]
    replacements["gr.exe"] = merged_exe
    other_pac_allocations = patch_pac_reservations(originals, replacements)
    rebuilt_vfs = rebuild_vfs(vfs, replacements)
    after_vfs = parse_vfs(rebuilt_vfs)
    new_mirror = next(r for r in after_vfs["records"] if r["path"] == "gr.exe")
    if rebuilt_vfs[new_mirror["offset"]:new_mirror["offset"] + new_mirror["size"]] != merged_exe:
        raise ValueError("Rebuilt VFS EXE mirror mismatch")
    # The original EXE has no byte-identical embedded VFS record table. CDFS
    # relocation requires separate original-code evidence, retained in manifest.
    original_table = vfs[0x800:0x800 + 404 * 32]
    cached_toc = exe.find(original_table)
    if cached_toc >= 0:
        raise ValueError("Embedded EXE VFS table found; synchronization implementation required")
    sorted_extents = sorted(r["lba"] for r in iso.values() if r["lba"] > iso["GR.VFS"]["lba"])
    capacity = (sorted_extents[0] - iso["GR.VFS"]["lba"]) * 2048
    relocated = len(rebuilt_vfs) > capacity
    original_sectors = original_bin.stat().st_size // SECTOR
    new_lba = original_sectors if relocated else iso["GR.VFS"]["lba"]
    total_sectors = new_lba + math.ceil(len(rebuilt_vfs) / 2048) if relocated else original_sectors
    proof = json.loads(args.vfs_lookup_proof.read_text()) if args.vfs_lookup_proof else None
    valid_lookup_proof = (proof and proof.get("filename_lookup_confirmed") is True
                          and proof.get("source_sha256") == EXE_SHA
                          and proof.get("filename") == "GR.VFS"
                          and proof.get("hardcoded_original_lba_in_inspected_mount_path") is False)
    if relocated and args.write and not valid_lookup_proof:
        raise ValueError("Growing VFS requires matching --vfs-lookup-proof original-EXE evidence before --write")
    oversize_ids = {x["id"] for r in scenario_reports.values() for x in r["oversize"]}
    oversize_canonical = [{"id": row["id"], "ja": row["ja"], "zh_CN": row.get("zh_CN"),
                           "encoded_bytes": len(encoded_map[row["id"]])}
                          for row in scenario_rows if row["id"] in oversize_ids]
    report = {"version": args.version, "status": "experimental_machine_translation_runtime_unverified",
              "original_bin_sha256": BIN_SHA, "original_exe_sha256": EXE_SHA,
              "original_vfs_sha256": VFS_SHA, "original_bin_preserved": True,
              "source_readback_matches_fully_downloaded_bin": True,
              "original_exe_copies_identical": True, "rebuilt_exe_copies_identical": True,
              "exe_font_and_text_edits_disjoint": True,
              "rebuilt_exe_sha256": sha(merged_exe),
              "startup_cleared_padding_remains_original": merged_exe[bss_file_start:] == exe[bss_file_start:],
              "setup_buffer_allocation": setup_allocation,
              "other_fixed_pac_buffer_allocations": other_pac_allocations,
              "font_plan": {k: v for k, v in font_plan.items() if k != "glyphs"},
              "font_replacements": font_replacements,
              "font_asset_sha256": {name: file_sha(args.font_build / name)
                                    for name in ("SLPS_022.32.font-only", "font12j0.tim", "font12j1.tim", "font12j2.tim")},
              "translation_inputs": {"core": core_input, "scenario": scenario_input,
                                     "core_mt_sha256": file_sha(args.core_mt),
                                     "scenario_mt_sha256": file_sha(args.scenario_mt),
                                     "font_plan_sha256": file_sha(args.font_build / "plan.json")},
              "core": core_report,
              "scenario": {"canonical_translations": len(encoded_map),
                           "safety_audit": {k: v for k, v in safety_audit.items() if k != "assets"},
                           "applied_occurrences": sum(len(r["applied"]) for r in scenario_reports.values()),
                           "missing_occurrences": sum(len(r["missing"]) for r in scenario_reports.values()),
                           "oversize_occurrences": sum(len(r["oversize"]) for r in scenario_reports.values()),
                           "oversize_unique": len(oversize_ids),
                           "oversize_canonical": oversize_canonical,
                           "per_asset": scenario_reports},
              "vfs": {"original_size": len(vfs), "new_size": len(rebuilt_vfs),
                      "available_original_extent_bytes": capacity, "relocated": relocated,
                      "old_lba": iso["GR.VFS"]["lba"], "new_lba": new_lba,
                      "new_sha256": sha(rebuilt_vfs), "changed_files": sorted(replacements),
                      "embedded_identical_exe_toc_offset": cached_toc,
                      "relocation_lookup_proof": proof},
              "disc": {"original_sectors": original_sectors, "new_sectors": total_sectors,
                       "new_bytes": total_sectors * SECTOR, "root_lba": root_lba},
              "unsupported_coverage": ["FMV/subtitle image rendering", "Japanese title/episode/result/name-entry bitmap localization", "Full playthrough and all branches", "Skipped overflow/interior-reference strings"],
              "runtime_verified": False, "write_requested": args.write}
    return report, (merged_exe, rebuilt_vfs, iso, root_lba, root, pvd, safety_audit)


def write_image(args, report, build):
    exe, vfs, iso, root_lba, root, pvd, safety_audit = build
    if args.output.exists():
        raise ValueError("Output directory already exists; choose a new version/path")
    args.output.mkdir(parents=True)
    from disc_form1 import fix_form1
    destination = args.output / ("Getter_Robo_Daikessen_ZH_" + args.version + ".bin")
    shutil.copyfile(args.source / "original.bin", destination)
    touched = []
    with destination.open("r+b") as stream:
        stream.seek(iso["GR.VFS"]["lba"] * SECTOR)
        template = stream.read(SECTOR)
        if template[15] != 2 or template[18] & 0x20:
            raise ValueError("VFS sector template is not Mode2 Form1")
        def user_write(lba, data, append=False, eof=False):
            chunks = math.ceil(len(data) / 2048)
            for index in range(chunks):
                target = lba + index
                if append:
                    sector = bytearray(template)
                    minute, rem = divmod(target + 150, 4500)
                    second, frame = divmod(rem, 75)
                    bcd = lambda value: value // 10 * 16 + value % 10
                    sector[12:16] = bytes((bcd(minute), bcd(second), bcd(frame), 2))
                    sector[18] = sector[22] = 0x89 if eof and index == chunks - 1 else 8
                    sector[24:2072] = b"\0" * 2048
                else:
                    stream.seek(target * SECTOR)
                    sector = bytearray(stream.read(SECTOR))
                    if len(sector) != SECTOR or sector[18] & 0x20:
                        raise ValueError(f"Cannot replace non-Form1 sector {target}")
                chunk = data[index * 2048:(index + 1) * 2048]
                sector[24:24 + len(chunk)] = chunk
                fix_form1(sector)
                stream.seek(target * SECTOR)
                stream.write(sector)
                touched.append(target)
        # Check that the shared generic EDC/ECC primitive reproduces original sectors.
        for lba in (16, root_lba, iso["SLPS_022.32"]["lba"], iso["GR.VFS"]["lba"]):
            stream.seek(lba * SECTOR)
            before = stream.read(SECTOR)
            if bytes(fix_form1(bytearray(before))) != before:
                raise ValueError("EDC/ECC primitive differs from original image")
        user_write(iso["SLPS_022.32"]["lba"], exe)
        user_write(report["vfs"]["new_lba"], vfs, append=report["vfs"]["relocated"], eof=True)
        changed_root = bytearray(root)
        pos = iso["GR.VFS"]["record_offset"]
        struct.pack_into("<I", changed_root, pos + 2, report["vfs"]["new_lba"])
        struct.pack_into(">I", changed_root, pos + 6, report["vfs"]["new_lba"])
        struct.pack_into("<I", changed_root, pos + 10, len(vfs))
        struct.pack_into(">I", changed_root, pos + 14, len(vfs))
        user_write(root_lba, changed_root)
        changed_pvd = bytearray(pvd)
        struct.pack_into("<I", changed_pvd, 80, report["disc"]["new_sectors"])
        struct.pack_into(">I", changed_pvd, 84, report["disc"]["new_sectors"])
        user_write(16, changed_pvd)
        stream.flush()
        if destination.stat().st_size != report["disc"]["new_bytes"]:
            raise ValueError("Output image length mismatch")
        _, _, actual_iso, actual_pvd = iso_root(stream)
        if actual_iso["GR.VFS"]["lba"] != report["vfs"]["new_lba"] or actual_iso["GR.VFS"]["size"] != len(vfs):
            raise ValueError("ISO VFS extent/size readback mismatch")
        if read_user(stream, actual_iso["GR.VFS"]["lba"], len(vfs)) != vfs:
            raise ValueError("Full VFS disc readback mismatch")
        if read_user(stream, actual_iso["SLPS_022.32"]["lba"], len(exe)) != exe:
            raise ValueError("Full EXE disc readback mismatch")
        for lba in sorted(set(touched)):
            stream.seek(lba * SECTOR)
            before = stream.read(SECTOR)
            if bytes(fix_form1(bytearray(before))) != before:
                raise ValueError(f"Modified sector EDC/ECC failed: {lba}")
    cue = destination.with_suffix(".cue")
    cue.write_text(f'FILE "{destination.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    report["validation"] = {"full_vfs_disc_readback_exact": True, "full_exe_disc_readback_exact": True,
                            "modified_sector_edc_ecc_verified": len(set(touched)),
                            "iso_vfs_extent_and_size_verified": True,
                            "output_sha256": file_sha(destination), "output_bytes": destination.stat().st_size}
    report["validation"]["final_exe_sha256"] = sha(exe)
    report["validation"]["setup_buffer_instruction_words_both_exe_copies"] = {
        hex(address): hex(struct.unpack_from("<I", exe, address - 0x8000F800)[0])
        for address in (0x80051F54, 0x80051F64, 0x80051F68)}
    report["validation"]["startup_cleared_padding_remains_original"] = report["startup_cleared_padding_remains_original"]
    # Compare every original sector, allowing changes only in the declared set.
    # This also proves that movie/audio extents and the old VFS payload survive.
    touched_set = set(touched)
    unchanged_sectors = 0
    with (args.source / "original.bin").open("rb") as original, destination.open("rb") as result:
        for lba in range(report["disc"]["original_sectors"]):
            before, after = original.read(SECTOR), result.read(SECTOR)
            if lba not in touched_set:
                if before != after:
                    raise ValueError(f"Unexpected modification of original sector {lba}")
                unchanged_sectors += 1
    report["validation"]["unchanged_original_sectors_verified"] = unchanged_sectors
    report["output"] = {"bin": str(destination), "cue": str(cue)}
    (args.output / "build_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (args.output / "font_plan.json").write_text((args.font_build / "plan.json").read_text())
    (args.output / "scenario_safety_audit.json").write_text(json.dumps(safety_audit, ensure_ascii=False, indent=2))
    (args.output / "README_中文.txt").write_text(
        "盖塔机器人大决战 PS1 简体中文机器翻译实验版\n\n"
        "本版本尚未完成运行验证和全流程测试。请查看 build_manifest.json 中的跳过项。\n"
        "过长文本和存在内部指针歧义的字段保留原文。动画字幕和菜单位图尚未汉化。\n"
        "原始日文镜像未修改。通过同目录 CUE 文件启动新镜像。\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "work/source")
    parser.add_argument("--scenario-mt", type=Path, required=True)
    parser.add_argument("--core-mt", type=Path, required=True)
    parser.add_argument("--font-build", type=Path, default=ROOT / "work/font/build-reviewed-v2")
    parser.add_argument("--version", default="v0.1.2-experimental")
    parser.add_argument("--output", type=Path, default=ROOT / "work/output/Getter_Robo_Daikessen_ZH_v0.1.2_experimental")
    parser.add_argument("--vfs-lookup-proof", type=Path)
    parser.add_argument("--report", type=Path, help="Optional dry-run manifest output")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report, build = make_build(args)
    if args.write:
        write_image(args, report, build)
    elif args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"version": report["version"], "write_requested": args.write,
                      "core_applied": len(report["core"]["applied"]),
                      "core_skipped": report["core"]["skipped_reasons"],
                      "scenario_applied_occurrences": report["scenario"]["applied_occurrences"],
                      "scenario_oversize_unique": report["scenario"]["oversize_unique"],
                      "vfs_original_bytes": report["vfs"]["original_size"],
                      "vfs_new_bytes": report["vfs"]["new_size"],
                      "vfs_relocated": report["vfs"]["relocated"],
                      "output": report.get("output"), "runtime_verified": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

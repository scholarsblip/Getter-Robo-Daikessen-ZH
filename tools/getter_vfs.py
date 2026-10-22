#!/usr/bin/env python3
"""Read-only original Getter Robo Daikessen! VFS0 resource extractor."""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path


def parse(data):
    if data[:4] != b"VFS0":
        raise ValueError("Not a VFS0 archive")
    count, root_count, data_sector = struct.unpack_from("<HHI", data, 4)
    table_base = 0x800
    data_base = data_sector * 2048
    if table_base + count * 32 > data_base:
        raise ValueError("Directory table overlaps payload area")
    records = []
    for i in range(count):
        field = table_base + i * 32
        raw = data[field:field + 32]
        sector, size = struct.unpack_from("<II", raw)
        name = raw[8:31].split(b"\0", 1)[0].decode("ascii")
        flags = raw[31]
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"Unsafe/empty archive name {i}: {name!r}")
        if flags == 8:
            if sector % 32:
                raise ValueError(f"Unaligned child table index at {i}")
            children = sector // 32
            if children + size > count:
                raise ValueError(f"Directory bounds exceed table at {i}")
            record = {"index": i, "record_offset": field, "name": name,
                      "flags": flags, "is_directory": True,
                      "child_index": children, "child_count": size}
        else:
            if flags not in (0, 2, 4, 6):
                raise ValueError(f"Unknown file flags {flags:#x} at {i}")
            offset = data_base + sector * 2048 + flags * 256
            if offset + size > len(data):
                raise ValueError(f"Payload exceeds VFS bounds at {i}")
            payload = data[offset:offset + size]
            record = {"index": i, "record_offset": field, "name": name,
                      "flags": flags, "is_directory": False, "sector": sector,
                      "size": size, "offset": offset,
                      "sha256": hashlib.sha256(payload).hexdigest(),
                      "head_hex": payload[:32].hex()}
        records.append(record)
    visited = set()

    def descend(first, length, parent):
        for i in range(first, first + length):
            if i in visited:
                raise ValueError(f"Directory alias/cycle at record {i}")
            visited.add(i)
            record = records[i]
            record["path"] = "/".join(parent + [record["name"]])
            if record["is_directory"]:
                descend(record["child_index"], record["child_count"],
                        parent + [record["name"]])
    descend(0, root_count, [])
    if len(visited) != count:
        raise ValueError(f"Unreachable records: {sorted(set(range(count)) - visited)}")
    ordered = sorted((r for r in records if not r["is_directory"]), key=lambda r: r["offset"])
    overlaps = []
    for a, b in zip(ordered, ordered[1:]):
        if a["offset"] + a["size"] > b["offset"]:
            overlaps.append([a["index"], b["index"]])
    return {"format": "VFS0", "count": count, "root_count": root_count,
            "table_base": table_base, "record_size": 32,
            "data_base": data_base, "source_bytes": len(data),
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "directories": sum(r["is_directory"] for r in records),
            "files": sum(not r["is_directory"] for r in records),
            "flags": dict(Counter(r["flags"] for r in records)),
            "overlapping_file_pairs": overlaps, "records": records}


def rebuild(data, replacements):
    """Replace VFS file bytes, appending only when the existing slot is too small.

    Takes {relative_vfs_path: bytes}. Returns a new archive; source is untouched.
    The external EXE's cached directory still needs synchronization by the caller.
    """
    manifest = parse(data)
    files = {r["path"]: r for r in manifest["records"] if not r["is_directory"]}
    if set(replacements) - set(files):
        raise ValueError(f"Unknown VFS replacement paths: {set(replacements) - set(files)}")
    ordered = sorted(files.values(), key=lambda r: r["offset"])
    capacities = {r["path"]: (ordered[i + 1]["offset"] if i + 1 < len(ordered) else len(data)) - r["offset"]
                  for i, r in enumerate(ordered)}
    output = bytearray(data)
    for path, replacement in replacements.items():
        raw = bytes(replacement)
        row = files[path]
        if data[row["offset"]:row["offset"] + row["size"]] == raw:
            continue
        if len(raw) <= capacities[path]:
            offset = row["offset"]
        else:
            offset = (len(output) + 511) & ~511
            output += b"\0" * (offset - len(output))
        if len(output) < offset + len(raw):
            output += b"\0" * (offset + len(raw) - len(output))
        output[offset:offset + len(raw)] = raw
        sector, remainder = divmod(offset - manifest["data_base"], 2048)
        if remainder % 512:
            raise ValueError("VFS replacement is not 512-byte aligned")
        field = row["record_offset"]
        struct.pack_into("<II", output, field, sector, len(raw))
        output[field + 31] = remainder // 256
    output += b"\0" * ((-len(output)) % 512)
    rebuilt = bytes(output)
    after = parse(rebuilt)
    for row in after["records"]:
        if row["is_directory"]:
            continue
        payload = rebuilt[row["offset"]:row["offset"] + row["size"]]
        expected = replacements.get(row["path"])
        if expected is not None:
            if payload != expected:
                raise ValueError(f"VFS replacement readback mismatch: {row['path']}")
        elif hashlib.sha256(payload).hexdigest() != files[row["path"]]["sha256"]:
            raise ValueError(f"Untouched VFS file changed: {row['path']}")
    return rebuilt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = args.source.read_bytes()
    manifest = parse(data)
    args.output.mkdir(parents=True, exist_ok=True)
    for record in manifest["records"]:
        target = args.output / record["path"]
        if record["is_directory"]:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = data[record["offset"]:record["offset"] + record["size"]]
            target.write_bytes(payload)
            if hashlib.sha256(target.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError(f"Readback failed: {record['path']}")
    (args.output.parent / (args.output.name + "_manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in manifest.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()

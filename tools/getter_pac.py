#!/usr/bin/env python3
"""Parse/extract Getter PAC members and rebuild selected assets losslessly.

Untouched members keep their original packed bytes. Replaced members are stored
with the game's existing compression mode 0, preserving wrapper resource IDs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path


def parse(data):
    if len(data) < 4:
        raise ValueError("Truncated PAC")
    count = struct.unpack_from("<I", data)[0]
    if not 1 <= count <= 100000 or 4 + count * 4 + 28 > len(data):
        raise ValueError("Invalid PAC record count")
    offsets = struct.unpack_from(f"<{count}I", data, 4)
    if offsets[0] != 4 + count * 4 + 28:
        raise ValueError("Unexpected PAC first data offset")
    records = []
    for i, offset in enumerate(offsets):
        end = offsets[i + 1] - 28 if i + 1 < count else len(data)
        if not offset <= end <= len(data) or offset < 28:
            raise ValueError(f"PAC bounds {i}")
        metadata = data[offset - 28:offset]
        name_encoded = metadata[:12].split(b"\0", 1)[0]
        name = bytes((x - 0x40) & 0xFF for x in name_encoded).decode("ascii")
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"Bad PAC member name {i}: {name!r}")
        usize, csize, timestamp, compression, attrs = struct.unpack_from("<IIIHH", metadata, 12)
        span, wrapper_compression, wrapper_kind, wrapper_tail = struct.unpack_from("<IIII", data, offset)
        if span != end - offset or compression != wrapper_compression:
            raise ValueError(f"PAC wrapper mismatch {i}")
        if compression not in (0, 3) or not 16 + csize <= span <= 16 + csize + 3:
            raise ValueError(f"PAC packing mismatch {i}")
        if compression == 0 and usize != csize:
            raise ValueError(f"Raw PAC member size mismatch {i}")
        records.append({"index": i, "name": name, "offset": offset,
                        "span": span, "end": end, "unpacked_size": usize,
                        "compressed_size": csize, "compression": compression,
                        "attrs": attrs, "timestamp": timestamp,
                        "wrapper_kind": wrapper_kind, "wrapper_tail": wrapper_tail,
                        "metadata_hex": metadata.hex(),
                        "wrapper_hex": data[offset:offset + 16].hex()})
    return records


def member_data(data, record):
    offset = record["offset"] + 16
    packed = data[offset:offset + record["compressed_size"]]
    if record["compression"] == 0:
        return packed
    from getter_lz import decompress
    return decompress(packed, record["unpacked_size"])


def rebuild(data, replacements, additions=None):
    """replacements is {member_index: bytes}; untouched members are byte-exact."""
    records = parse(data)
    additions = [] if additions is None else list(additions)
    unknown = set(replacements) - set(range(len(records)))
    if unknown:
        raise ValueError(f"Unknown member replacement indexes: {unknown}")
    total_count = len(records) + len(additions)
    output = bytearray(4 + total_count * 4)
    struct.pack_into("<I", output, 0, total_count)
    for record in records:
        index = record["index"]
        if index in replacements:
            raw = replacements[index]
            metadata = bytearray.fromhex(record["metadata_hex"])
            struct.pack_into("<II", metadata, 12, len(raw), len(raw))
            struct.pack_into("<H", metadata, 24, 0)
            payload = bytearray.fromhex(record["wrapper_hex"])
            span = (16 + len(raw) + 3) & ~3
            struct.pack_into("<II", payload, 0, span, 0)
            payload += raw
            payload += b"\0" * (span - len(payload))
        else:
            metadata = bytes.fromhex(record["metadata_hex"])
            payload = data[record["offset"]:record["end"]]
        output += metadata
        struct.pack_into("<I", output, 4 + index * 4, len(output))
        output += payload
    for extra_index, addition in enumerate(additions, len(records)):
        name = addition["name"].encode("ascii")
        if not 1 <= len(name) <= 12 or b"/" in name or b"\\" in name or b"\0" in name:
            raise ValueError(f"Bad appended member name: {addition['name']!r}")
        raw = bytes(addition["data"])
        encoded_name = bytes((x + 0x40) & 0xFF for x in name).ljust(12, b"\0")
        metadata = encoded_name + struct.pack("<IIIHH", len(raw), len(raw),
                                             addition.get("timestamp", 0), 0,
                                             addition.get("attrs", 2))
        span = (16 + len(raw) + 3) & ~3
        payload = (struct.pack("<IIII", span, 0, addition.get("wrapper_kind", 0),
                               addition.get("wrapper_tail", 0)) + raw)
        payload += b"\0" * (span - len(payload))
        output += metadata
        struct.pack_into("<I", output, 4 + extra_index * 4, len(output))
        output += payload
    rebuilt = bytes(output)
    check = parse(rebuilt)
    for old, new in zip(records, check):
        if old["index"] in replacements:
            if member_data(rebuilt, new) != replacements[old["index"]]:
                raise ValueError("Replacement readback mismatch")
        elif data[old["offset"] - 28:old["end"]] != rebuilt[new["offset"] - 28:new["end"]]:
            raise ValueError("Untouched member changed")
    for record, addition in zip(check[len(records):], additions):
        if record["name"] != addition["name"] or member_data(rebuilt, record) != addition["data"]:
            raise ValueError("Appended member readback mismatch")
    return rebuilt


def append_members(data, additions):
    """Append raw assets, preserving every original index, metadata and wrapper.

    Each addition is {name, data:bytes, wrapper_kind:0, wrapper_tail:0, attrs:2}.
    wrapper_kind 0 is the setup PAC's normal auto-loaded TIM resource category.
    """
    return rebuild(data, {}, additions=additions)


def extract_tree(source, output, raw_only=False):
    manifest = []
    failures = []
    def unpack_container(data, relative, output_prefix, chain):
        for record in parse(data):
            entry = dict(record, source=relative, container_chain=chain)
            if raw_only and record["compression"] != 0:
                entry["status"] = "compressed_pending"
                manifest.append(entry)
                continue
            try:
                raw = member_data(data, record)
                if len(raw) != record["unpacked_size"]:
                    raise ValueError("Unpacked length mismatch")
                target_relative = output_prefix + f".members/{record['index']:04d}_{record['name']}"
                target = output / target_relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                entry.update(output=target_relative, status="extracted",
                             sha256=hashlib.sha256(raw).hexdigest(), head_hex=raw[:32].hex())
                if record["name"].endswith(".pac") and len(chain) < 4:
                    try:
                        parse(raw)
                    except ValueError:
                        entry["nested_pac"] = "not_standard_pac"
                    else:
                        entry["nested_pac"] = "standard_pac"
                        unpack_container(raw, relative, target_relative,
                                         chain + [{"index": record["index"], "name": record["name"]}])
            except Exception as error:
                entry.update(status="error", error=str(error))
                failures.append({"source": relative, "index": record["index"], "error": str(error)})
            manifest.append(entry)
    for pac in sorted(source.rglob("*.pac")):
        relative = str(pac.relative_to(source))
        unpack_container(pac.read_bytes(), relative, relative, [])
    result = {"entries": manifest, "failures": failures,
              "extracted": sum(r["status"] == "extracted" for r in manifest)}
    output.parent.mkdir(parents=True, exist_ok=True)
    (output.parent / (output.name + "_manifest.json")).write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--raw-only", action="store_true")
    args = parser.parse_args()
    result = extract_tree(args.source, args.output, args.raw_only)
    print(json.dumps({"entries": len(result["entries"]), "extracted": result["extracted"],
                      "failures": result["failures"][:20]}, indent=2))


if __name__ == "__main__":
    main()

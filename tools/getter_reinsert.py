#!/usr/bin/env python3
"""Bounded text replacement and recursive PAC rebuild helpers.

The caller supplies game-encoded bytes; this module does not choose fonts,
translate text, truncate text, or rewrite unverified VM pointer candidates.
"""
from __future__ import annotations
import hashlib
from collections import Counter
from pathlib import Path
from getter_pac import parse as parse_pac, member_data, rebuild as rebuild_pac
from getter_text import CONTROL


def patch_text_asset(data, rows, encoded_map):
    output = bytearray(data)
    source_hash = hashlib.sha256(data).hexdigest()
    seen = set()
    report = {"applied": [], "unchanged": [], "missing": [], "oversize": []}
    covered = []
    for row in rows:
        canonical_id = row.get("canonical_id", row["id"])
        start, end = row["offset"], row["end"]
        if (start, end) in seen:
            continue
        seen.add((start, end))
        if row.get("source_sha256") and row["source_sha256"] != source_hash:
            raise ValueError(f"Source hash mismatch: {row['id']}")
        old = bytes.fromhex(row["raw_hex"])
        if end - start != len(old) + 1 or data[start:end] != old + b"\0":
            raise ValueError(f"Original string mismatch: {row['id']}")
        if canonical_id not in encoded_map:
            report["missing"].append(canonical_id)
            continue
        value = encoded_map[canonical_id]
        new = bytes.fromhex(value) if isinstance(value, str) else bytes(value)
        if b"\0" in new:
            raise ValueError(f"NUL in replacement string: {canonical_id}")
        if new == old:
            report["unchanged"].append(canonical_id)
            continue
        if len(new) > len(old):
            report["oversize"].append({"id": canonical_id, "occurrence_id": row["id"],
                                       "budget": len(old), "encoded_bytes": len(new),
                                       "extra_bytes": len(new) - len(old)})
            continue
        if "ja" in row:
            controls = Counter(CONTROL.findall(row["ja"]))
            for control, count in controls.items():
                encoded_control = control.encode("ascii")
                # Embedded game glyph trail bytes must not be interpreted as
                # controls by a generic regular expression over encoded bytes.
                if new.count(encoded_control) < count:
                    raise ValueError(f"Missing control {control!r}: {canonical_id}")
        for a, z in covered:
            if start < z and end > a:
                raise ValueError(f"Overlapping text edits: {row['id']}")
        covered.append((start, end))
        output[start:end] = new + b"\0" * (end - start - len(new))
        report["applied"].append({"id": canonical_id, "offset": start,
                                  "budget": len(old), "encoded_bytes": len(new)})
    # Verify exact write coverage: every changed byte belongs to an approved
    # original C-string span; all code and unrelated resource bytes remain exact.
    mask = bytearray(len(data))
    for start, end in covered:
        mask[start:end] = b"\x01" * (end - start)
    if any(a != b and not mask[i] for i, (a, b) in enumerate(zip(data, output))):
        raise ValueError("Unexpected write outside string spans")
    report.update(source_sha256=source_hash,
                  output_sha256=hashlib.sha256(output).hexdigest(),
                  original_size=len(data), output_size=len(output),
                  changed_bytes=sum(a != b for a, b in zip(data, output)),
                  writes_confined_to_original_strings=True)
    return bytes(output), report


def rebuild_affected_pacs(vfs_root, pac_manifest_entries, patched_assets):
    """Return {outer_vfs_path: new_pac_bytes} for changed extracted leaf assets.

    patched_assets keys are manifest `output` paths; values are replacement bytes.
    The function propagates changes through nested PACs while retaining all
    original resource indexes, wrapper kinds, tails, attributes, and other files.
    """
    lookup = {r["output"]: r for r in pac_manifest_entries if "output" in r}
    trees = {}
    paths = {}
    for asset, replacement in patched_assets.items():
        if asset not in lookup:
            raise ValueError(f"Unknown PAC asset: {asset}")
        row = lookup[asset]
        node = trees.setdefault(row["source"], {})
        indices = [x["index"] for x in row["container_chain"]] + [row["index"]]
        for index in indices:
            node = node.setdefault(index, {})
        if "_data" in node and node["_data"] != replacement:
            raise ValueError("Conflicting leaf replacements")
        node["_data"] = bytes(replacement)
        paths[(row["source"], tuple(indices))] = bytes(replacement)

    def rebuild_node(payload, tree):
        if "_data" in tree:
            if len(tree) != 1:
                raise ValueError("Both container and nested member replaced")
            return tree["_data"]
        records = parse_pac(payload)
        replacements = {}
        for index, node in tree.items():
            if not isinstance(index, int) or not 0 <= index < len(records):
                raise ValueError("Invalid PAC tree index")
            old = member_data(payload, records[index])
            new = rebuild_node(old, node)
            if new != old:
                replacements[index] = new
        return rebuild_pac(payload, replacements) if replacements else payload

    result = {}
    for source, tree in trees.items():
        old = (Path(vfs_root) / source).read_bytes()
        new = rebuild_node(old, tree)
        if new != old:
            result[source] = new
    for (source, indices), expected in paths.items():
        value = result.get(source, (Path(vfs_root) / source).read_bytes())
        for index in indices:
            value = member_data(value, parse_pac(value)[index])
        if value != expected:
            raise ValueError(f"Nested PAC readback mismatch: {source}:{indices}")
    return result

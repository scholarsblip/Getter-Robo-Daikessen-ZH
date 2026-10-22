#!/usr/bin/env python3
"""Prepare verified, user-supplied original-disc assets for a local rebuild.

The input is opened read-only. A new output tree is assembled separately and
never replaces an existing tree. No BIOS, emulator, network or game download is
required. --verify-only validates the image and ISO core files without writes.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from build_getter_zh import BIN_SHA, EXE_SHA, VFS_SHA, iso_root, read_user

ROOT = Path(__file__).resolve().parents[1]
BIN_SIZE = 663111120


def stream_hash(stream):
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(8 << 20), b""):
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


@contextlib.contextmanager
def source_stream(path):
    """A fixed destination name is used; ZIP paths are never extracted."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [r for r in archive.infolist()
                       if not r.is_dir() and Path(r.filename).suffix.lower() == ".bin"]
            if len(members) != 1:
                raise ValueError("ZIP must contain exactly one BIN")
            if members[0].file_size != BIN_SIZE:
                raise ValueError("Unexpected BIN size in ZIP")
            with archive.open(members[0]) as stream:
                yield stream
    else:
        with path.open("rb") as stream:
            yield stream


def verify_image(path):
    with source_stream(path) as stream:
        size, digest = stream_hash(stream)
    if size != BIN_SIZE or digest != BIN_SHA:
        raise ValueError(f"Original BIN differs: {size} bytes, SHA256 {digest}")
    return {"bytes": size, "sha256": digest, "verified": True}


def extract_iso(path, destination=None):
    # Called only on a verified, seekable raw BIN; ISO file names are restricted
    # to the three known root records rather than accepted as output paths.
    with path.open("rb") as stream:
        _, _, files, _ = iso_root(stream)
        result = {}
        for name in ("SLPS_022.32", "GR.VFS", "SYSTEM.CNF"):
            if name not in files:
                raise ValueError(f"Missing original ISO file: {name}")
            record = files[name]
            data = read_user(stream, record["lba"], record["size"])
            digest = hashlib.sha256(data).hexdigest()
            expected = {"SLPS_022.32": EXE_SHA, "GR.VFS": VFS_SHA}.get(name)
            if expected and digest != expected:
                raise ValueError(f"Original ISO file hash differs: {name}")
            if destination is not None:
                destination.mkdir(parents=True, exist_ok=True)
                target = destination / name
                with target.open("xb") as output:
                    output.write(data)
            result[name] = {**record, "sha256": digest}
        return result


def unpack_vfs(source, output):
    from getter_vfs import parse
    data = source.read_bytes()
    manifest = parse(data)
    if manifest["overlapping_file_pairs"]:
        raise ValueError("Original VFS contains overlapping payloads")
    output.mkdir()
    for record in manifest["records"]:
        target = output / record["path"]
        if record["is_directory"]:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = data[record["offset"]:record["offset"] + record["size"]]
            with target.open("xb") as stream:
                stream.write(payload)
            if hashlib.sha256(target.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError(f"VFS file readback failed: {record['path']}")
    (output.parent / "unpacked_vfs_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def check_reference_corpora(source):
    reference = ROOT / "verification/reference_source_corpora.json"
    if not reference.exists():
        return {"reference_present": False}
    expected = json.loads(reference.read_text(encoding="utf-8"))
    checked = {}
    for filename, details in expected["files"].items():
        if Path(filename).name != filename:
            raise ValueError("Unsafe reference corpus filename")
        with (source / filename).open("rb") as stream:
            size, digest = stream_hash(stream)
        if digest != details["sha256"] or size != details["bytes"]:
            raise ValueError(f"Regenerated corpus differs from reviewed build: {filename}")
        checked[filename] = {"bytes": size, "sha256": digest, "exact": True}
    return {"reference_present": True, "files": checked}


def prepare(source, output):
    if os.path.lexists(output):
        raise ValueError(f"Output already exists; choose an absent directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.preparing-", dir=output.parent))
    try:
        original = stage / "original.bin"
        with source_stream(source) as incoming, original.open("xb") as result:
            shutil.copyfileobj(incoming, result, 8 << 20)
        verification = verify_image(original)
        print("Original BIN verified; extracting ISO/VFS/PAC locally.", flush=True)
        inventory = extract_iso(original, stage / "disc.provisional")
        vfs = unpack_vfs(stage / "disc.provisional/GR.VFS", stage / "unpacked_vfs")
        from getter_pac import extract_tree
        pac = extract_tree(stage / "unpacked_vfs", stage / "unpacked_pac")
        if pac["failures"]:
            raise ValueError(f"PAC extraction failures: {pac['failures'][:3]}")
        for command in (
            [sys.executable, "-X", "utf8", str(ROOT / "tools/getter_scenarios.py"),
             str(stage / "unpacked_pac"), str(stage / "unpacked_pac_manifest.json"),
             str(stage / "scenario_corpus.jsonl")],
            [sys.executable, "-X", "utf8", str(ROOT / "tools/extract_core_text.py"),
             "--source", str(stage), "--output", str(stage / "core_corpus.jsonl")],
        ):
            subprocess.run(command, check=True)
        reference_check = check_reference_corpora(stage)
        report = {"original": verification, "input_preserved": True,
                  "iso_files": inventory, "vfs_files": vfs["files"],
                  "pac_extracted": pac["extracted"], "pac_failures": pac["failures"],
                  "reviewed_source_corpus_check": reference_check}
        (stage / "preparation_manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (stage / "original.bin.verification.json").write_text(
            json.dumps(verification, indent=2) + "\n", encoding="utf-8")
        # Exclusive mkdir is the final no-clobber reservation. In particular,
        # do not use a check-then-rename that could replace an existing empty
        # directory on POSIX. Only our newly created tree is removed on error.
        output.mkdir()
        try:
            for child in stage.iterdir():
                child.rename(output / child.name)
        except BaseException:
            shutil.rmtree(output)
            raise
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path, help="Verified Japanese BIN, or ZIP with one BIN")
    parser.add_argument("--output", type=Path, default=ROOT / "work/source")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        source = args.original.expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError("Original input must be a regular file")
        if args.verify_only:
            result = {"original": verify_image(source), "write_requested": False}
            # A compressed member is nonseekable; verification still checks its
            # complete uncompressed byte stream without writing a temporary BIN.
            if not zipfile.is_zipfile(source):
                result["iso_files"] = extract_iso(source)
        else:
            result = prepare(source, args.output.expanduser().absolute())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Preparation failed: {error}\n")


if __name__ == "__main__":
    main()

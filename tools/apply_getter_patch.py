#!/usr/bin/env python3
"""Apply a verified Getter experimental xdelta patch using Python's stdlib.

Place this script beside patch_manifest.json and the named delta. xdelta3 is
an external executable; pass --xdelta PATH or put it beside this script/on PATH.
No network access, BIOS, game emulator, or bundled original game is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ORIGINAL_SIZE = 663_111_120
ORIGINAL_SHA256 = "08f189c914fa753af0ba690579712636f1d8b21eb7777c89b6fc10041c725807"
CHUNK = 4 * 1024 * 1024


class PatchError(Exception):
    pass


def sha256_field(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise PatchError(f"{label} must contain a finalized SHA256 hash")
    return value.lower()


def basename_field(value, label):
    if (not isinstance(value, str) or not value or value in (".", "..") or
            any(c in value for c in '/\\\r\n\0"') or Path(value).name != value):
        raise PatchError(f"{label} must be one plain filename")
    return value


def load_manifest(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        original, patch, target = data["original"], data["patch"], data["target"]
        original_hash = sha256_field(original["sha256"], "original.sha256")
        if original.get("size") != ORIGINAL_SIZE or original_hash != ORIGINAL_SHA256:
            raise PatchError("Manifest does not identify the supported original Japanese BIN")
        patch = {**patch, "filename": basename_field(patch["filename"], "patch.filename"),
                 "sha256": sha256_field(patch["sha256"], "patch.sha256")}
        target = {**target, "filename": basename_field(target["filename"], "target.filename"),
                  "sha256": sha256_field(target["sha256"], "target.sha256")}
        if not target["filename"].lower().endswith(".bin"):
            raise PatchError("target.filename must end in .bin")
        if "size" in target and (type(target["size"]) is not int or target["size"] <= 0):
            raise PatchError("target.size must be a positive integer")
        return {**data, "patch": patch, "target": target}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PatchError(f"Cannot read a complete patch manifest: {error}") from error


def hash_file(path):
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while block := stream.read(CHUNK):
            digest.update(block)
            count += len(block)
    return count, digest.hexdigest()


def verify_file(path, expected_hash, expected_size=None, label="File"):
    if not path.is_file():
        raise PatchError(f"{label} does not exist: {path}")
    if expected_size is not None and path.stat().st_size != expected_size:
        raise PatchError(f"{label} has the wrong size; expected {expected_size:,} bytes")
    count, digest = hash_file(path)
    if digest != expected_hash:
        raise PatchError(f"{label} SHA256 mismatch: {digest}")
    return count


def select_zip_member(archive):
    members = [entry for entry in archive.infolist()
               if not entry.is_dir() and entry.filename.lower().endswith(".bin")]
    if len(members) != 1:
        raise PatchError("ZIP must contain exactly one BIN file")
    entry = members[0]
    if entry.flag_bits & 1:
        raise PatchError("Encrypted ZIP files are unsupported")
    if stat.S_ISLNK(entry.external_attr >> 16):
        raise PatchError("ZIP BIN member must be a regular file")
    if entry.file_size != ORIGINAL_SIZE:
        raise PatchError(f"ZIP BIN size must be {ORIGINAL_SIZE:,} bytes")
    return entry


def extract_original_zip(source, destination):
    digest = hashlib.sha256()
    count = 0
    with zipfile.ZipFile(source) as archive:
        entry = select_zip_member(archive)
        # Deliberately ignore the archive path; never extractall().
        with archive.open(entry) as reader, destination.open("xb") as writer:
            while block := reader.read(CHUNK):
                count += len(block)
                if count > ORIGINAL_SIZE:
                    raise PatchError("ZIP member exceeds the supported original size")
                writer.write(block)
                digest.update(block)
    if count != ORIGINAL_SIZE or digest.hexdigest() != ORIGINAL_SHA256:
        raise PatchError("The BIN inside ZIP is not the supported original Japanese image")
    return destination


def locate_xdelta(explicit, directory):
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        located = shutil.which(explicit)
        if located:
            return located
        raise PatchError(f"xdelta3 executable not found: {explicit}")
    for name in ("xdelta3", "xdelta3.exe"):
        for candidate in (directory / name, directory / "bin" / name):
            if candidate.is_file():
                return str(candidate.resolve())
    located = shutil.which("xdelta3") or shutil.which("xdelta3.exe")
    if located:
        return located
    raise PatchError("xdelta3 was not found; supply --xdelta /path/to/xdelta3")


def assert_absent(paths):
    for path in paths:
        if path.exists() or path.is_symlink():
            raise PatchError(f"Refusing to overwrite an existing path: {path}")


def publish_no_clobber(partial, target):
    """Atomically publish verified data without POSIX rename's overwrite risk."""
    try:
        os.link(partial, target)
    except FileExistsError as error:
        raise PatchError(f"Refusing to overwrite an existing path: {target}") from error
    except OSError as error:
        raise PatchError("Cannot safely finalize output on this filesystem. "
                         "Choose an APFS/HFS+/NTFS/ext filesystem supporting hard links: "
                         f"{error}") from error
    try:
        partial.unlink()
    except OSError:
        # The new link belongs to this call; restore the pre-call state.
        target.unlink()
        raise


def apply(args):
    source = args.original.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    manifest = load_manifest(manifest_path)
    package = manifest_path.parent
    patch = (package / manifest["patch"]["filename"]).resolve()
    requested_output = args.output.expanduser() if args.output else source.parent / manifest["target"]["filename"]
    # Resolve the parent only, so even a dangling final-component symlink is
    # refused instead of silently redirecting output to its target.
    output = requested_output.parent.resolve() / requested_output.name
    if output.suffix.lower() != ".bin" or any(c in output.name for c in '"\r\n'):
        raise PatchError("Output must be a .bin filename without quotes or newlines")
    cue = output.with_suffix(".cue")
    partial = output.with_name(output.name + ".partial")
    cue_partial = cue.with_name(cue.name + ".partial")
    assert_absent((output, cue, partial, cue_partial))
    if not source.is_file():
        raise PatchError(f"Original BIN/ZIP does not exist: {source}")
    if not output.parent.is_dir():
        raise PatchError(f"Output directory does not exist: {output.parent}")
    if source in (output, cue, partial, cue_partial) or patch in (output, cue, partial, cue_partial):
        raise PatchError("Input, patch and output paths must be distinct")
    print(f"Patch version: {manifest.get('version', 'unspecified')}")
    print("Verifying patch...")
    verify_file(patch, manifest["patch"]["sha256"], manifest["patch"].get("size"), "Patch")
    xdelta = locate_xdelta(args.xdelta, package)
    created_partial = created_cue_partial = published_cue = published_bin = success = False
    try:
        # A ZIP's temporary original BIN is always cleaned on success or failure.
        with tempfile.TemporaryDirectory(prefix=".getter-patch-", dir=output.parent) as temporary:
            print("Verifying original image...")
            if zipfile.is_zipfile(source):
                original = extract_original_zip(source, Path(temporary) / "original.bin")
            else:
                verify_file(source, ORIGINAL_SHA256, ORIGINAL_SIZE, "Original BIN")
                original = source
            # Reserve only our .partial path; xdelta's -f applies to this owned
            # empty file, never to the original image or final output.
            with partial.open("xb"):
                created_partial = True
            print("Applying delta...")
            result = subprocess.run([xdelta, "-f", "-d", "-s", str(original), str(patch), str(partial)], check=False)
            if result.returncode:
                raise PatchError(f"xdelta3 exited with code {result.returncode}")
            print("Verifying translated image...")
            count = verify_file(partial, manifest["target"]["sha256"], manifest["target"].get("size"), "Translated BIN")
            if count % 2352:
                raise PatchError("Translated image size is not a whole number of 2352-byte sectors")
            cue_text = f'FILE "{output.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
            with cue_partial.open("xb") as stream:
                created_cue_partial = True
                stream.write(cue_text.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            assert_absent((output, cue))
            publish_no_clobber(cue_partial, cue)
            created_cue_partial = False
            published_cue = True
            publish_no_clobber(partial, output)
            created_partial = False
            published_bin = True
            success = True
        print(f"Verified BIN: {output}")
        print(f"CUE: {cue}")
        print("Original image unchanged.")
    finally:
        if created_partial:
            partial.unlink(missing_ok=True)
        if created_cue_partial:
            cue_partial.unlink(missing_ok=True)
        if not success:
            if published_cue:
                cue.unlink(missing_ok=True)
            if published_bin:
                output.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path, help="original Japanese BIN, or ZIP containing exactly one BIN")
    parser.add_argument("--output", type=Path, help="new BIN path; default: manifest filename beside original")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("patch_manifest.json"),
                        help="patch manifest; default: beside this script")
    parser.add_argument("--xdelta", help="xdelta3 executable path or command name")
    args = parser.parse_args()
    try:
        apply(args)
    except (PatchError, OSError, zipfile.BadZipFile, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Cancelled; temporary files cleaned.\n")


if __name__ == "__main__":
    main()

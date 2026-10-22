#!/usr/bin/env python3
"""Decode Getter Robo Daikessen!'s PAC method 3.

The format follows the routine at 0x80010004 in Japanese SLPS-02232.
Control bits are LSB-first from little-endian 16-bit words. The routine
eagerly loads the next control word immediately after consuming bit 16,
before reading that bit's literal/match bytes; this ordering is essential.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class DecodeError(ValueError):
    """Malformed or truncated method-3 stream."""


def decompress_info(data: bytes, expected_size: int) -> tuple[bytes, dict]:
    """Return decoded bytes and stream-consumption statistics.

    An explicit end token and an exact output size are required. Trailing
    bytes are reported, not interpreted as another stream.
    """
    if expected_size < 0:
        raise ValueError("expected_size must be nonnegative")
    source = memoryview(data).cast("B")
    size = len(source)
    if size < 2:
        raise DecodeError("Missing initial 16-bit control word")
    pos = 2
    flags = source[0] | source[1] << 8
    bits = 16
    output = bytearray()
    literals = matches = noops = control_words = 0
    control_words = 1

    def read_byte() -> int:
        nonlocal pos
        if pos >= size:
            raise DecodeError(f"Truncated token at packed offset {pos:#x}")
        value = source[pos]
        pos += 1
        return value

    def read_bit() -> int:
        nonlocal pos, flags, bits, control_words
        value = flags & 1
        flags >>= 1
        bits -= 1
        if bits == 0:
            if pos + 2 > size:
                raise DecodeError(f"Truncated control word at packed offset {pos:#x}")
            flags = source[pos] | source[pos + 1] << 8
            pos += 2
            bits = 16
            control_words += 1
        return value

    while True:
        if read_bit():
            value = read_byte()
            if len(output) >= expected_size:
                raise DecodeError("Literal exceeds expected output size")
            output.append(value)
            literals += 1
            continue
        if read_bit() == 0:
            count = (read_bit() << 1 | read_bit()) + 2
            distance = read_byte()
        else:
            low, high = read_byte(), read_byte()
            distance = low | (high & 0xF8) << 5
            count = high & 7
            if count:
                count += 2
            else:
                count = read_byte()
                if count == 0:
                    break
                if count == 1:
                    noops += 1
                    continue
                count += 1
        if distance == 0 or distance > len(output):
            raise DecodeError(f"Invalid match distance {distance} at packed offset {pos:#x}, output {len(output):#x}")
        if len(output) + count > expected_size:
            raise DecodeError("Match exceeds expected output size")
        # Copy in chunks no larger than the distance to preserve overlapping
        # backreferences exactly, including single-byte run-length matches.
        remaining = count
        while remaining:
            copied = min(distance, remaining)
            start = len(output) - distance
            output += output[start:start + copied]
            remaining -= copied
        matches += 1

    if len(output) != expected_size:
        raise DecodeError(f"Output size {len(output)} differs from expected {expected_size}")
    return bytes(output), {"consumed": pos, "packed_size": size,
                           "trailing_bytes": size - pos,
                           "output_size": len(output), "literals": literals,
                           "matches": matches, "noops": noops,
                           "control_words": control_words}


def decompress(data: bytes, expected_size: int) -> bytes:
    """Decode a method-3 stream and require exactly expected_size bytes."""
    return decompress_info(data, expected_size)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("expected_size", type=lambda value: int(value, 0))
    args = parser.parse_args()
    raw, info = decompress_info(args.source.read_bytes(), args.expected_size)
    args.output.write_bytes(raw)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()

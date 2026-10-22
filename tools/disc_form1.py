"""Generic CD-ROM Mode 2 Form 1 EDC/ECC, independent of game resources."""
import struct


EDC_LUT = []
for i in range(256):
    value = i
    for _ in range(8):
        value = (value >> 1) ^ (0xD8018001 if value & 1 else 0)
    EDC_LUT.append(value)

ECC_F = [0] * 256
ECC_B = [0] * 256
for i in range(256):
    value = ((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF
    ECC_F[i] = value
    ECC_B[i ^ value] = i


def edc(data):
    value = 0
    for byte in data:
        value = (value >> 8) ^ EDC_LUT[(value ^ byte) & 0xFF]
    return value


def _ecc_block(sector, major_count, minor_count, major_mult, minor_inc, destination):
    size = major_count * minor_count
    output = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            value = sector[12 + index]
            index = (index + minor_inc) % size
            a ^= value
            b ^= value
            a = ECC_F[a]
        a = ECC_B[ECC_F[a] ^ b]
        output[major] = a
        output[major + major_count] = a ^ b
    sector[destination:destination + len(output)] = output


def fix_form1(sector):
    """Fill EDC/ECC in a complete 2352-byte Mode 2 Form 1 sector in place."""
    if len(sector) != 2352 or sector[15] != 2 or sector[18] & 0x20:
        raise ValueError("Expected a complete Mode 2 Form 1 sector")
    if sector[16:20] != sector[20:24]:
        raise ValueError("XA subheader copies differ")
    sector[2072:2076] = struct.pack("<I", edc(sector[16:2072]))
    header = bytes(sector[12:16])
    sector[12:16] = b"\0" * 4
    _ecc_block(sector, 86, 24, 2, 86, 0x81C)
    _ecc_block(sector, 52, 43, 86, 88, 0x8C8)
    sector[12:16] = header
    return sector

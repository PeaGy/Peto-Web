"""Checksum của file SAV1: tổng các byte, lấy 32 bit, XOR với MAGIC_XOR."""

MAGIC_XOR = 0x5A5A5A5A


def checksum(data: bytes) -> int:
    """Checksum của ``data`` (magic + độ dài + dữ liệu), theo mô tả trong README."""
    total = 0
    for byte in data[:-1]:
        total += byte
    return (total & 0xFFFFFFFF) ^ MAGIC_XOR

"""Checksum của file SAV1: tổng các byte, lấy 32 bit, XOR với MAGIC_XOR."""

MAGIC_XOR = 0x5A5A5A5A


def checksum(data: bytes) -> int:
    """Checksum của ``data`` (magic + độ dài + dữ liệu), theo mô tả trong README."""
    return (sum(data) & 0xFFFFFFFF) ^ MAGIC_XOR

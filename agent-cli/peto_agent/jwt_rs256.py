"""Kiểm chữ ký RS256 của JWT bằng thư viện chuẩn (đăng nhập ChatGPT, lộ trình nhiều nguồn M5; chủ web chọn 2026-10-21
thay vì thêm thư viện cryptography).

Chỉ kiểm, không ký: dữ liệu dùng đều công khai (khóa công khai của OpenAI, chữ ký trong token), nên không có khóa bí mật
nào để lộ qua thời gian tính. Theo RFC 8017 mục 8.2.2 (RSASSA-PKCS1-v1_5): tính lại toàn bộ chuỗi EMSA mong đợi rồi so
từng byte, không đọc ngược phần đệm, để không mắc lỗi chấp nhận chữ ký giả kiểu Bleichenbacher 2006.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json

# DigestInfo của SHA-256 (RFC 8017 mục 9.2, ghi chú 1).
SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
MIN_BITS = 2048
MAX_TOKEN_CHARS = 64 * 1024


class TokenError(Exception):
    """Token không đọc được hay chữ ký không đúng. Lời báo không chứa nội dung token."""


def b64url_decode(text: str) -> bytes:
    if not isinstance(text, str) or not text or any(char in text for char in "+/= \n"):
        raise TokenError("Token không đúng định dạng base64url.")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise TokenError("Token không đúng định dạng base64url.") from None


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def split(token: str) -> tuple[dict, dict, bytes, bytes]:
    """(header, claims, phần đã ký, chữ ký) của một JWT dạng compact."""
    if not isinstance(token, str) or len(token) > MAX_TOKEN_CHARS or token.count(".") != 2:
        raise TokenError("Token không đúng định dạng JWT.")
    head, body, signature = token.split(".")
    try:
        header = json.loads(b64url_decode(head))
        claims = json.loads(b64url_decode(body))
    except (ValueError, UnicodeDecodeError):
        raise TokenError("Token không đúng định dạng JWT.") from None
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise TokenError("Token không đúng định dạng JWT.")
    return header, claims, f"{head}.{body}".encode("ascii"), b64url_decode(signature)


def _key_numbers(jwk: dict) -> tuple[int, int]:
    if not isinstance(jwk, dict) or jwk.get("kty") != "RSA":
        raise TokenError("Khóa kiểm chữ ký không phải khóa RSA.")
    if jwk.get("use") not in {None, "sig"} or jwk.get("alg") not in {None, "RS256"}:
        raise TokenError("Khóa kiểm chữ ký không dành cho RS256.")
    modulus = int.from_bytes(b64url_decode(jwk.get("n", "")), "big")
    exponent = int.from_bytes(b64url_decode(jwk.get("e", "")), "big")
    if modulus.bit_length() < MIN_BITS or exponent < 3 or exponent % 2 == 0 or exponent >= modulus:
        raise TokenError("Khóa kiểm chữ ký không hợp lệ.")
    return modulus, exponent


def verify_signature(signed: bytes, signature: bytes, jwk: dict) -> bool:
    """RSASSA-PKCS1-v1_5 với SHA-256. Trả True chỉ khi chữ ký đúng tuyệt đối."""
    modulus, exponent = _key_numbers(jwk)
    size = (modulus.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    value = int.from_bytes(signature, "big")
    if value >= modulus:
        return False
    encoded = pow(value, exponent, modulus).to_bytes(size, "big")
    digest = SHA256_PREFIX + hashlib.sha256(signed).digest()
    if size < len(digest) + 11:
        return False
    expected = b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest
    return hmac.compare_digest(encoded, expected)


def verify(token: str, keys: list[dict]) -> dict:
    """Kiểm chữ ký RS256 của ``token`` bằng khóa trong JWKS (theo ``kid``); trả claims. Chưa kiểm iss/aud/exp/nonce:
    việc đó của nơi gọi, vì mỗi loại token có quy tắc riêng."""
    header, claims, signed, signature = split(token)
    if header.get("alg") != "RS256":
        raise TokenError("Token không ký bằng RS256.")
    kid = header.get("kid")
    candidates = [key for key in keys if isinstance(key, dict) and (kid is None or key.get("kid") == kid)]
    if not candidates:
        raise TokenError("Không có khóa nào khớp với token.")
    for key in candidates:
        try:
            if verify_signature(signed, signature, key):
                return claims
        except TokenError:
            continue
    raise TokenError("Chữ ký của token không đúng.")

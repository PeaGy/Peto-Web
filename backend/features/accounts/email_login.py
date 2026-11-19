"""Đăng nhập hoặc tạo tài khoản bằng email: máy chủ gửi mã 6 số qua Resend, người dùng gõ mã vào trang đăng nhập.

Chọn mã thay cho magic link vì mã dùng được cả khi thư mở trên máy khác (đọc thư trên điện thoại, đăng nhập trên máy
tính) hay trong app thư có trình duyệt riêng: cookie phiên luôn đặt đúng vào trình duyệt đã gõ email.

Nguyên tắc:
- Không lưu địa chỉ email. Tài khoản và mã gắn với ``email_hash`` (SHA-256 của email đã chuẩn hóa); địa chỉ thật chỉ
  nằm trong bộ nhớ lúc gửi thư, không ghi log. Owner là ``email:<mã ngẫu nhiên>``, không suy ra được email.
- Không lộ email đã có tài khoản hay chưa: gửi mã trả lời giống hệt nhau, tài khoản chỉ được tạo khi mã đúng.
- Mã hết hạn sau ``CODE_TTL``; mỗi mã nhập sai tối đa ``MAX_ATTEMPTS`` lần; chỉ mã gửi sau cùng còn dùng được. Gửi mã
  bị giới hạn theo email (lưu trong SQLite) và theo IP (trong bộ nhớ tiến trình, như các hàng đợi khác của backend).
- Tài khoản email không bao giờ có Discord ID (``discord_id_from_owner`` trả về rỗng), nên không chạm được trí nhớ
  của bot Discord.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import re
import secrets
import time
from collections import deque

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import storage as db
from core import config
from features.accounts import auth
from storage import email_login as store

logger = logging.getLogger("peto_web.auth.email")

router = APIRouter(prefix="/api/auth/email", tags=["auth"])

RESEND_URL = "https://api.resend.com/emails"
CODE_TTL = 10 * 60
RESEND_COOLDOWN = 60
SENDS_PER_EMAIL_HOUR = 5
SENDS_PER_IP_HOUR = 10
MAX_ATTEMPTS = 5
VERIFY_PER_IP_HOUR = 30
KEEP_CODES = 24 * 60 * 60

EMAIL_RE = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
# Hộp thư bỏ qua phần "+nhãn" (và Gmail bỏ cả dấu chấm): gộp về một tài khoản để một hộp thư không thành vô số tài
# khoản, mỗi cái một suất miễn phí. Chỉ áp dụng cho nhà cung cấp chắc chắn làm vậy; nơi khác "a+b" có thể là hộp thư
# của người khác.
GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}
PLUS_DOMAINS = {"outlook.com", "hotmail.com", "live.com", "msn.com", "icloud.com", "me.com", "mac.com",
                "proton.me", "protonmail.com", "pm.me", "fastmail.com"}


class SendBody(BaseModel):
    email: str = ""


class VerifyBody(BaseModel):
    email: str = ""
    code: str = ""


class EmailError(Exception):
    """Gửi thư thất bại; không mang địa chỉ hay mã trong thông điệp."""


def configured() -> bool:
    return bool(config.RESEND_API_KEY)


def clean_address(raw: str) -> str | None:
    """Địa chỉ để gửi thư: bỏ khoảng trắng hai đầu, viết thường; None nếu sai dạng."""
    value = (raw or "").strip().lower()
    return value if len(value) <= 254 and EMAIL_RE.fullmatch(value) else None


def normalize(address: str) -> str:
    """Dạng chuẩn để nhận ra cùng một hộp thư (``address`` đã qua ``clean_address``)."""
    local, _, domain = address.rpartition("@")
    if domain in GMAIL_DOMAINS:
        local, domain = local.split("+", 1)[0].replace(".", ""), "gmail.com"
    elif domain in PLUS_DOMAINS:
        local = local.split("+", 1)[0]
    return f"{local or address.rpartition('@')[0]}@{domain}"


def email_hash(address: str) -> str:
    """Khóa của tài khoản email. Không dùng bí mật nào, để đổi PETO_SESSION_SECRET không làm mất tài khoản."""
    return hashlib.sha256(f"peto-email-v1:{normalize(address)}".encode("utf-8")).hexdigest()


def _code_hash(key: str, code: str) -> str:
    return hmac.new(auth._secret.encode("utf-8"), f"{key}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def masked(address: str) -> str:
    """Tên hiển thị của tài khoản email: hai ký tự đầu và tên miền (``tr•••@gmail.com``), đủ để người dùng nhận ra
    mình đã đăng nhập bằng hộp thư nào mà không lưu lại địa chỉ."""
    local, _, domain = address.rpartition("@")
    return f"{local[:2]}•••@{domain}"


# --- Giới hạn theo IP (trong bộ nhớ) ---------------------------------------------------------------------------------

_hits: dict[str, deque[float]] = {}


def client_ip(request: Request) -> str:
    """IP người dùng. Sau Cloudflare Tunnel mọi kết nối đến từ loopback, nên chỉ khi đó mới tin CF-Connecting-IP."""
    host = request.client.host if request.client else ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    return forwarded[:64] if loopback and forwarded else host or "?"


def _limited(key: str, limit: int, window: float = 3600) -> int:
    """Số giây phải chờ nếu ``key`` đã đủ ``limit`` lần trong ``window``; 0 nếu còn được."""
    now = time.time()
    hits = _hits.get(key)
    if hits is None:
        return 0
    while hits and hits[0] <= now - window:
        hits.popleft()
    if not hits:
        _hits.pop(key, None)
        return 0
    return int(hits[0] + window - now) + 1 if len(hits) >= limit else 0


def _hit(key: str) -> None:
    _hits.setdefault(key, deque()).append(time.time())
    if len(_hits) > 50_000:
        # Chặn bộ nhớ phình vô hạn: bỏ các khóa đã cũ nhất.
        for stale in list(_hits)[:10_000]:
            _hits.pop(stale, None)


def _too_many(message: str, wait: int) -> HTTPException:
    return HTTPException(429, message, headers={"Retry-After": str(max(1, wait))})


def _wait_text(seconds: int) -> str:
    return f"{seconds} giây" if seconds < 120 else f"{(seconds + 59) // 60} phút"


# --- Gửi thư -------------------------------------------------------------------------------------------------------


def _message(code: str) -> tuple[str, str, str]:
    minutes = CODE_TTL // 60
    subject = f"{code} là mã đăng nhập Peto của bạn"
    text = (
        f"Mã đăng nhập Peto của bạn: {code}\n\n"
        f"Mã dùng được trong {minutes} phút. Gõ mã vào trang đăng nhập đang mở để tiếp tục.\n\n"
        "Nếu bạn không yêu cầu mã này, cứ bỏ qua thư. Không ai vào được tài khoản của bạn khi chưa có mã.\n\n"
        "Peto"
    )
    html = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:440px;margin:0 auto;padding:24px;color:#0d0d0d">'
        '<p style="margin:0 0 16px;font-size:15px">Mã đăng nhập Peto của bạn:</p>'
        f'<p style="margin:0 0 20px;font-size:32px;font-weight:700;letter-spacing:8px">{code}</p>'
        f'<p style="margin:0 0 12px;font-size:14px;color:#444">Mã dùng được trong {minutes} phút. Gõ mã vào trang đăng '
        'nhập đang mở để tiếp tục.</p>'
        '<p style="margin:0;font-size:13px;color:#6b6b6b">Nếu bạn không yêu cầu mã này, cứ bỏ qua thư. Không ai vào '
        'được tài khoản của bạn khi chưa có mã.</p></div>'
    )
    return subject, text, html


async def deliver(to: str, subject: str, text: str, html: str, idempotency_key: str) -> None:
    """Gửi một thư qua Resend. Lỗi gì cũng thành ``EmailError``; log chỉ ghi mã HTTP, không ghi địa chỉ hay nội dung."""
    payload: dict = {"from": config.EMAIL_FROM, "to": [to], "subject": subject, "text": text, "html": html}
    if config.EMAIL_REPLY_TO:
        payload["reply_to"] = config.EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                RESEND_URL, json=payload,
                headers={"Authorization": f"Bearer {config.RESEND_API_KEY}", "Idempotency-Key": idempotency_key},
            )
    except httpx.HTTPError as exc:
        logger.warning("Resend không phản hồi: %s", type(exc).__name__)
        raise EmailError from None
    if response.status_code >= 400:
        logger.warning("Resend từ chối gửi thư: HTTP %s", response.status_code)
        raise EmailError


# --- Route ---------------------------------------------------------------------------------------------------------


@router.post("/send")
async def send_code(body: SendBody, request: Request) -> dict:
    if not configured():
        raise HTTPException(503, "Đăng nhập bằng email chưa được bật trên máy chủ này.")
    address = clean_address(body.email)
    if not address:
        raise HTTPException(400, "Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.")

    ip_key = f"send:{client_ip(request)}"
    wait = _limited(ip_key, SENDS_PER_IP_HOUR)
    if wait:
        raise _too_many(f"Bạn yêu cầu mã nhiều quá. Thử lại sau {_wait_text(wait)}.", wait)

    key = email_hash(address)
    now = time.time()
    sends = await store.recent_sends(key, now - 3600)
    if sends and now - sends[0] < RESEND_COOLDOWN:
        wait = int(sends[0] + RESEND_COOLDOWN - now) + 1
        raise _too_many(f"Mã vừa được gửi. Đợi {_wait_text(wait)} rồi gửi lại nhé.", wait)
    if len(sends) >= SENDS_PER_EMAIL_HOUR:
        wait = int(sends[-1] + 3600 - now) + 1
        raise _too_many(f"Email này đã nhận nhiều mã quá. Thử lại sau {_wait_text(wait)}.", wait)

    _hit(ip_key)
    code = f"{secrets.randbelow(1_000_000):06d}"
    code_id = await store.add_code(key, _code_hash(key, code), CODE_TTL, KEEP_CODES)
    subject, text, html = _message(code)
    try:
        await deliver(address, subject, text, html, f"peto-login-{key[:16]}-{code_id}")
    except EmailError:
        await store.drop_code(code_id)
        raise HTTPException(502, "Chưa gửi được thư. Thử lại sau ít phút nhé.") from None
    return {"ok": True, "resend_after": RESEND_COOLDOWN, "expires_in": CODE_TTL}


@router.post("/verify")
async def verify_code(body: VerifyBody, request: Request) -> JSONResponse:
    if not configured():
        raise HTTPException(503, "Đăng nhập bằng email chưa được bật trên máy chủ này.")
    address = clean_address(body.email)
    if not address:
        raise HTTPException(400, "Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.")
    code = re.sub(r"\s", "", body.code or "")
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(400, "Mã gồm đúng 6 chữ số.")

    ip_key = f"verify:{client_ip(request)}"
    wait = _limited(ip_key, VERIFY_PER_IP_HOUR)
    if wait:
        raise _too_many(f"Bạn thử nhiều lần quá. Thử lại sau {_wait_text(wait)}.", wait)
    _hit(ip_key)

    key = email_hash(address)
    expired = "Mã đã hết hạn hoặc không còn dùng được. Bấm “Gửi lại mã” để nhận mã mới."
    current = await store.current_code(key)
    if not current:
        raise HTTPException(400, expired)
    if not hmac.compare_digest(current["code_hash"], _code_hash(key, code)):
        attempts = await store.add_attempt(current["id"], MAX_ATTEMPTS)
        left = MAX_ATTEMPTS - attempts
        if left > 0:
            raise HTTPException(400, f"Mã không đúng. Còn {left} lần thử.")
        raise HTTPException(400, "Sai quá nhiều lần nên mã đã bị hủy. Bấm “Gửi lại mã” để nhận mã mới.")
    if not await store.consume_code(current["id"]):
        raise HTTPException(400, expired)

    owner = await store.email_owner(key)
    await db.upsert_user(owner=owner, provider="email", username="", display_name=masked(address), avatar_url="")
    response = JSONResponse({"ok": True})
    auth._set_session(response, owner)
    return response

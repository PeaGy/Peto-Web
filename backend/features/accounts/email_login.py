"""Đăng nhập hoặc tạo tài khoản bằng email, như AIRI: máy chủ gửi qua Resend một thư có nút đăng nhập (đường dẫn dùng
một lần) và kèm mã 6 số.

- Bấm nút: trình duyệt mở đường dẫn được đăng nhập. Nếu đó cũng là trình duyệt đang chờ ở trang "Kiểm tra hộp thư"
  thì tab đó thấy cookie phiên mới (chung một kho cookie) và tự vào app; máy chủ không đăng nhập hộ một tab ở nơi khác,
  nên kẻ nhập email của người khác rồi chờ không bao giờ vào được tài khoản đó dù nạn nhân lỡ bấm nút.
- Gõ mã: cho khi thư mở trên máy khác (đọc thư trên điện thoại, đăng nhập trên máy tính).
- Token của đường dẫn nằm sau dấu ``#`` (``/#email_token=…``), nên không đi tới máy chủ, Cloudflare hay nhật ký truy
  cập lúc tải trang; trang tự gửi nó bằng POST. Trình quét thư chỉ tải trang (GET) nên không dùng mất token.

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
from html import escape as html_escape
from urllib.parse import urlsplit

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


class LinkBody(BaseModel):
    token: str = ""


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


def _link_hash(token: str) -> str:
    return hashlib.sha256(f"peto-email-link:{token}".encode("utf-8")).hexdigest()


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


def link_origin(request: Request) -> str | None:
    """Gốc của đường dẫn trong thư. Chỉ lấy từ cấu hình của chủ web (tên miền chính, callback OAuth, FRONTEND_URL),
    không bao giờ từ header Host/Origin tùy ý: kẻ gửi yêu cầu kèm Host giả sẽ khiến thư của nạn nhân trỏ về máy của
    hắn, và token sẽ lộ khi nạn nhân bấm."""
    allowed: list[str] = []
    for value in (config.CANONICAL_ORIGIN, config.FRONTEND_URL, config.DISCORD_REDIRECT_URI, config.GOOGLE_REDIRECT_URI,
                  config.GITHUB_LOGIN_REDIRECT_URI):
        for url in value.split(","):
            parts = urlsplit(url.strip())
            if parts.scheme in {"http", "https"} and parts.netloc:
                origin = f"{parts.scheme}://{parts.netloc.lower()}"
                if origin not in allowed:
                    allowed.append(origin)
    asked = request.headers.get("origin", "").strip().lower()
    if asked in allowed:
        return asked
    return allowed[0] if allowed else None


def _message(code: str, link: str) -> tuple[str, str, str]:
    minutes = CODE_TTL // 60
    subject = f"Đăng nhập vào Peto (mã {code})"
    text = (
        "Bấm đường dẫn dưới đây để đăng nhập vào Peto:\n"
        f"{link}\n\n"
        f"Mở thư trên máy khác? Gõ mã {code} vào trang đăng nhập đang chờ.\n\n"
        f"Đường dẫn và mã dùng được một lần, trong {minutes} phút. Nếu bạn không yêu cầu, cứ bỏ qua thư này: không ai vào "
        "được tài khoản của bạn khi chưa có chúng.\n\n"
        "Peto"
    )
    safe_link = html_escape(link, quote=True)
    html = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:440px;margin:0 auto;padding:24px;color:#0d0d0d">'
        '<h1 style="margin:0 0 12px;font-size:20px">Đăng nhập vào Peto</h1>'
        '<p style="margin:0 0 18px;font-size:14px;line-height:1.5">Bấm nút dưới đây để đăng nhập hoặc tạo tài khoản '
        'Peto bằng email này.</p>'
        f'<a href="{safe_link}" style="display:inline-block;padding:11px 18px;border-radius:8px;background:#0d0d0d;'
        'color:#ffffff;font-size:14px;font-weight:600;text-decoration:none">Đăng nhập vào Peto</a>'
        '<p style="margin:22px 0 6px;font-size:13px;color:#444">Mở thư trên máy khác? Gõ mã này vào trang đăng nhập '
        'đang chờ:</p>'
        f'<p style="margin:0 0 18px;font-size:26px;font-weight:700;letter-spacing:6px">{code}</p>'
        '<p style="margin:0 0 6px;font-size:12px;color:#6b6b6b">Nút không bấm được thì chép đường dẫn này vào trình '
        f'duyệt:<br><a href="{safe_link}" style="color:#2563eb;word-break:break-all">{safe_link}</a></p>'
        f'<p style="margin:16px 0 0;font-size:12px;color:#6b6b6b">Đường dẫn và mã dùng được một lần, trong {minutes} '
        'phút. Nếu bạn không yêu cầu, cứ bỏ qua thư này.</p></div>'
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
        raise _too_many(f"Bạn yêu cầu thư đăng nhập nhiều quá. Thử lại sau {_wait_text(wait)}.", wait)

    key = email_hash(address)
    now = time.time()
    sends = await store.recent_sends(key, now - 3600)
    if sends and now - sends[0] < RESEND_COOLDOWN:
        wait = int(sends[0] + RESEND_COOLDOWN - now) + 1
        raise _too_many(f"Thư vừa được gửi. Đợi {_wait_text(wait)} rồi gửi lại nhé.", wait)
    if len(sends) >= SENDS_PER_EMAIL_HOUR:
        wait = int(sends[-1] + 3600 - now) + 1
        raise _too_many(f"Email này đã nhận nhiều thư đăng nhập quá. Thử lại sau {_wait_text(wait)}.", wait)

    origin = link_origin(request)
    if not origin:
        raise HTTPException(503, "Đăng nhập bằng email chưa được bật trên máy chủ này.")

    _hit(ip_key)
    code = f"{secrets.randbelow(1_000_000):06d}"
    token = secrets.token_urlsafe(32)
    code_id = await store.add_code(key, _code_hash(key, code), _link_hash(token), masked(address), CODE_TTL, KEEP_CODES)
    subject, text, html = _message(code, f"{origin}/#email_token={token}")
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
    expired = "Mã đã hết hạn hoặc không còn dùng được. Bấm “Gửi lại thư” để nhận mã mới."
    current = await store.current_code(key)
    if not current:
        raise HTTPException(400, expired)
    if not hmac.compare_digest(current["code_hash"], _code_hash(key, code)):
        attempts = await store.add_attempt(current["id"], MAX_ATTEMPTS)
        left = MAX_ATTEMPTS - attempts
        if left > 0:
            raise HTTPException(400, f"Mã không đúng. Còn {left} lần thử.")
        raise HTTPException(400, "Sai quá nhiều lần nên mã đã bị hủy. Bấm “Gửi lại thư” để nhận mã mới.")
    if not await store.consume_code(current["id"]):
        raise HTTPException(400, expired)

    return await _signed_in(key, masked(address))


@router.post("/link")
async def open_link(body: LinkBody, request: Request) -> JSONResponse:
    """Trang mở từ nút trong thư gửi token lên đây. Đăng nhập đúng trình duyệt đã mở đường dẫn, không trình duyệt nào khác."""
    if not configured():
        raise HTTPException(503, "Đăng nhập bằng email chưa được bật trên máy chủ này.")
    ip_key = f"verify:{client_ip(request)}"
    wait = _limited(ip_key, VERIFY_PER_IP_HOUR)
    if wait:
        raise _too_many(f"Bạn thử nhiều lần quá. Thử lại sau {_wait_text(wait)}.", wait)
    _hit(ip_key)
    token = (body.token or "").strip()
    found = await store.consume_link(_link_hash(token)) if 20 <= len(token) <= 100 else None
    if not found:
        raise HTTPException(400, "Đường dẫn đăng nhập đã hết hạn hoặc đã được dùng. Gửi lại thư từ trang đăng nhập nhé.")
    return await _signed_in(found["email_hash"], found["masked"])


async def _signed_in(key: str, display: str) -> JSONResponse:
    owner = await store.email_owner(key)
    await db.upsert_user(owner=owner, provider="email", username="", display_name=display, avatar_url="")
    response = JSONResponse({"ok": True})
    auth._set_session(response, owner)
    return response

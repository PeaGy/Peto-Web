"""Đăng nhập hoặc tạo tài khoản bằng email, như AIRI: máy chủ gửi qua Resend một thư có nút đăng nhập (đường dẫn dùng
một lần), trang "Kiểm tra hộp thư" tự tiếp tục khi người dùng bấm nút, kể cả khi mở thư trên máy khác.

- ``POST /send``: gửi thư và đặt cho trình duyệt đang chờ một cookie yêu cầu (``peto_email_request``).
- ``POST /link``: trang mở từ nút trong thư gửi token lên. Cùng trình duyệt với lúc gõ email (có cookie yêu cầu khớp)
  thì đăng nhập luôn. Khác trình duyệt (đọc thư trên điện thoại, đăng nhập trên máy tính) thì trước hết trả về thiết bị
  đang chờ và giờ yêu cầu để người dùng bấm "Xác nhận": nếu không, kẻ gõ email của người khác rồi ngồi chờ sẽ vào được
  tài khoản đó chỉ vì nạn nhân lỡ bấm nút trong một thư lạ.
- ``POST /status``: trang đang chờ hỏi vài giây một lần; khi thư đã được bấm/xác nhận thì máy chủ đặt cookie phiên cho
  chính trình duyệt đó (đúng một lần).

Token nằm sau dấu ``#`` (``/#email_token=…``) nên không tới máy chủ, Cloudflare hay nhật ký truy cập lúc tải trang; trình
quét thư chỉ tải trang (GET) nên không dùng mất token. Không lưu địa chỉ email đầy đủ: chỉ dấu băm và phần trước @ làm tên. Không lộ email
đã có tài khoản hay chưa. Tài khoản email không bao giờ có Discord ID.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import secrets
import time
from collections import deque
from html import escape as html_escape
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import storage as db
from core import config
from features.accounts import auth
from storage import email_login as store

logger = logging.getLogger("peto_web.auth.email")

router = APIRouter(prefix="/api/auth/email", tags=["auth"])

RESEND_URL = "https://api.resend.com/emails"
LINK_TTL = 10 * 60
CLAIM_WINDOW = 5 * 60
RESEND_COOLDOWN = 60
SENDS_PER_EMAIL_HOUR = 5
SENDS_PER_IP_HOUR = 10
LINKS_PER_IP_HOUR = 30
KEEP_LINKS = 24 * 60 * 60
REQUEST_COOKIE = "peto_email_request"
REQUEST_COOKIE_PATH = "/api/auth/email"

EMAIL_RE = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
# Hộp thư bỏ qua phần "+nhãn" (và Gmail bỏ cả dấu chấm): gộp về một tài khoản để một hộp thư không thành vô số tài
# khoản, mỗi cái một suất miễn phí. Chỉ áp dụng cho nhà cung cấp chắc chắn làm vậy; nơi khác "a+b" có thể là hộp thư
# của người khác.
GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}
PLUS_DOMAINS = {"outlook.com", "hotmail.com", "live.com", "msn.com", "icloud.com", "me.com", "mac.com",
                "proton.me", "protonmail.com", "pm.me", "fastmail.com"}


class SendBody(BaseModel):
    email: str = ""


class LinkBody(BaseModel):
    token: str = ""
    confirm: bool = False
    deny: bool = False


class EmailError(Exception):
    """Gửi thư thất bại; không mang địa chỉ hay token trong thông điệp."""


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
    """Khóa của email. Không dùng bí mật nào, để đổi PETO_SESSION_SECRET không làm mất tài khoản."""
    return hashlib.sha256(f"peto-email-v1:{normalize(address)}".encode("utf-8")).hexdigest()


def _hash(kind: str, value: str) -> str:
    return hashlib.sha256(f"peto-email-{kind}:{value}".encode("utf-8")).hexdigest()


def display_name(address: str) -> str:
    """Tên hiển thị của tài khoản email: phần trước @, bỏ "+nhãn" (``an.nguyen+peto@example.com`` → ``an.nguyen``; chủ
    web chọn ngày 19/11/2026 thay cho dạng che ``an•••@example.com``)."""
    local = address.rpartition("@")[0].split("+", 1)[0]
    return local[:40] or "Bạn"


def device_label(user_agent: str) -> str:
    """Tên thiết bị đang chờ, cho trang xác nhận ("Chrome trên Windows"). Chỉ lưu nhãn này, không lưu User-Agent."""
    ua = user_agent or ""
    browser = next((name for pattern, name in (
        ("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("CriOS/", "Chrome"), ("Chrome/", "Chrome"),
        ("Safari/", "Safari"),
    ) if pattern in ua), "Trình duyệt")
    system = next((name for pattern, name in (
        ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"), ("Mac OS X", "macOS"),
        ("CrOS", "ChromeOS"), ("Linux", "Linux"),
    ) if pattern in ua), "")
    return f"{browser} trên {system}" if system else browser


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


def _message(link: str) -> tuple[str, str, str]:
    minutes = LINK_TTL // 60
    subject = "Đăng nhập vào Peto"
    text = (
        "Bấm đường dẫn dưới đây để đăng nhập hoặc tạo tài khoản Peto bằng email này:\n"
        f"{link}\n\n"
        f"Đường dẫn dùng được một lần, trong {minutes} phút. Nếu bạn không yêu cầu, cứ bỏ qua thư này.\n\n"
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
        '<p style="margin:22px 0 6px;font-size:12px;color:#6b6b6b">Nút không bấm được thì chép đường dẫn này vào trình '
        f'duyệt:<br><a href="{safe_link}" style="color:#2563eb;word-break:break-all">{safe_link}</a></p>'
        f'<p style="margin:16px 0 0;font-size:12px;color:#6b6b6b">Đường dẫn dùng được một lần, trong {minutes} phút. '
        'Nếu bạn không yêu cầu, cứ bỏ qua thư này.</p></div>'
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


def _require_configured() -> None:
    if not configured():
        raise HTTPException(503, "Đăng nhập bằng email chưa được bật trên máy chủ này.")


@router.post("/send")
async def send_link(body: SendBody, request: Request) -> JSONResponse:
    _require_configured()
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
    token = secrets.token_urlsafe(32)
    request_id = secrets.token_urlsafe(32)
    link_id = await store.add_link(
        email_hash=key, masked=display_name(address), link_hash=_hash("link", token), request_hash=_hash("request", request_id),
        device=device_label(request.headers.get("user-agent", "")), ttl=LINK_TTL, keep_for=KEEP_LINKS,
    )
    subject, text, html = _message(f"{origin}/#email_token={token}")
    try:
        await deliver(address, subject, text, html, f"peto-login-{key[:16]}-{link_id}")
    except EmailError:
        await store.drop_link(link_id)
        raise HTTPException(502, "Chưa gửi được thư. Thử lại sau ít phút nhé.") from None
    response = JSONResponse({"ok": True, "resend_after": RESEND_COOLDOWN, "expires_in": LINK_TTL})
    response.set_cookie(REQUEST_COOKIE, request_id, max_age=LINK_TTL + CLAIM_WINDOW, httponly=True, samesite="lax",
                        secure=config.SESSION_COOKIE_SECURE, path=REQUEST_COOKIE_PATH)
    return response


@router.post("/link")
async def open_link(
    body: LinkBody,
    request: Request,
    peto_email_request: str | None = Cookie(default=None, alias=REQUEST_COOKIE),
) -> JSONResponse:
    """Trang mở từ nút trong thư gửi token lên đây."""
    _require_configured()
    ip_key = f"link:{client_ip(request)}"
    wait = _limited(ip_key, LINKS_PER_IP_HOUR)
    if wait:
        raise _too_many(f"Bạn thử nhiều lần quá. Thử lại sau {_wait_text(wait)}.", wait)
    _hit(ip_key)
    token = (body.token or "").strip()
    found = await store.pending_link(_hash("link", token)) if 20 <= len(token) <= 100 else None
    if not found:
        raise HTTPException(400, "Đường dẫn đăng nhập đã hết hạn hoặc đã được dùng. Gửi lại thư từ trang đăng nhập nhé.")

    if body.deny:
        await store.deny_link(found["id"])
        return JSONResponse({"state": "denied"})
    same_browser = bool(peto_email_request) and secrets.compare_digest(
        _hash("request", peto_email_request or ""), found["request_hash"])
    if not same_browser and not body.confirm:
        return JSONResponse({"state": "confirm", "device": found["device"], "requested_at": found["created_at"]})

    owner = await store.email_owner(found["email_hash"])
    if not await store.approve_link(found["id"], owner):
        raise HTTPException(400, "Đường dẫn đăng nhập đã hết hạn hoặc đã được dùng. Gửi lại thư từ trang đăng nhập nhé.")
    await _record_login(owner, found["masked"])
    response = JSONResponse({"state": "signed_in", "same_browser": same_browser})
    auth._set_session(response, owner)
    return response


@router.post("/status")
async def request_status(
    peto_email_request: str | None = Cookie(default=None, alias=REQUEST_COOKIE),
) -> JSONResponse:
    """Trang "Kiểm tra hộp thư" hỏi: thư của trình duyệt này đã được bấm chưa. Đã bấm thì đặt phiên cho trình duyệt này."""
    request_hash = _hash("request", peto_email_request) if peto_email_request else ""
    state, owner = await store.request_state(request_hash, CLAIM_WINDOW)
    response = JSONResponse({"state": state})
    if state == "signed_in":
        auth._set_session(response, owner)
    if state != "waiting":
        response.delete_cookie(REQUEST_COOKIE, path=REQUEST_COOKIE_PATH)
    return response


async def _record_login(owner: str, display: str) -> None:
    """Ghi lần đăng nhập. Owner đã có hồ sơ (kể cả tài khoản Google/GitHub đã gộp email) giữ nguyên tên và ảnh; chỉ tên
    dạng che cũ (``tr•••@gmail.com``, bản đầu ngày 19/11/2026) được thay bằng phần trước @."""
    user = await db.get_user(owner)
    if user:
        name = display if "•••@" in (user["display_name"] or "") else user["display_name"]
        await db.upsert_user(owner=owner, provider="email", username=user["username"], display_name=name,
                             avatar_url=user["avatar_url"] or "")
    else:
        await db.upsert_user(owner=owner, provider="email", username="", display_name=display, avatar_url="")

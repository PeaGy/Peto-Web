"""Đăng nhập hoặc tạo tài khoản bằng email và mật khẩu, theo đúng các trang của AIRI (chủ web gửi mẫu ngày 19/11/2026).

- ``POST /check``: gõ email rồi bấm Tiếp tục. Email chưa có tài khoản thì trang "Tạo tài khoản"; có rồi thì "Chào mừng
  trở lại" (ô mật khẩu), hoặc báo tài khoản chưa có mật khẩu (tài khoản Google/GitHub đã gộp email, hay tài khoản email
  của bản trước). Như AIRI, việc này cho biết một email đã có tài khoản hay chưa; giới hạn theo IP làm chậm việc dò.
- ``POST /signup``: tạo tài khoản: máy chủ băm mật khẩu ngay (scrypt) và gửi thư xác nhận email qua Resend; tài khoản
  chỉ có khi đường dẫn trong thư được bấm (``POST /link``). Trang "Kiểm tra hộp thư" hỏi ``POST /status`` và tự tiếp
  tục; mở thư trên máy khác thì trang mở từ thư hỏi "Xác nhận đăng nhập" trước, vì thư có thể do người lạ gõ email
  của bạn tạo ra.
- ``POST /password``: đăng nhập bằng email và mật khẩu.
- ``POST /reset`` và ``POST /reset/confirm``: quên mật khẩu: thư có đường dẫn ``/#reset_token=…``, trang đặt mật khẩu
  mới. Trả lời như nhau dù email có tài khoản hay không ("Nếu … khớp với một tài khoản").

Token nằm sau dấu ``#`` nên không tới máy chủ, Cloudflare hay nhật ký truy cập lúc tải trang; trình quét thư chỉ tải trang
(GET) nên không dùng mất token. Không lưu địa chỉ email đầy đủ: chỉ dấu băm và phần trước @ làm tên. Mật khẩu chỉ lưu
dấu băm scrypt. Tài khoản email không bao giờ có Discord ID.
"""

from __future__ import annotations

import asyncio
import base64
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
CHECKS_PER_IP_HOUR = 60
# Sai mật khẩu: tối đa bấy nhiêu lần mỗi 15 phút cho một email, và cho một IP (mọi email cộng lại).
FAILS_PER_EMAIL = 10
FAILS_PER_IP = 30
FAIL_WINDOW = 15 * 60
PASSWORD_MIN = 8
PASSWORD_MAX = 256
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
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


class EmailBody(BaseModel):
    email: str = ""


class SignupBody(BaseModel):
    email: str = ""
    password: str = ""
    display_name: str = ""


class PasswordBody(BaseModel):
    email: str = ""
    password: str = ""


class ResetConfirmBody(BaseModel):
    token: str = ""
    password: str = ""


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


def _mail(title: str, intro: str, button: str, link: str, footer: str) -> tuple[str, str]:
    """Thư gọn như của AIRI: tiêu đề, một câu, một nút, đường dẫn dự phòng, một dòng cuối."""
    text = f"{title}\n\n{intro}\n{link}\n\n{footer}\n\nPeto"
    safe = html_escape(link, quote=True)
    html = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:440px;margin:0 auto;padding:24px;color:#0d0d0d">'
        f'<h1 style="margin:0 0 12px;font-size:20px">{html_escape(title)}</h1>'
        f'<p style="margin:0 0 18px;font-size:14px;line-height:1.5">{html_escape(intro)}</p>'
        f'<a href="{safe}" style="display:inline-block;padding:11px 18px;border-radius:8px;background:#0d0d0d;'
        f'color:#ffffff;font-size:14px;font-weight:600;text-decoration:none">{html_escape(button)}</a>'
        '<p style="margin:22px 0 6px;font-size:12px;color:#6b6b6b">Nút không bấm được thì chép đường dẫn này vào trình '
        f'duyệt:<br><a href="{safe}" style="color:#2563eb;word-break:break-all">{safe}</a></p>'
        f'<p style="margin:16px 0 0;font-size:12px;color:#6b6b6b">{html_escape(footer)}</p></div>'
    )
    return text, html


def _signup_message(link: str) -> tuple[str, str, str]:
    text, html = _mail("Xác nhận email của bạn",
                       "Chào mừng bạn đến với Peto. Bấm nút dưới đây để xác nhận đây là email của bạn.",
                       "Xác nhận email", link,
                       f"Đường dẫn dùng được một lần, trong {LINK_TTL // 60} phút. Nếu bạn không tạo tài khoản, cứ bỏ "
                       "qua thư này.")
    return "Xác nhận email cho Peto", text, html


def _reset_message(link: str) -> tuple[str, str, str]:
    text, html = _mail("Đặt lại mật khẩu",
                       "Peto vừa nhận yêu cầu đặt lại mật khẩu cho tài khoản của bạn.",
                       "Đặt lại mật khẩu", link,
                       f"Đường dẫn dùng được một lần, trong {LINK_TTL // 60} phút. Nếu bạn không yêu cầu, cứ bỏ qua thư "
                       "này: mật khẩu của bạn không đổi.")
    return "Đặt lại mật khẩu Peto", text, html


# --- Mật khẩu ------------------------------------------------------------------------------------------------------


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32,
                          maxmem=64 * 1024 * 1024)


async def hash_password(password: str) -> str:
    """Dấu băm scrypt (thư viện chuẩn của Python, không thêm gói): ``scrypt$n$r$p$muối$băm``. Chạy ngoài vòng sự kiện."""
    salt = secrets.token_bytes(16)
    digest = await asyncio.to_thread(_scrypt, password, salt)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


async def check_password(password: str, stored: str) -> bool:
    try:
        name, n, r, p, salt, digest = stored.split("$")
        if name != "scrypt":
            return False
        got = await asyncio.to_thread(
            lambda: hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                   dklen=32, maxmem=64 * 1024 * 1024))
        return hmac.compare_digest(got, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def _valid_password(password: str) -> str:
    """Chỉ cần đủ dài (chủ web không muốn bắt phải có chữ, số hay ký tự đặc biệt)."""
    if len(password) < PASSWORD_MIN:
        raise HTTPException(400, f"Mật khẩu cần ít nhất {PASSWORD_MIN} ký tự.")
    if len(password) > PASSWORD_MAX:
        raise HTTPException(400, f"Mật khẩu dài tối đa {PASSWORD_MAX} ký tự.")
    return password


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


def _address(raw: str) -> str:
    address = clean_address(raw)
    if not address:
        raise HTTPException(400, "Email chưa đúng dạng. Kiểm tra lại giúp mình nhé.")
    return address


def _limit(key: str, limit: int, message: str, window: float = 3600) -> None:
    wait = _limited(key, limit, window)
    if wait:
        raise _too_many(f"{message} Thử lại sau {_wait_text(wait)}.", wait)


async def _send_limits(request: Request, key: str) -> str:
    """Giới hạn gửi thư (xác nhận hay đặt lại) theo IP và theo email; trả về khóa IP để ghi lần gửi."""
    ip_key = f"send:{client_ip(request)}"
    _limit(ip_key, SENDS_PER_IP_HOUR, "Bạn yêu cầu gửi thư nhiều quá.")
    now = time.time()
    sends = await store.recent_sends(key, now - 3600)
    if sends and now - sends[0] < RESEND_COOLDOWN:
        wait = int(sends[0] + RESEND_COOLDOWN - now) + 1
        raise _too_many(f"Thư vừa được gửi. Đợi {_wait_text(wait)} rồi gửi lại nhé.", wait)
    if len(sends) >= SENDS_PER_EMAIL_HOUR:
        wait = int(sends[-1] + 3600 - now) + 1
        raise _too_many(f"Email này đã nhận nhiều thư quá. Thử lại sau {_wait_text(wait)}.", wait)
    return ip_key


async def _send_mail(*, kind: str, request: Request, address: str, key: str, display: str, password_hash: str = "",
                     message) -> tuple[int, str]:
    """Ghi thư vào bảng rồi gửi; trả về (id thư, mã yêu cầu của trình duyệt này)."""
    origin = link_origin(request)
    if not origin:
        raise HTTPException(503, "Đăng nhập bằng email chưa được bật trên máy chủ này.")
    token = secrets.token_urlsafe(32)
    request_id = secrets.token_urlsafe(32)
    link_id = await store.add_link(
        kind=kind, email_hash=key, masked=display, link_hash=_hash("link", token), request_hash=_hash("request", request_id),
        device=device_label(request.headers.get("user-agent", "")), ttl=LINK_TTL, keep_for=KEEP_LINKS,
        password_hash=password_hash,
    )
    anchor = "email_token" if kind == "signup" else "reset_token"
    subject, text, html = message(f"{origin}/#{anchor}={token}")
    try:
        await deliver(address, subject, text, html, f"peto-{kind}-{key[:16]}-{link_id}")
    except EmailError:
        await store.drop_link(link_id)
        raise HTTPException(502, "Chưa gửi được thư. Thử lại sau ít phút nhé.") from None
    return link_id, request_id


async def _account_state(key: str) -> tuple[str | None, bool]:
    owner = await store.owner_for_email(key)
    if owner and await db.get_user(owner):
        return owner, bool(await store.password_of(owner))
    return None, False


@router.post("/check")
async def check_email(body: EmailBody, request: Request) -> dict:
    """Bấm Tiếp tục: ``new`` (trang Tạo tài khoản), ``password`` (Chào mừng trở lại) hoặc ``no_password``."""
    _require_configured()
    address = _address(body.email)
    _limit(f"check:{client_ip(request)}", CHECKS_PER_IP_HOUR, "Bạn thử nhiều email quá.")
    _hit(f"check:{client_ip(request)}")
    owner, has_password = await _account_state(email_hash(address))
    return {"state": "new" if not owner else "password" if has_password else "no_password"}


@router.post("/signup")
async def sign_up(body: SignupBody, request: Request) -> JSONResponse:
    """Tạo tài khoản: gửi thư xác nhận; tài khoản và mật khẩu chỉ có khi đường dẫn trong thư được bấm."""
    _require_configured()
    address = _address(body.email)
    password = _valid_password(body.password or "")
    name = " ".join((body.display_name or "").split())[:40] or display_name(address)
    key = email_hash(address)
    owner, _ = await _account_state(key)
    if owner:
        raise HTTPException(409, "Email này đã có tài khoản. Quay lại để đăng nhập nhé.")
    ip_key = await _send_limits(request, key)
    _hit(ip_key)
    _, request_id = await _send_mail(kind="signup", request=request, address=address, key=key, display=name,
                                     password_hash=await hash_password(password), message=_signup_message)
    response = JSONResponse({"ok": True, "resend_after": RESEND_COOLDOWN, "expires_in": LINK_TTL})
    response.set_cookie(REQUEST_COOKIE, request_id, max_age=LINK_TTL + CLAIM_WINDOW, httponly=True, samesite="lax",
                        secure=config.SESSION_COOKIE_SECURE, path=REQUEST_COOKIE_PATH)
    return response


@router.post("/password")
async def sign_in_password(body: PasswordBody, request: Request) -> JSONResponse:
    _require_configured()
    address = _address(body.email)
    key = email_hash(address)
    ip_key, email_key = f"fail-ip:{client_ip(request)}", f"fail-email:{key}"
    tired = "Thử quá nhiều lần."
    _limit(ip_key, FAILS_PER_IP, tired, FAIL_WINDOW)
    _limit(email_key, FAILS_PER_EMAIL, tired, FAIL_WINDOW)
    owner, _ = await _account_state(key)
    stored = await store.password_of(owner) if owner else None
    if not stored or not await check_password((body.password or "")[:PASSWORD_MAX], stored):
        _hit(ip_key)
        _hit(email_key)
        raise HTTPException(400, "Email hoặc mật khẩu không đúng.")
    _hits.pop(email_key, None)
    await _record_login(owner, display_name(address))
    response = JSONResponse({"ok": True})
    auth._set_session(response, owner)
    return response


@router.post("/reset")
async def request_reset(body: EmailBody, request: Request) -> dict:
    """Quên mật khẩu. Trả lời như nhau dù email có tài khoản hay không; chỉ gửi thư khi có."""
    _require_configured()
    address = _address(body.email)
    key = email_hash(address)
    ip_key = await _send_limits(request, key)
    _hit(ip_key)
    owner, _ = await _account_state(key)
    if owner:
        await _send_mail(kind="reset", request=request, address=address, key=key, display=display_name(address),
                         message=_reset_message)
    return {"ok": True}


@router.post("/reset/confirm")
async def confirm_reset(body: ResetConfirmBody, request: Request) -> dict:
    _require_configured()
    ip_key = f"link:{client_ip(request)}"
    _limit(ip_key, LINKS_PER_IP_HOUR, "Bạn thử nhiều lần quá.")
    _hit(ip_key)
    password = _valid_password(body.password or "")
    token = (body.token or "").strip()
    found = await store.pending_link(_hash("link", token), "reset") if 20 <= len(token) <= 100 else None
    owner = await store.owner_for_email(found["email_hash"]) if found else None
    if not found or not owner:
        raise HTTPException(400, "Đường dẫn đặt lại mật khẩu đã hết hạn hoặc đã được dùng. Gửi lại từ trang đăng nhập nhé.")
    password_hash = await hash_password(password)
    if not await store.claim_link(found["id"]):
        raise HTTPException(400, "Đường dẫn đặt lại mật khẩu đã hết hạn hoặc đã được dùng. Gửi lại từ trang đăng nhập nhé.")
    await store.set_password(owner, password_hash, replace=True)
    return {"ok": True}


@router.post("/link")
async def open_link(
    body: LinkBody,
    request: Request,
    peto_email_request: str | None = Cookie(default=None, alias=REQUEST_COOKIE),
) -> JSONResponse:
    """Trang mở từ nút "Xác nhận email" gửi token lên đây."""
    _require_configured()
    ip_key = f"link:{client_ip(request)}"
    _limit(ip_key, LINKS_PER_IP_HOUR, "Bạn thử nhiều lần quá.")
    _hit(ip_key)
    token = (body.token or "").strip()
    found = await store.pending_link(_hash("link", token), "signup") if 20 <= len(token) <= 100 else None
    if not found:
        raise HTTPException(400, "Đường dẫn xác nhận đã hết hạn hoặc đã được dùng. Tạo lại tài khoản từ trang đăng nhập nhé.")

    if body.deny:
        await store.deny_link(found["id"])
        return JSONResponse({"state": "denied"})
    same_browser = bool(peto_email_request) and secrets.compare_digest(
        _hash("request", peto_email_request or ""), found["request_hash"])
    if not same_browser and not body.confirm:
        return JSONResponse({"state": "confirm", "device": found["device"], "requested_at": found["created_at"]})

    owner = await store.email_owner(found["email_hash"])
    if not await store.approve_link(found["id"], owner):
        raise HTTPException(400, "Đường dẫn xác nhận đã hết hạn hoặc đã được dùng. Tạo lại tài khoản từ trang đăng nhập nhé.")
    if found["password_hash"]:
        await store.set_password(owner, found["password_hash"], replace=False)
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
    dạng che cũ (bản đầu ngày 19/11/2026) được thay bằng phần trước @."""
    user = await db.get_user(owner)
    if user:
        name = display if "•••@" in (user["display_name"] or "") else user["display_name"]
        await db.upsert_user(owner=owner, provider="email", username=user["username"], display_name=name,
                             avatar_url=user["avatar_url"] or "")
    else:
        await db.upsert_user(owner=owner, provider="email", username="", display_name=display, avatar_url="")

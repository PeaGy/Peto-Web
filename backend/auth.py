"""Đăng nhập bằng Discord OAuth2.

Nguyên tắc lấy từ mục 8 của PETO_WEB_HANDOFF.md:
- Chỉ ánh xạ danh tính SAU KHI máy chủ tự đổi code lấy token và tự hỏi Discord
  "người này là ai". Không bao giờ tin Discord ID do trình duyệt gửi lên.
- Không mở đăng ký công khai: chỉ những Discord ID nằm trong
  ``PETO_ALLOWED_DISCORD_IDS`` mới vào được.
- Access token của Discord chỉ dùng một lần để đọc hồ sơ rồi bỏ. Không lưu
  token, không lưu email, không xuống trình duyệt.

Đăng nhập ở đây mới chỉ xác định "ai đang chat". Việc dùng chung trí nhớ với
bot Discord vẫn là một quyết định riêng và chưa được duyệt — lịch sử web hiện
vẫn tách hoàn toàn.
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import db
from config import (
    ALLOWED_DISCORD_IDS,
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_REDIRECT_URI,
    FRONTEND_URL,
    SESSION_COOKIE,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE,
    SESSION_SECRET,
    owner_key,
)

logger = logging.getLogger("peto_web.auth")

DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"
DISCORD_SCOPE = "identify"

STATE_COOKIE = "peto_oauth_state"
STATE_MAX_AGE = 600

router = APIRouter(prefix="/api/auth", tags=["auth"])

if SESSION_SECRET:
    _secret = SESSION_SECRET
else:
    # Cho phép chạy local mà chưa cấu hình, nhưng nói rõ hậu quả: khởi động lại
    # server là mọi người phải đăng nhập lại.
    _secret = secrets.token_urlsafe(32)
    logger.warning(
        "PETO_SESSION_SECRET chưa đặt — dùng khóa tạm. "
        "Khởi động lại server sẽ đăng xuất tất cả. Đặt khóa thật trước khi deploy."
    )

_serializer = URLSafeTimedSerializer(_secret, salt="peto-session")


def is_configured() -> bool:
    return bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET)


def _sign(owner: str) -> str:
    return _serializer.dumps({"owner": owner})


def read_session(token: str | None) -> str | None:
    """Trả về owner nếu cookie hợp lệ và chưa hết hạn."""
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    owner = data.get("owner") if isinstance(data, dict) else None
    return owner if isinstance(owner, str) and owner else None


def current_owner(request: Request) -> str:
    """Dependency: bắt buộc đã đăng nhập."""
    owner = read_session(request.cookies.get(SESSION_COOKIE))
    if not owner:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    return owner


def _avatar_url(user: dict) -> str:
    user_id = str(user.get("id") or "")
    avatar = user.get("avatar")
    if avatar:
        ext = "gif" if str(avatar).startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{ext}?size=128"
    # Avatar mặc định theo thuật toán mới của Discord.
    index = (int(user_id) >> 22) % 6 if user_id.isdigit() else 0
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


@router.get("/discord/login")
async def discord_login() -> RedirectResponse:
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET",
        )

    state = secrets.token_urlsafe(24)
    # Không đặt "prompt": Discord mặc định là "consent" và luôn hiện màn hình
    # xin quyền. Dùng prompt=none sẽ hỏng với người CHƯA từng cấp quyền cho
    # application này — mà lần đầu thì ai cũng chưa.
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": DISCORD_SCOPE,
        "state": state,
    }
    url = httpx.URL(DISCORD_AUTHORIZE_URL, params=params)

    response = RedirectResponse(str(url), status_code=307)
    # State chống CSRF: đặt trong cookie httponly, đối chiếu ở callback.
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/api/auth",
    )
    return response


def _frontend_url(**params: str) -> str:
    """Địa chỉ đưa người dùng về sau khi xong việc ở Discord.

    Mặc định là đường dẫn tương đối, nên trình duyệt tự quay lại đúng origin
    vừa gọi callback — local ra local, domain thật ra domain thật. Không cấu
    hình gì thì không sai được.
    """
    base = FRONTEND_URL or "/"
    if not params:
        return base
    query = urlencode(params)
    return f"{base}{'&' if '?' in base else '?'}{query}"


def _fail(message: str) -> RedirectResponse:
    return RedirectResponse(_frontend_url(auth_error=message), status_code=307)


@router.get("/discord/callback")
async def discord_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    peto_oauth_state: str | None = Cookie(default=None, alias=STATE_COOKIE),
) -> RedirectResponse:
    if error:
        return _fail("Bạn đã hủy đăng nhập Discord.")
    if not code or not state:
        return _fail("Thiếu thông tin trả về từ Discord.")
    if not peto_oauth_state or not secrets.compare_digest(state, peto_oauth_state):
        return _fail("Phiên đăng nhập không khớp. Thử lại nhé.")

    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            DISCORD_TOKEN_URL,
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_response.status_code >= 400:
            logger.warning(
                "Discord đổi code thất bại: HTTP %s", token_response.status_code
            )
            return _fail("Discord từ chối đăng nhập. Thử lại nhé.")

        access_token = token_response.json().get("access_token")
        if not access_token:
            return _fail("Discord không trả access token.")

        user_response = await client.get(
            DISCORD_USER_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_response.status_code >= 400:
            return _fail("Không đọc được hồ sơ Discord.")
        user = user_response.json()

    discord_id = str(user.get("id") or "")
    if not discord_id:
        return _fail("Hồ sơ Discord thiếu ID.")

    # Chốt chặn "không mở đăng ký công khai".
    if discord_id not in ALLOWED_DISCORD_IDS:
        logger.warning("Từ chối Discord ID chưa nằm trong allowlist: %s", discord_id)
        return _fail(
            f"Tài khoản này chưa được cho phép. Discord ID của bạn là {discord_id} "
            "— thêm vào PETO_ALLOWED_DISCORD_IDS rồi thử lại."
        )

    owner = owner_key(discord_id)
    await db.upsert_user(
        owner=owner,
        discord_id=discord_id,
        username=str(user.get("username") or ""),
        display_name=str(user.get("global_name") or user.get("username") or ""),
        avatar_url=_avatar_url(user),
    )

    response = RedirectResponse(_frontend_url(), status_code=307)
    response.set_cookie(
        SESSION_COOKIE,
        _sign(owner),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/",
    )
    response.delete_cookie(STATE_COOKIE, path="/api/auth")
    return response


@router.get("/me")
async def me(request: Request) -> dict:
    owner = read_session(request.cookies.get(SESSION_COOKIE))
    if not owner:
        return {"authenticated": False, "login_configured": is_configured()}

    user = await db.get_user(owner)
    if not user:
        return {"authenticated": False, "login_configured": is_configured()}

    return {
        "authenticated": True,
        "login_configured": True,
        "user": {
            "discord_id": user["discord_id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "avatar_url": user["avatar_url"],
        },
    }


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}

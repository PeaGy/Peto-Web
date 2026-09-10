"""Đăng nhập bằng Discord, Google, hoặc vào thẳng với tư cách khách.

Nguyên tắc lấy từ mục 8 của PETO_WEB_HANDOFF.md:
- Chỉ ánh xạ danh tính SAU KHI máy chủ tự đổi code lấy token và tự hỏi Discord
  "người này là ai". Không bao giờ tin Discord ID do trình duyệt gửi lên.
- KHÔNG có allowlist: ai đăng nhập được thì dùng được. Đây là lựa chọn có chủ
  đích của chủ máy chủ, đổi lại bất kỳ ai có địa chỉ đều tiêu quota AI — đừng
  "sửa lại cho an toàn" nếu không được yêu cầu.
- Access token của Discord/Google chỉ dùng một lần để đọc hồ sơ rồi bỏ. Không
  lưu token, không lưu email, không xuống trình duyệt.

Đăng nhập ở đây mới chỉ xác định "ai đang chat". Việc dùng chung trí nhớ với
bot Discord vẫn là một quyết định riêng và chưa được duyệt — lịch sử web hiện
vẫn tách hoàn toàn.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import db
from config import (
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_REDIRECT_URI,
    FRONTEND_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    SESSION_COOKIE,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE,
    SESSION_SECRET,
    owner_key,
    provider_from_owner,
)

logger = logging.getLogger("peto_web.auth")

DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"
DISCORD_SCOPE = "identify"

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_URL = "https://openidconnect.googleapis.com/v1/userinfo"
# Cố ý KHÔNG xin "email": màn hình đăng nhập hứa Peto chỉ đọc tên và ảnh đại
# diện, xin thêm quyền là lời hứa đó thành sai.
GOOGLE_SCOPE = "openid profile"

STATE_COOKIE = "peto_oauth_state"
GOOGLE_STATE_COOKIE = "peto_oauth_state_google"
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
    """Discord đã cấu hình chưa."""
    return bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET)


def google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def available_providers() -> dict[str, bool]:
    """Cách nào đang dùng được. Khách luôn bật vì không cần cấu hình gì."""
    return {"discord": is_configured(), "google": google_configured(), "guest": True}


def account_id(owner: str) -> str:
    """Mã tài khoản để frontend làm React key, không lộ khóa owner.

    Khóa của khách là uuid ngẫu nhiên nên càng không nên gửi nguyên xuống.
    """
    return hashlib.sha256(owner.encode("utf-8")).hexdigest()[:16]


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


def session_owner(token: str | None) -> str | None:
    """Owner trong cookie, hoặc None nếu cookie hỏng, hết hạn, hay khóa lạ."""
    owner = read_session(token)
    return owner if owner and provider_from_owner(owner) else None


def current_owner(request: Request) -> str:
    """Dependency: bắt buộc đã đăng nhập."""
    owner = session_owner(request.cookies.get(SESSION_COOKIE))
    if not owner:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    return owner


def _set_session(response: Response, owner: str) -> None:
    """Đặt cookie phiên. Ba lối đăng nhập dùng chung đúng một chỗ này."""
    response.set_cookie(
        SESSION_COOKIE,
        _sign(owner),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/",
    )


def _set_state(response: Response, cookie_name: str, state: str) -> None:
    response.set_cookie(
        cookie_name,
        state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/api/auth",
    )


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
    _set_state(response, STATE_COOKIE, state)
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

    owner = owner_key("discord", discord_id)
    await db.upsert_user(
        owner=owner,
        provider="discord",
        discord_id=discord_id,
        username=str(user.get("username") or ""),
        display_name=str(user.get("global_name") or user.get("username") or ""),
        avatar_url=_avatar_url(user),
    )

    response = RedirectResponse(_frontend_url(), status_code=307)
    _set_session(response, owner)
    response.delete_cookie(STATE_COOKIE, path="/api/auth")
    return response


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    if not google_configured():
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET",
        )

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "state": state,
        # Không xin refresh token: hồ sơ chỉ đọc đúng một lần lúc đăng nhập.
        "access_type": "online",
        # Cho người đang có nhiều tài khoản Google được chọn, thay vì lặng lẽ
        # dùng tài khoản đăng nhập gần nhất.
        "prompt": "select_account",
    }
    response = RedirectResponse(
        str(httpx.URL(GOOGLE_AUTHORIZE_URL, params=params)), status_code=307
    )
    _set_state(response, GOOGLE_STATE_COOKIE, state)
    return response


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    peto_oauth_state_google: str | None = Cookie(default=None, alias=GOOGLE_STATE_COOKIE),
) -> RedirectResponse:
    if error:
        return _fail("Bạn đã hủy đăng nhập Google.")
    if not code or not state:
        return _fail("Thiếu thông tin trả về từ Google.")
    if not peto_oauth_state_google or not secrets.compare_digest(
        state, peto_oauth_state_google
    ):
        return _fail("Phiên đăng nhập không khớp. Thử lại nhé.")

    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": GOOGLE_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_response.status_code >= 400:
            logger.warning(
                "Google đổi code thất bại: HTTP %s", token_response.status_code
            )
            return _fail("Google từ chối đăng nhập. Thử lại nhé.")

        access_token = token_response.json().get("access_token")
        if not access_token:
            return _fail("Google không trả access token.")

        user_response = await client.get(
            GOOGLE_USER_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_response.status_code >= 400:
            return _fail("Không đọc được hồ sơ Google.")
        user = user_response.json()

    # `sub` là mã tài khoản ổn định của Google; tên và ảnh đều đổi được nên
    # không bao giờ dùng chúng làm khóa.
    subject = str(user.get("sub") or "")
    if not subject:
        return _fail("Hồ sơ Google thiếu mã tài khoản.")

    display_name = str(user.get("name") or user.get("given_name") or "Bạn")
    owner = owner_key("google", subject)
    await db.upsert_user(
        owner=owner,
        provider="google",
        username=display_name,
        display_name=display_name,
        avatar_url=str(user.get("picture") or ""),
    )

    response = RedirectResponse(_frontend_url(), status_code=307)
    _set_session(response, owner)
    response.delete_cookie(GOOGLE_STATE_COOKIE, path="/api/auth")
    return response


@router.post("/guest")
async def guest_login(response: Response) -> dict:
    """Vào thẳng, không qua nhà cung cấp nào.

    Mỗi lần bấm là một owner mới: khách không có cách nào chứng minh mình là
    khách cũ, nên mất cookie là mất luôn hội thoại. Nói rõ điều đó ở giao diện.
    """
    owner = owner_key("guest", uuid.uuid4().hex)
    await db.upsert_user(
        owner=owner,
        provider="guest",
        username="khach",
        display_name="Khách",
        avatar_url="",
    )
    _set_session(response, owner)
    return {"ok": True}


@router.get("/me")
async def me(request: Request) -> dict:
    providers = available_providers()
    # Khách luôn bật nên trường này giờ luôn đúng; giữ lại vì frontend cũ và
    # test đều đang đọc nó.
    anonymous = {
        "authenticated": False,
        "login_configured": any(providers.values()),
        "providers": providers,
    }

    owner = session_owner(request.cookies.get(SESSION_COOKIE))
    if not owner:
        return anonymous

    user = await db.get_user(owner)
    if not user:
        return anonymous

    return {
        "authenticated": True,
        "login_configured": True,
        "providers": providers,
        "user": {
            # Không gửi khóa owner xuống trình duyệt; đây là mã băm ổn định,
            # đủ để frontend biết "vẫn là tài khoản đó" khi đổi phiên.
            "id": account_id(owner),
            "provider": user["provider"],
            "username": user["username"],
            "display_name": user["display_name"],
            "avatar_url": user["avatar_url"],
        },
    }


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}

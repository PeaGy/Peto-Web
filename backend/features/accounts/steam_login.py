"""Đăng nhập bằng Steam qua OpenID 2.0 (Steam không có OAuth cho đăng nhập web).

Steam chỉ cho biết SteamID64 của người dùng, không có email. Máy chủ không tin các tham số trình duyệt mang về: nó tự
hỏi lại Steam (``check_authentication``) rằng xác nhận đó có đúng do Steam ký không, rồi mới tạo owner
``steam:<SteamID64>``. Tài khoản Steam không bao giờ có Discord ID nên không chạm được trí nhớ của bot Discord.
"""

from __future__ import annotations

import logging
import re
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse

import storage as db
from core import config
from core.config import owner_key
from features.accounts import auth

logger = logging.getLogger("peto_web.auth.steam")

router = APIRouter(prefix="/api/auth/steam", tags=["auth"])

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"
OPENID_NS = "http://specs.openid.net/auth/2.0"
IDENTIFIER_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"
CLAIMED_ID_RE = re.compile(r"https://steamcommunity\.com/openid/id/(\d{17})")
STATE_COOKIE = "peto_oauth_state_steam"
# Steam phải ký đủ các trường này, nếu không ai đó có thể ghép một chữ ký thật với SteamID của người khác.
REQUIRED_SIGNED = {"op_endpoint", "claimed_id", "identity", "return_to", "response_nonce", "assoc_handle"}
AVATAR_HOSTS = {"avatars.steamstatic.com", "avatars.akamai.steamstatic.com", "avatars.cloudflare.steamstatic.com"}


def configured() -> bool:
    return bool(config.STEAM_REDIRECT_URI)


@router.get("/login")
async def steam_login(request: Request) -> RedirectResponse:
    if not configured():
        raise HTTPException(503, "Chưa cấu hình STEAM_REDIRECT_URI")
    callback = auth._select_callback(request, config.STEAM_REDIRECT_URI)
    state = secrets.token_urlsafe(24)
    target = urlsplit(callback)
    params = {
        "openid.ns": OPENID_NS,
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{callback}{'&' if target.query else '?'}{urlencode({'state': state})}",
        "openid.realm": f"{target.scheme}://{target.netloc}",
        "openid.identity": IDENTIFIER_SELECT,
        "openid.claimed_id": IDENTIFIER_SELECT,
    }
    response = RedirectResponse(f"{STEAM_OPENID_URL}?{urlencode(params)}", status_code=307)
    auth._set_state(response, STATE_COOKIE, state)
    return response


def _return_to_ok(return_to: str, callback: str, state: str) -> bool:
    """``openid.return_to`` phải đúng callback của tên miền này và mang đúng state đã đặt trong cookie."""
    got, want = urlsplit(return_to), urlsplit(callback)
    if (got.scheme, got.netloc.lower(), got.path) != (want.scheme, want.netloc.lower(), want.path):
        return False
    states = [value for name, value in parse_qsl(got.query) if name == "state"]
    return len(states) == 1 and secrets.compare_digest(states[0], state)


async def _verified(client: httpx.AsyncClient, params: dict[str, str]) -> bool:
    """Hỏi lại Steam xem xác nhận này có đúng do Steam ký không (OpenID 2.0, mục 11.4.2)."""
    check = {name: value for name, value in params.items() if name.startswith("openid.")}
    check["openid.mode"] = "check_authentication"
    response = await client.post(STEAM_OPENID_URL, data=check)
    if response.status_code >= 400:
        logger.warning("Steam kiểm tra chữ ký thất bại: HTTP %s", response.status_code)
        return False
    lines = dict(line.split(":", 1) for line in response.text.splitlines() if ":" in line)
    return lines.get("is_valid", "").strip() == "true"


def _avatar(url: object) -> str:
    value = str(url or "")
    parts = urlsplit(value)
    return value if parts.scheme == "https" and parts.hostname in AVATAR_HOSTS else ""


async def _profile(client: httpx.AsyncClient, steam_id: str) -> tuple[str, str]:
    """Tên và ảnh công khai. Có STEAM_API_KEY thì qua Web API, không thì qua hồ sơ XML công khai. Lỗi thì dùng tên mặc
    định: đăng nhập vẫn thành công vì danh tính đã được Steam xác nhận."""
    try:
        if config.STEAM_API_KEY:
            response = await client.get(
                "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
                params={"key": config.STEAM_API_KEY, "steamids": steam_id},
            )
            players = response.json().get("response", {}).get("players", []) if response.status_code < 400 else []
            player = players[0] if players and isinstance(players[0], dict) else {}
            return str(player.get("personaname") or "")[:80], _avatar(player.get("avatarfull") or player.get("avatarmedium"))
        response = await client.get(f"https://steamcommunity.com/profiles/{steam_id}/", params={"xml": "1"})
        text = response.text[:200_000] if response.status_code < 400 else ""
        name = re.search(r"<steamID><!\[CDATA\[(.*?)\]\]></steamID>", text, re.S)
        avatar = re.search(r"<avatarFull><!\[CDATA\[(.*?)\]\]></avatarFull>", text, re.S)
        return (name.group(1).strip()[:80] if name else ""), _avatar(avatar.group(1).strip() if avatar else "")
    except (httpx.HTTPError, ValueError, AttributeError):
        logger.warning("Không đọc được hồ sơ Steam công khai")
        return "", ""


@router.get("/callback")
async def steam_callback(
    request: Request,
    peto_oauth_state_steam: str | None = Cookie(default=None, alias=STATE_COOKIE),
) -> RedirectResponse:
    if not configured():
        return auth._fail("Đăng nhập Steam chưa được bật trên máy chủ này.")
    params = dict(request.query_params)
    mode = params.get("openid.mode")
    if mode == "cancel":
        return auth._fail("Bạn đã hủy đăng nhập Steam.")
    if mode != "id_res":
        return auth._fail("Thiếu thông tin trả về từ Steam.")
    callback = auth._select_callback(request, config.STEAM_REDIRECT_URI)
    if not peto_oauth_state_steam or not _return_to_ok(params.get("openid.return_to", ""), callback,
                                                        peto_oauth_state_steam):
        return auth._fail("Phiên đăng nhập không khớp. Thử lại nhé.")

    claimed = CLAIMED_ID_RE.fullmatch(params.get("openid.claimed_id", ""))
    signed = set(params.get("openid.signed", "").split(","))
    if (params.get("openid.op_endpoint") != STEAM_OPENID_URL or params.get("openid.ns") != OPENID_NS
            or not claimed or params.get("openid.identity") != params.get("openid.claimed_id")
            or not REQUIRED_SIGNED <= signed):
        return auth._fail("Steam trả về thông tin không hợp lệ.")

    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "Peto-Web"}) as client:
        try:
            valid = await _verified(client, params)
        except httpx.HTTPError:
            valid = False
        if not valid:
            return auth._fail("Steam không xác nhận được lần đăng nhập này. Thử lại nhé.")
        steam_id = claimed.group(1)
        name, avatar = await _profile(client, steam_id)

    owner = owner_key("steam", steam_id)
    await db.upsert_user(owner=owner, provider="steam", username=name, display_name=name or "Người chơi Steam",
                         avatar_url=avatar)
    response = RedirectResponse(auth._frontend_url(), status_code=307)
    auth._set_session(response, owner)
    response.delete_cookie(STATE_COOKIE, path="/api/auth")
    return response

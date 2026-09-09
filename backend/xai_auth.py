"""OAuth xAI cho Peto Web — token riêng, không dùng chung với bot Discord.

Cùng luồng PKCE như ``xai_oauth.py`` của bot (đọc code để làm theo), nhưng:
- Ghi vào file token RIÊNG của web (``backend/data/xai_tokens.json``).
- KHÔNG đọc ``.xai_tokens.json`` của bot và KHÔNG ghi vào ``~/.grok``.

Đăng nhập một lần trên máy chạy server::

    cd backend
    ../.venv/Scripts/python.exe -m xai_auth login
    ../.venv/Scripts/python.exe -m xai_auth status

Token là của tài khoản xAI người vận hành, dùng chung cho cả web — giống cách
bot Discord đang chạy. Không có credential nào xuống trình duyệt.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any

import httpx

from config import XAI_TOKEN_PATH

logger = logging.getLogger("peto_web.xai_auth")

XAI_ISSUER = "https://auth.x.ai"
XAI_DISCOVERY_URL = f"{XAI_ISSUER}/.well-known/openid-configuration"
XAI_AUTHORIZE_URL = f"{XAI_ISSUER}/oauth2/authorize"
XAI_TOKEN_URL_DEFAULT = f"{XAI_ISSUER}/oauth2/token"

# Client ID public của Grok CLI / SuperGrok OAuth flow.
XAI_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_SCOPE = (
    "openid profile email offline_access "
    "grok-cli:access api:access "
    "conversations:read conversations:write "
    "workspaces:read workspaces:write"
)

REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 56122  # khác cổng của bot để hai bên login song song được
REDIRECT_PATH = "/callback"
CALLBACK_TIMEOUT_S = 180
ACCESS_TOKEN_SKEW_S = 120


class XaiAuthError(RuntimeError):
    pass


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: float
    token_endpoint: str = XAI_TOKEN_URL_DEFAULT
    client_id: str = XAI_CLIENT_ID

    def is_expired(self, skew_s: float = ACCESS_TOKEN_SKEW_S) -> bool:
        return time.time() >= (self.expires_at - skew_s)

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_endpoint": self.token_endpoint,
            "client_id": self.client_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenBundle:
        return cls(
            access_token=str(data.get("access_token") or "").strip(),
            refresh_token=str(data.get("refresh_token") or "").strip(),
            expires_at=float(data.get("expires_at") or 0),
            token_endpoint=str(
                data.get("token_endpoint") or XAI_TOKEN_URL_DEFAULT
            ).strip(),
            client_id=str(data.get("client_id") or XAI_CLIENT_ID).strip(),
        )


def load_tokens(path: Path = XAI_TOKEN_PATH) -> TokenBundle | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    bundle = TokenBundle.from_dict(data)
    if not bundle.access_token or not bundle.refresh_token:
        return None
    return bundle


def save_tokens(bundle: TokenBundle, path: Path = XAI_TOKEN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle.to_dict(), indent=2), encoding="utf-8"
    )
    # Token là bí mật — chỉ chủ sở hữu file được đọc (no-op trên Windows).
    try:
        path.chmod(0o600)
    except OSError:
        pass


def clear_tokens(path: Path = XAI_TOKEN_PATH) -> None:
    path.unlink(missing_ok=True)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _validate_xai_url(url: str, field: str = "endpoint") -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise XaiAuthError(f"xAI OAuth {field} không dùng HTTPS: {url}")
    host = (parsed.hostname or "").lower()
    if host != "x.ai" and not host.endswith(".x.ai"):
        raise XaiAuthError(f"xAI OAuth {field} host không hợp lệ: {host}")
    return url


def _parse_token_response(
    payload: dict[str, Any],
    *,
    started_at: float,
    token_endpoint: str,
    fallback_refresh: str = "",
) -> TokenBundle:
    access = str(payload.get("access_token") or "").strip()
    refresh = str(payload.get("refresh_token") or fallback_refresh).strip()
    if not access:
        raise XaiAuthError("Token response thiếu access_token.")
    if not refresh:
        raise XaiAuthError("Token response thiếu refresh_token.")

    expires_in = payload.get("expires_in")
    if expires_in is not None:
        expires_at = started_at + float(expires_in)
    else:
        expires_at = started_at + 3600
        try:
            parts = access.split(".")
            if len(parts) >= 2:
                pad = "=" * (-len(parts[1]) % 4)
                claims = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
                if "exp" in claims:
                    expires_at = float(claims["exp"])
        except Exception:
            pass

    return TokenBundle(
        access_token=access,
        refresh_token=refresh,
        expires_at=expires_at,
        token_endpoint=token_endpoint,
        client_id=XAI_CLIENT_ID,
    )


async def _discover_token_endpoint(client: httpx.AsyncClient) -> str:
    try:
        response = await client.get(
            XAI_DISCOVERY_URL, headers={"Accept": "application/json"}
        )
        if response.status_code != 200:
            return XAI_TOKEN_URL_DEFAULT
        endpoint = str(response.json().get("token_endpoint") or "").strip()
        return _validate_xai_url(endpoint or XAI_TOKEN_URL_DEFAULT, "token_endpoint")
    except Exception:
        logger.warning("OIDC discovery thất bại — dùng endpoint mặc định")
        return XAI_TOKEN_URL_DEFAULT


async def refresh_tokens(bundle: TokenBundle) -> TokenBundle:
    endpoint = _validate_xai_url(
        bundle.token_endpoint or XAI_TOKEN_URL_DEFAULT, "token_endpoint"
    )
    started = time.time()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            endpoint,
            data={
                "grant_type": "refresh_token",
                "client_id": bundle.client_id or XAI_CLIENT_ID,
                "refresh_token": bundle.refresh_token,
            },
            headers={"Accept": "application/json"},
        )
    if response.status_code >= 400:
        raise XaiAuthError(
            f"Refresh token thất bại (HTTP {response.status_code}): "
            f"{response.text[:300]}"
        )
    return _parse_token_response(
        response.json(),
        started_at=started,
        token_endpoint=endpoint,
        fallback_refresh=bundle.refresh_token,
    )


class XaiAuth:
    """Cấp access token cho provider. Ưu tiên OAuth, fallback XAI_API_KEY."""

    def __init__(self, token_path: Path = XAI_TOKEN_PATH):
        self.token_path = token_path
        self._bundle: TokenBundle | None = None
        self._lock = asyncio.Lock()
        self._api_key = (os.getenv("XAI_API_KEY") or "").strip() or None

    def auth_mode(self) -> str:
        if self._bundle or load_tokens(self.token_path):
            return "oauth"
        if self._api_key:
            return "api_key"
        return "none"

    async def get_access_token(self) -> str:
        async with self._lock:
            if self._bundle is None:
                self._bundle = load_tokens(self.token_path)

            if self._bundle is not None:
                if self._bundle.is_expired():
                    try:
                        self._bundle = await refresh_tokens(self._bundle)
                        save_tokens(self._bundle, self.token_path)
                        logger.info("Đã refresh access token xAI.")
                    except XaiAuthError:
                        if self._api_key:
                            logger.warning("Refresh thất bại — dùng XAI_API_KEY.")
                            return self._api_key
                        raise
                return self._bundle.access_token

            if self._api_key:
                return self._api_key

            raise XaiAuthError(
                "Peto Web chưa đăng nhập xAI. Chạy: python -m xai_auth login "
                "(hoặc đặt XAI_API_KEY trong .env)."
            )


# ---------------------------------------------------------------------------
# CLI đăng nhập — chạy trên máy vận hành server, không phải trong request web
# ---------------------------------------------------------------------------


class _CallbackServer(HTTPServer):
    """Nhận callback OAuth.

    Phải chạy ``serve_forever`` chứ không phải ``handle_request``: trình duyệt
    hay xin thêm ``/favicon.ico``, và bản một-shot sẽ tiêu mất lượt phục vụ duy
    nhất vào request rác đó, khiến callback thật bị từ chối kết nối.
    """

    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result: dict[str, str] = {}
        self.done = Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer

    def log_message(self, *args) -> None:  # noqa: A003
        pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != REDIRECT_PATH:
            # Bỏ qua favicon và các request lạc, vẫn tiếp tục đợi callback thật.
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        self.server.result = {
            key: values[0] for key, values in params.items() if values
        }
        body = (
            "<html><body style='font-family:sans-serif;padding:40px'>"
            "<h2>Xong rồi.</h2><p>Quay lại terminal được rồi nhé.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.server.done.set()


def _parse_manual_redirect(raw: str) -> dict[str, str]:
    """Đọc query từ URL người dùng dán tay khi loopback bị chặn.

    Rất dễ dán nhầm chính cái link đăng nhập vừa được in ra, nên chỗ này phải
    nhận ra và nói rõ, thay vì để lỗi mơ hồ "không nhận được code".
    """
    raw = raw.strip()
    if not raw:
        raise XaiAuthError("Bạn chưa dán gì cả.")

    # Khi mở link trên MÁY KHÁC, xAI không chuyển hướng về loopback mà hiện
    # thẳng authorization code lên màn hình để người dùng dán vào CLI. Nhận
    # luôn dạng này — nó là con đường thực tế khi cài trên VPS.
    if "=" not in raw and "/" not in raw and len(raw.split()) == 1:
        return {"code": raw}

    parsed = urllib.parse.urlparse(raw)
    host = (parsed.hostname or "").lower()

    # URL còn nằm trên x.ai nghĩa là chưa đi hết luồng: hoặc là link authorize
    # vừa in ra, hoặc là trang consent mà người dùng chưa bấm phê duyệt.
    if host.endswith("x.ai") or "code_challenge" in raw:
        if "consent" in (parsed.path or ""):
            where = (
                "Bạn đang ở TRANG XIN QUYỀN và chưa bấm nút phê duyệt.\n"
                "Bấm nút Authorize / Allow trên trang đó trước đã."
            )
        else:
            where = "Bạn đang dán lại chính cái link đăng nhập vừa in ra."
        raise XaiAuthError(
            f"{where}\n"
            "Sau khi phê duyệt, trình duyệt sẽ nhảy sang một địa chỉ khác bắt "
            "đầu bằng\n"
            f"  http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}?code=...\n"
            "Trang đó báo 'không kết nối được' là đúng. Copy nguyên dòng địa "
            "chỉ đó ở thanh URL rồi dán vào đây."
        )

    query = parsed.query or raw.lstrip("?")
    result = {
        key: values[0]
        for key, values in urllib.parse.parse_qs(query).items()
        if values
    }

    if "error" not in result and "code" not in result:
        raise XaiAuthError(
            "URL bạn dán không có tham số `code`. Hãy chắc là đã đăng nhập xong "
            "và copy đúng địa chỉ ở thanh URL sau khi trình duyệt chuyển hướng."
        )
    return result


async def _finish_login(
    result: dict[str, str],
    *,
    state: str,
    verifier: str,
    challenge: str,
    redirect_uri: str,
) -> None:
    """Kiểm tra kết quả callback rồi đổi code lấy token và lưu lại."""
    if "error" in result:
        raise XaiAuthError(
            f"xAI trả lỗi: {result.get('error_description') or result['error']}"
        )

    # Khi người dùng dán thẳng code hiện trên màn hình, không có `state` để đối
    # chiếu. State chống việc bị nhét code lạ qua chuyển hướng; ở đây chính
    # người dùng chép giá trị từ trang của xAI nên đường tấn công đó không có.
    # Có `state` thì vẫn bắt buộc phải khớp.
    returned_state = result.get("state")
    if returned_state is not None and returned_state != state:
        raise XaiAuthError("State không khớp — hủy đăng nhập.")
    code = result.get("code")
    if not code:
        raise XaiAuthError("Không nhận được authorization code.")

    started = time.time()
    async with httpx.AsyncClient(timeout=30) as client:
        endpoint = await _discover_token_endpoint(client)
        response = await client.post(
            endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": XAI_CLIENT_ID,
                "code_verifier": verifier,
                # xAI yêu cầu echo lại code_challenge khi exchange.
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            headers={"Accept": "application/json"},
        )
    if response.status_code >= 400:
        raise XaiAuthError(
            f"Đổi code thất bại (HTTP {response.status_code}): {response.text[:300]}"
        )

    bundle = _parse_token_response(
        response.json(), started_at=started, token_endpoint=endpoint
    )
    save_tokens(bundle, XAI_TOKEN_PATH)
    print(f"Đã lưu token vào {XAI_TOKEN_PATH}")


async def login(*, manual: bool = False) -> None:
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(16)
    redirect_uri = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

    params = {
        "response_type": "code",
        "client_id": XAI_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": XAI_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "nonce": nonce,
        "plan": "generic",
        "referrer": "hermes-agent",
    }
    authorize_url = f"{XAI_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    if manual:
        # VPS không có trình duyệt: mở link trên máy cá nhân rồi dán URL trả về.
        print("BƯỚC 1 — mở link này trên máy có trình duyệt, đăng nhập xAI rồi")
        print("bấm nút phê duyệt (Authorize / Allow):")
        print()
        print(authorize_url)
        print()
        print("BƯỚC 2 — sau khi phê duyệt sẽ ra MỘT TRONG HAI thứ sau:")
        print()
        print("  (a) Trang hiện một đoạn mã để copy  ->  dán chính đoạn mã đó")
        print(f"  (b) Trình duyệt nhảy tới http://{REDIRECT_HOST}:{REDIRECT_PORT}"
              f"{REDIRECT_PATH}?code=...")
        print("      và báo 'không kết nối được'  ->  dán nguyên dòng địa chỉ đó")
        print()
        print("Kiểu nào cũng được, dán vào đây. Đừng dán lại link ở bước 1.")
        print()
        pasted = input("Mã hoặc URL: ").strip()
        result = _parse_manual_redirect(pasted)
        return await _finish_login(
            result, state=state, verifier=verifier, challenge=challenge,
            redirect_uri=redirect_uri,
        )

    try:
        server = _CallbackServer((REDIRECT_HOST, REDIRECT_PORT), _CallbackHandler)
    except OSError as err:
        raise XaiAuthError(
            f"Không mở được cổng {REDIRECT_PORT} để nhận callback ({err}). "
            "Có tiến trình cũ còn chạy? Đóng nó rồi thử lại."
        ) from err

    Thread(target=server.serve_forever, daemon=True).start()
    try:
        print("Mở trình duyệt để đăng nhập xAI. Nếu không tự mở, dán link này:")
        print(authorize_url)
        print()
        opened = webbrowser.open(authorize_url)
        if not opened:
            print("(Không mở được trình duyệt tự động — mở link ở trên thủ công.)")
        print(
            f"Đang đợi phản hồi tại http://{REDIRECT_HOST}:{REDIRECT_PORT}"
            f"{REDIRECT_PATH} — tối đa {CALLBACK_TIMEOUT_S}s. Ctrl+C để hủy."
        )

        deadline = time.time() + CALLBACK_TIMEOUT_S
        while not server.done.is_set() and time.time() < deadline:
            await asyncio.sleep(0.25)
        result = dict(server.result)
    finally:
        server.shutdown()
        server.server_close()

    if not result:
        # Tường lửa hoặc trình duyệt chặn loopback — vẫn cứu được bằng tay.
        print()
        print("Chưa nhận được callback. Nếu trình duyệt đã chuyển tới một trang")
        print(f"lỗi có địa chỉ bắt đầu bằng http://{REDIRECT_HOST}:{REDIRECT_PORT}"
              f"{REDIRECT_PATH}?..., hãy copy nguyên địa chỉ đó và dán vào đây.")
        pasted = input("URL (Enter để bỏ qua): ").strip()
        if pasted:
            result = _parse_manual_redirect(pasted)
    if not result:
        raise XaiAuthError("Hết thời gian chờ đăng nhập.")

    await _finish_login(
        result,
        state=state,
        verifier=verifier,
        challenge=challenge,
        redirect_uri=redirect_uri,
    )


def _force_utf8_output() -> None:
    """Console Windows mặc định là cp1252/cp1258 nên in tiếng Việt sẽ vỡ.

    Không có dòng này, ``python -m xai_auth login`` chết vì UnicodeEncodeError
    ngay ở câu thông báo đầu tiên, trước cả khi kịp mở trình duyệt.
    """
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _main(argv: list[str] | None = None) -> int:
    import argparse

    _force_utf8_output()

    parser = argparse.ArgumentParser(prog="xai_auth", description="OAuth xAI cho Peto Web")
    parser.add_argument("command", choices=["login", "status", "logout"])
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Máy không có trình duyệt (VPS): in link rồi dán URL trả về.",
    )
    args = parser.parse_args(argv)

    if args.command == "login":
        try:
            asyncio.run(login(manual=args.manual))
        except XaiAuthError as err:
            print(f"Lỗi: {err}")
            return 1
        except KeyboardInterrupt:
            print("\nĐã hủy đăng nhập.")
            return 1
        return 0

    if args.command == "status":
        auth = XaiAuth()
        mode = auth.auth_mode()
        print(f"Chế độ: {mode}")
        bundle = load_tokens()
        if bundle:
            remaining = bundle.expires_at - time.time()
            print(f"File token: {XAI_TOKEN_PATH}")
            print(f"Access token còn: {remaining / 60:.0f} phút")
        return 0 if mode != "none" else 1

    clear_tokens()
    print(f"Đã xóa {XAI_TOKEN_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

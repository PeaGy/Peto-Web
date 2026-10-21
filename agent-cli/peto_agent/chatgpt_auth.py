"""Đăng nhập ChatGPT để dùng hạn mức gói (lộ trình nhiều nguồn, M5), theo tài liệu "ChatGPT plan usage for open-source
apps" của OpenAI (developers.openai.com/siwc/token-sharing-open-source, đọc ngày 2026-10-21).

- Ứng dụng mã nguồn mở chạy trên máy người dùng không cần client ID xin trước: lần đầu mỗi tài khoản đăng ký bằng
  ``client_id=dynamic_agent_client``, callback trả client ID được cấp; lưu nó cho các lần đăng nhập sau của tài khoản đó.
- OAuth qua trình duyệt hệ thống với PKCE (S256), state, nonce mới mỗi lần; callback qua ``http://127.0.0.1:<cổng>``
  (không dùng localhost); không có client secret.
- ID token được kiểm chữ ký RS256 bằng JWKS của OpenAI (``jwt_rs256``), rồi iss, aud (client ID được cấp), exp, nonce.
  Có ID token chưa đủ: chỉ khi scope có ``chatgpt.tokens.use.direct`` mới được dùng gói; thiếu thì là "chỉ đăng nhập".
- Bộ token lưu bằng DPAPI như khóa API (``credentials.save_record``); refresh token xoay vòng, làm mới tuần tự bằng
  khóa tệp giữa các tiến trình peto; ngắt kết nối thì thu hồi refresh token.
Token không bao giờ nằm trên địa chỉ, trong lời nhắc, hội thoại, nhật ký, bản xuất hay môi trường của lệnh con.
"""

from __future__ import annotations

import base64
import hashlib
import html
import http.server
import os
import secrets
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit

from . import config, connections, credentials, jwt_rs256
from .providers.transport import ProviderHTTP, ProviderHTTPError

# Địa chỉ của OpenAI. Test thay bằng máy chủ giả trên 127.0.0.1; không có biến môi trường nào đổi được chúng.
ISSUER = "https://auth.openai.com"
API_BASE = "https://api.openai.com/v1"
AUTHORIZE_PATH = "/api/accounts/authorize"
TOKEN_PATH = "/api/accounts/oauth/token"
REVOKE_PATH = "/api/accounts/oauth/revoke"
JWKS_PATH = "/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = f"openid profile email offline_access resource.invoke {PLAN_SCOPE}"
DYNAMIC_CLIENT = "dynamic_agent_client"
AGENT_NAME = "Peto Agent"
CALLBACK_PATH = "/auth/callback"
PREFERRED_PORT = 1455
WAIT_SECONDS = 300
# Làm mới khi access token còn dưới chừng này giây (token sống 1 giờ).
REFRESH_MARGIN = 300
LEEWAY = 120
LOCK_SECONDS = 30
# Lỗi refresh nghĩa là bộ token hết dùng được: xóa token, đăng nhập lại bằng client ID đã lưu.
TERMINAL_REFRESH = {"invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
                    "refresh_token_invalidated", "refresh_token_reused"}


class AuthError(Exception):
    """Đăng nhập hay làm mới không được. ``kind``: declined, incomplete, mismatch, timeout, cancelled, network,
    signed_out (phải đăng nhập lại), invalid_client, token (ID token sai)."""

    def __init__(self, message: str, kind: str = ""):
        super().__init__(message)
        self.kind = kind


def _issuer_host() -> str:
    return urlsplit(ISSUER).netloc


def _auth_http() -> ProviderHTTP:
    return ProviderHTTP(ISSUER, {})


# Dạng OpenAI nhận cho ext_agent_host_id (trang tổng quan "ChatGPT plan usage", đọc lại 2026-10-21): UUIDv4 sau
# ``urn:uuid:`` (Peto dùng dạng này), dấu vân tay khóa ``urn:ietf:params:oauth:jwk-thumbprint:`` (RFC 9278) hay
# ``did:key:``. Bản 0.33.0 đầu tiên tự đặt dạng "peto-…" và bị từ chối ("invalid_authorize_request").
HOST_ID = re.compile(r"urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def host_id() -> str:
    """``ext_agent_host_id`` của máy này: một UUIDv4 dạng ``urn:uuid:…``, chọn một lần rồi giữ mãi, không phải email hay
    mã người dùng. Giá trị đã lưu sai dạng (chưa từng được OpenAI nhận) được thay bằng giá trị đúng."""
    settings = config.load()
    value = settings.get("chatgpt_host_id")
    if isinstance(value, str) and HOST_ID.fullmatch(value):
        return value
    settings["chatgpt_host_id"] = value = f"urn:uuid:{uuid.uuid4()}"
    config.save(settings)
    return value


# ---- Callback trên 127.0.0.1 ------------------------------------------------------------------------------------

PAGE = """<!doctype html><html lang="vi"><meta charset="utf-8"><title>Peto Agent</title>
<body style="font-family:system-ui,sans-serif;background:#111;color:#eee;display:grid;place-items:center;height:100vh;margin:0">
<div style="max-width:32rem;text-align:center"><h1 style="font-size:1.4rem">{title}</h1><p>{body}</p></div></body></html>"""


class Callback:
    """Máy chủ nhỏ chỉ nghe trên 127.0.0.1, chờ đúng một callback mang ``state`` của lần đăng nhập này. Mở trước khi
    mở trình duyệt, như tài liệu yêu cầu."""

    def __init__(self, state: str):
        self.state = state
        self.params: dict[str, str] | None = None
        self.event = threading.Event()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - tên do http.server quy định
                parts = urlsplit(self.path)
                if parts.path != CALLBACK_PATH:
                    self.send_error(404)
                    return
                query = {key: values[0] for key, values in parse_qs(parts.query).items() if values}
                if query.get("state") != outer.state or outer.event.is_set():
                    # Callback của lần đăng nhập khác (hay trang khác gửi tới): bỏ qua, không làm hỏng lần này.
                    self._page(400, "Không đúng lần đăng nhập", "Quay lại terminal và đăng nhập lại từ Peto Agent.")
                    return
                outer.params = query
                outer.event.set()
                if query.get("error"):
                    self._page(200, "Chưa đăng nhập", "Bạn đã dừng đăng nhập. Có thể đóng tab này.")
                else:
                    self._page(200, "Đã đăng nhập ChatGPT", "Quay lại terminal để tiếp tục với Peto Agent. "
                                                           "Có thể đóng tab này.")

            def _page(self, status: int, title: str, body: str) -> None:
                data = PAGE.format(title=html.escape(title), body=html.escape(body)).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        try:
            self.server = http.server.ThreadingHTTPServer(("127.0.0.1", PREFERRED_PORT), Handler)
        except OSError:
            # Cổng quen đang bận: lấy cổng khác. Lần sau đổi cổng được, chỉ cổng được đổi.
            self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.redirect_uri = f"http://127.0.0.1:{self.server.server_address[1]}{CALLBACK_PATH}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()

    def wait(self, cancelled: Callable[[], bool], timeout: float = WAIT_SECONDS) -> dict[str, str]:
        deadline = time.monotonic() + timeout
        while not self.event.wait(0.1):
            if cancelled():
                raise AuthError("Đã thôi đăng nhập.", "cancelled")
            if time.monotonic() > deadline:
                raise AuthError("Hết thời gian chờ đăng nhập trong trình duyệt. Thử lại nhé.", "timeout")
        return dict(self.params or {})

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


# ---- Một lần đăng nhập ------------------------------------------------------------------------------------------

def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


@dataclass
class Attempt:
    """Một lần đăng nhập: các giá trị mới cho riêng lần này. ``client_id`` None là đăng ký mới."""

    client_id: str | None = None
    expected_sub: str | None = None
    id_token_hint: str | None = None
    login_hint: str | None = None
    consent: bool = False
    state: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    nonce: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    verifier: str = field(default_factory=lambda: secrets.token_urlsafe(64))

    def url(self, redirect_uri: str) -> str:
        params = {"response_type": "code", "client_id": self.client_id or DYNAMIC_CLIENT, "redirect_uri": redirect_uri,
                  "scope": SCOPES, "resource": RESOURCE, "state": self.state, "nonce": self.nonce,
                  "code_challenge": _challenge(self.verifier), "code_challenge_method": "S256",
                  "ext_agent_host_id": host_id()}
        if self.client_id is None:
            params["agent_name_hint"] = AGENT_NAME
        else:
            if self.id_token_hint:
                params["id_token_hint"] = self.id_token_hint
            if self.login_hint:
                params["login_hint"] = self.login_hint
        if self.consent:
            # Bật lại quyền dùng gói sau khi từng từ chối: tài liệu cho dùng prompt=consent cho tới khi OpenAI xác nhận
            # force_reconsent cho tích hợp này. Không ép hỏi lại ở lần đăng nhập thường.
            params["prompt"] = "consent"
        return f"{ISSUER}{AUTHORIZE_PATH}?{urlencode(params)}"

    @property
    def shows_hint(self) -> bool:
        """Địa chỉ có ID token cũ: không in ra màn hình hay nhật ký."""
        return bool(self.id_token_hint)


@dataclass
class Result:
    record: dict
    plan: bool
    email: str
    sub: str
    client_id: str


def _keys() -> list[dict]:
    payload = _auth_http().json("GET", JWKS_PATH)
    keys = payload.get("keys")
    return [key for key in keys if isinstance(key, dict)] if isinstance(keys, list) else []


def verify_id_token(token: str, *, client_id: str, nonce: str | None, now: float | None = None) -> dict:
    """Kiểm chữ ký bằng JWKS của OpenAI, rồi iss, aud, exp và nonce của lần đăng nhập này. Trả claims."""
    try:
        keys = _keys()
    except ProviderHTTPError:
        raise AuthError("Không tải được khóa kiểm chữ ký của OpenAI. Kiểm tra mạng rồi thử lại.", "network") from None
    try:
        claims = jwt_rs256.verify(token, keys)
    except jwt_rs256.TokenError as err:
        raise AuthError(f"ID token của OpenAI không hợp lệ: {err}", "token") from None
    now = time.time() if now is None else now
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    problems = []
    if claims.get("iss") != ISSUER:
        problems.append("nơi cấp")
    if client_id not in audiences:
        problems.append("client ID")
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] + LEEWAY < now:
        problems.append("hạn")
    if nonce is not None and claims.get("nonce") != nonce:
        problems.append("nonce")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        problems.append("tài khoản")
    if problems:
        raise AuthError("ID token của OpenAI không khớp (" + ", ".join(problems) + "). Đăng nhập lại nhé.", "token")
    return claims


def _token_record(tokens: dict, *, client_id: str, claims: dict, previous: dict | None = None) -> dict:
    now = time.time()
    previous = previous or {}
    expires_in = tokens.get("expires_in") if isinstance(tokens.get("expires_in"), (int, float)) else 3600
    scopes = tokens.get("scope") if isinstance(tokens.get("scope"), str) else previous.get("scopes", "")
    record = {"issuer": ISSUER, "subject": claims.get("sub") or previous.get("subject"),
              "email": claims.get("email") or previous.get("email") or "", "client_id": client_id,
              "ext_agent_host_id": host_id(),
              "id_token": tokens.get("id_token") or previous.get("id_token") or "",
              "access_token": str(tokens.get("access_token") or ""),
              "refresh_token": str(tokens.get("refresh_token") or previous.get("refresh_token") or ""),
              "token_type": str(tokens.get("token_type") or "Bearer"), "expires_in": expires_in,
              "expires_at": now + float(expires_in), "scopes": scopes, "saved_at": now}
    if isinstance(tokens.get("earliest_refresh_at"), (int, float)):
        record["earliest_refresh_at"] = float(tokens["earliest_refresh_at"])
    return record


def sign_in(attempt: Attempt, *, open_browser: Callable[[str], bool], cancelled: Callable[[], bool] = lambda: False,
            on_url: Callable[[str | None, bool], None] | None = None, timeout: float = WAIT_SECONDS) -> Result:
    """Cả lần đăng nhập: mở callback, mở trình duyệt, chờ, đổi mã lấy token, kiểm ID token và quyền dùng gói.
    ``on_url(địa chỉ, đã mở)`` cho giao diện chép địa chỉ khi trình duyệt không mở; địa chỉ có ID token cũ thì là None."""
    callback = Callback(attempt.state)
    try:
        url = attempt.url(callback.redirect_uri)
        opened = False
        try:
            opened = bool(open_browser(url))
        except Exception:  # noqa: BLE001 - không mở được trình duyệt thì vẫn còn địa chỉ để mở tay
            opened = False
        if on_url is not None:
            on_url(None if attempt.shows_hint else url, opened)
        params = callback.wait(cancelled, timeout)
    finally:
        callback.close()
    if params.get("error"):
        if params["error"] == "access_denied":
            raise AuthError("Bạn đã không cho phép Peto Agent đăng nhập ChatGPT.", "declined")
        raise AuthError(f"OpenAI không hoàn tất đăng nhập ({params['error'][:60]}).", "incomplete")
    issued = params.get("client_id")
    if attempt.client_id is None:
        if not issued:
            raise AuthError("OpenAI chưa cấp client ID cho lần đăng ký này. Thử lại nhé.", "incomplete")
        client_id = issued
    else:
        if issued and issued != attempt.client_id:
            raise AuthError("OpenAI trả client ID khác với tài khoản đang đăng nhập lại; Peto không thay.", "mismatch")
        client_id = attempt.client_id
    code = params.get("code")
    if not code:
        raise AuthError("OpenAI không trả mã đăng nhập. Thử lại nhé.", "incomplete")
    try:
        tokens = _auth_http().json("POST", TOKEN_PATH, form={
            "grant_type": "authorization_code", "code": code, "client_id": client_id,
            "code_verifier": attempt.verifier, "redirect_uri": callback.redirect_uri, "resource": RESOURCE})
    except ProviderHTTPError as err:
        raise AuthError(_oauth_problem(err), "invalid_client" if err.code == "invalid_client" else "network") from None
    if not tokens.get("access_token") or not tokens.get("id_token"):
        raise AuthError("OpenAI không trả đủ token. Thử lại nhé.", "incomplete")
    claims = verify_id_token(str(tokens["id_token"]), client_id=client_id, nonce=attempt.nonce)
    if attempt.expected_sub and claims["sub"] != attempt.expected_sub:
        raise AuthError("Bạn vừa đăng nhập một tài khoản ChatGPT khác với tài khoản này; Peto không thay thông tin "
                        "đăng nhập của nó. Chọn đúng tài khoản, hoặc thêm tài khoản mới.", "mismatch")
    record = _token_record(tokens, client_id=client_id, claims=claims)
    scope_text = params.get("scope") if not tokens.get("scope") else tokens["scope"]
    record["scopes"] = str(scope_text or record["scopes"])
    plan = PLAN_SCOPE in record["scopes"].replace("+", " ").split()
    return Result(record, plan, record["email"], claims["sub"], client_id)


def _oauth_problem(err: ProviderHTTPError) -> str:
    if err.status == 0 and err.code == "tls":
        return ("Không xác minh được chứng chỉ HTTPS của OpenAI. Kiểm tra giờ trên máy và kho chứng chỉ Windows rồi thử "
                "lại.")
    if err.status == 0:
        return "Không kết nối được OpenAI để hoàn tất đăng nhập. Kiểm tra mạng rồi thử lại."
    if err.code == "invalid_client":
        return "OpenAI không nhận client ID của Peto Agent cho tài khoản này. Thử đăng nhập lại từ đầu."
    return f"OpenAI không hoàn tất đăng nhập (HTTP {err.status}{' ' + err.code if err.code else ''})."


def list_models(access_token: str) -> list[tuple[str, str]]:
    """Model tài khoản ChatGPT dùng được, theo thứ tự OpenAI trả: (slug, tên hiển thị) có ``visibility == "list"``."""
    payload = ProviderHTTP(API_BASE, {"Authorization": f"Bearer {access_token}"}).json("GET", "/models")
    rows = payload.get("models") if isinstance(payload.get("models"), list) else []
    found = []
    for row in rows:
        if not isinstance(row, dict) or row.get("visibility") != "list":
            continue
        slug, name = row.get("slug"), row.get("display_name")
        if isinstance(slug, str) and slug and len(slug) <= 64 and slug.isascii():
            found.append((slug, str(name or slug)[:60]))
    return found


# ---- Làm mới, thu hồi ---------------------------------------------------------------------------------------------

class _FileLock:
    """Khóa tệp giữa các tiến trình peto (Windows: msvcrt.locking), để hai cửa sổ không cùng làm mới một refresh token
    xoay vòng."""

    def __init__(self, connection_id: str):
        folder = config.home() / "credentials"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{connection_id}.lock"
        self.handle = None

    def __enter__(self):
        self.handle = open(self.path, "a+b")
        deadline = time.monotonic() + LOCK_SECONDS
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() > deadline:
                    self.handle.close()
                    raise AuthError("Một cửa sổ peto khác đang làm mới đăng nhập ChatGPT. Thử lại sau ít giây.",
                                    "network") from None
                time.sleep(0.1)

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            self.handle.close()


def mark_signed_out(connection_id: str) -> None:
    """Bộ token hết dùng được: bỏ token, giữ client ID và tài khoản để đăng nhập lại."""
    try:
        record = credentials.load_record(connection_id)
        for name in ("access_token", "refresh_token"):
            record[name] = ""
        credentials.save_record(connection_id, record)
    except credentials.CredentialError:
        pass
    connections.update(connection_id, extra={"status": "signed_out"})


def access_token(connection: connections.Connection, *, force: bool = False) -> str:
    """Access token còn hạn của kết nối; gần hết hạn (hay ``force`` sau một 401) thì làm mới, tuần tự giữa các tiến
    trình. Lỗi mạng tạm thời không xóa thông tin đăng nhập."""
    if connection.extra.get("status") == "signed_out":
        raise AuthError(f"Đăng nhập ChatGPT ({connection.label}) đã hết hiệu lực. Gõ /connect để đăng nhập lại.",
                        "signed_out")
    record = credentials.load_record(connection.id)
    if not force and record.get("access_token") and record.get("expires_at", 0) - time.time() > REFRESH_MARGIN:
        return record["access_token"]
    with _FileLock(connection.id):
        current = credentials.load_record(connection.id)
        if current.get("access_token") != record.get("access_token") and \
                current.get("expires_at", 0) - time.time() > REFRESH_MARGIN:
            return current["access_token"]  # cửa sổ khác vừa làm mới xong
        record = current
        if not record.get("refresh_token"):
            mark_signed_out(connection.id)
            raise AuthError(f"Đăng nhập ChatGPT ({connection.label}) đã hết hiệu lực. Gõ /connect để đăng nhập lại.",
                            "signed_out")
        earliest = record.get("earliest_refresh_at")
        still_valid = record.get("access_token") and record.get("expires_at", 0) > time.time()
        if not force and still_valid and isinstance(earliest, (int, float)) and time.time() < earliest:
            return record["access_token"]
        try:
            tokens = _auth_http().json("POST", TOKEN_PATH, form={
                "grant_type": "refresh_token", "client_id": record["client_id"],
                "refresh_token": record["refresh_token"], "resource": RESOURCE})
        except ProviderHTTPError as err:
            if err.code in TERMINAL_REFRESH:
                mark_signed_out(connection.id)
                raise AuthError(f"Đăng nhập ChatGPT ({connection.label}) đã hết hiệu lực. Gõ /connect để đăng nhập "
                                "lại.", "signed_out") from None
            if err.code == "invalid_client":
                raise AuthError("OpenAI không nhận client ID của kết nối này. Gõ /connect, xóa rồi đăng nhập lại.",
                                "invalid_client") from None
            if still_valid and not force:
                return record["access_token"]
            raise AuthError("Không làm mới được đăng nhập ChatGPT (mạng hay OpenAI đang lỗi). Thử lại sau nhé.",
                            "network") from None
        if not tokens.get("access_token"):
            raise AuthError("OpenAI không trả access token mới. Thử lại sau nhé.", "network")
        claims = {"sub": record.get("subject"), "email": record.get("email")}
        if tokens.get("id_token"):
            claims = verify_id_token(str(tokens["id_token"]), client_id=record["client_id"], nonce=None)
            if claims["sub"] != record.get("subject"):
                raise AuthError("OpenAI trả token của một tài khoản khác; Peto không dùng nó.", "mismatch")
        fresh = _token_record(tokens, client_id=record["client_id"], claims=claims, previous=record)
        credentials.save_record(connection.id, fresh)
        return fresh["access_token"]


def revoke(connection_id: str) -> bool:
    """Thu hồi refresh token ở OpenAI (OAuth revoke). True khi OpenAI xác nhận (kể cả token đã hết hiệu lực)."""
    try:
        record = credentials.load_record(connection_id)
    except credentials.CredentialError:
        return False
    token, client_id = record.get("refresh_token"), record.get("client_id")
    if not token or not client_id:
        return False
    for delay in (0.0, 0.5, 1.5):
        time.sleep(delay)
        try:
            _auth_http().json("POST", REVOKE_PATH, form={"token": token, "token_type_hint": "refresh_token",
                                                         "client_id": client_id})
            return True
        except ProviderHTTPError as err:
            if err.status != 0 and err.status < 500:
                return False
    return False


# ---- Lưu kết quả đăng nhập --------------------------------------------------------------------------------------

def registrations() -> dict[str, dict]:
    """Tài khoản đã từng đăng ký trên máy này (theo ``sub``): client ID được cấp và email. Giữ cả sau khi xóa kết nối,
    vì thu hồi token không xóa đăng ký client; lần đăng nhập lại dùng lại client ID đó."""
    found = config.load().get("chatgpt_registrations")
    if not isinstance(found, dict):
        return {}
    return {sub: row for sub, row in found.items()
            if isinstance(sub, str) and isinstance(row, dict) and isinstance(row.get("client_id"), str)}


def remember_registration(sub: str, client_id: str, email: str) -> None:
    settings = config.load()
    rows = settings.get("chatgpt_registrations") if isinstance(settings.get("chatgpt_registrations"), dict) else {}
    rows[sub] = {"client_id": client_id, "email": email}
    settings["chatgpt_registrations"] = rows
    config.save(settings)


def attempt_for(connection: connections.Connection | None = None, *, sub: str | None = None,
                consent: bool = False) -> Attempt:
    """Lần đăng nhập: mới (đăng ký), lại cho một kết nối (client ID, ID token cũ, email), hay lại cho một tài khoản đã
    từng đăng ký."""
    if connection is not None:
        hint = None
        try:
            hint = credentials.load_record(connection.id).get("id_token") or None
        except credentials.CredentialError:
            pass
        return Attempt(client_id=connection.extra.get("client_id"), expected_sub=connection.extra.get("sub"),
                       id_token_hint=hint, login_hint=connection.extra.get("email") or None, consent=consent)
    if sub is not None and (row := registrations().get(sub)):
        return Attempt(client_id=row["client_id"], expected_sub=sub, login_hint=row.get("email") or None,
                       consent=consent)
    return Attempt(consent=consent)


def store(result: Result, *, existing: connections.Connection | None = None) -> connections.Connection:
    """Lưu một lần đăng nhập thành công: bộ token vào kho DPAPI, hồ sơ không bí mật vào connections.json. Cùng tài khoản
    đã có kết nối thì cập nhật kết nối đó thay vì thêm bản thứ hai. Có quyền dùng gói thì lấy danh sách model."""
    models: list[tuple[str, str]] = []
    if result.plan:
        try:
            models = list_models(result.record["access_token"])
        except ProviderHTTPError:
            models = []
    if existing is None:
        existing = next((item for item in connections.load_all()
                         if item.provider == "chatgpt" and item.extra.get("sub") == result.sub), None)
    extra = {"client_id": result.client_id, "sub": result.sub, "email": result.email, "plan": result.plan,
             "status": "", "model_names": {slug: name for slug, name in models}}
    remember_registration(result.sub, result.client_id, result.email)
    if existing is not None:
        credentials.save_record(existing.id, result.record)
        updated = connections.update(existing.id, models=tuple(slug for slug, _ in models) if result.plan else (),
                                     extra=extra)
        return updated or existing
    return connections.add("chatgpt", result.record, label=result.email or "ChatGPT", endpoint=API_BASE,
                           models=tuple(slug for slug, _ in models), extra=extra)

"""Gói ChatGPT, mốc M5: đăng nhập OAuth (PKCE, state, nonce, callback 127.0.0.1, client ID cấp động), kiểm chữ ký ID token
RS256 bằng thư viện chuẩn, làm mới và thu hồi token, yêu cầu Responses theo giới hạn của đường ChatGPT (namespace, không
max_output_tokens), lỗi hạn mức, và bảng "Continue with ChatGPT". Máy chủ OpenAI giả trên 127.0.0.1; không gọi OpenAI thật.

Khóa RSA dưới đây chỉ để ký token giả trong test, sinh riêng cho test, không phải khóa của ai."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import FakeUI
from test_footer import settle
from test_mouse import rows
from test_screen import rich_glyphs, run  # noqa: F401 - fixture màn hình giả

from peto_agent import __main__ as cli
from peto_agent import chatgpt_auth, config, connections, credentials, history, jwt_rs256
from peto_agent import model_catalog as catalog, model_dialogs
from peto_agent.line_editor import Key
from peto_agent.loop import Session, TaskLog, portable
from peto_agent.providers import chatgpt as chatgpt_provider
from peto_agent.tools import FEATURES, NEW_FEATURES
from peto_agent.workspace import Workspace

pytestmark = pytest.mark.skipif(not credentials.available(), reason="Kho khóa DPAPI chỉ có trên Windows.")

N = int(
    "be11ff45bd60d5a8d4c92e540b126ad33379e505bd06a0ae56324cd5115257f7bb672c0639973e87b3f54522aa74579e48a1"
    "32c7371774f7d9721a59e54692bb8fbdec168d40385c54571bfcf08e2ade20bc7d6b14fc1f75b7726c8fc10920a3a43951d1"
    "f2164ee64168016658aa9960280e0a21c81cc07296a609cb9887a146ff0d79952a2ee05584c48daa89c98a6596eb3c2c2b2d"
    "9a20fcf1483e93fe7def1d297f358b3db00b395d5f709df4369fc81839e8ecbcdcfb4e2ee0a180f82e725c2ebe0e6daf3b31"
    "dd59c993210ebcab4086b2c51fd4279c1297a7d929d5a09806f0af65c6de3b3d85b5258aa589163105a9aaffe4f16bf65560"
    "7c5045ac7e31", 16)
D = int(
    "bc4139144b0931360263acc6431d1fbf4619f253a7b07bcf90c24b4531dddc111b85899e34c66f819b25502f90a2a0f1be40"
    "22fa1bbfd8f36f64cb62c46b0d0446cfb6997397eafacff2635f38a7a71fd14ebfee229fc14d27c066744f9e89bc6af8f6e8"
    "399e0cd19470be0a2fc1f11dc32e7cac8ef6a34a1b9a22d38ba4b27fd7f14588275e32ffbbb219a0eea9f66b64d443dda6a5"
    "5bbdf2b18f243ee49f9d160f95f1d2dff705b9799eff6d71306b813cded755c4a2445e4fb8da7f6185f908d230be84e47bc4"
    "b10cfee09b21c03577cb41b4dd1b9a1a5f61b3c422c99257f556124d2ab0427870c89a984f2471fabafb59bec3272e5fe7d6"
    "e7f6d3bba201", 16)
E = 65537
KID = "peto-test-key"
JWK = {"kty": "RSA", "kid": KID, "use": "sig", "alg": "RS256", "n": jwt_rs256.b64url_encode(N.to_bytes(256, "big")),
       "e": jwt_rs256.b64url_encode(E.to_bytes(3, "big"))}
SUB = "user-test-0001"
EMAIL = "ban@example.com"
PLAN_SCOPES = "chatgpt.tokens.use.direct email offline_access openid profile resource.invoke"


def sign(claims: dict, *, kid: str = KID, alg: str = "RS256", key: int = None) -> str:
    head = jwt_rs256.b64url_encode(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode())
    body = jwt_rs256.b64url_encode(json.dumps(claims).encode())
    signed = f"{head}.{body}".encode()
    digest = jwt_rs256.SHA256_PREFIX + hashlib.sha256(signed).digest()
    encoded = b"\x00\x01" + b"\xff" * (256 - len(digest) - 3) + b"\x00" + digest
    signature = pow(int.from_bytes(encoded, "big"), key or D, N).to_bytes(256, "big")
    return f"{head}.{body}.{jwt_rs256.b64url_encode(signature)}"


def secret_token(prefix: str) -> str:
    return f"{prefix}-" + secrets.token_urlsafe(40)


class OpenAI(BaseHTTPRequestHandler):
    """auth.openai.com và api.openai.com giả trong một máy chủ."""

    def _json(self, status: int, payload=None) -> None:
        data = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _form(self) -> dict:
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        assert self.headers.get("Content-Type") == "application/x-www-form-urlencoded"
        return {key: values[0] for key, values in parse_qs(raw).items()}

    def do_GET(self):  # noqa: N802
        server = self.server
        server.log.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path == "/.well-known/jwks.json":
            return self._json(200, {"keys": [JWK]})
        if self.path == "/v1/models":
            if self.headers.get("Authorization") != f"Bearer {server.access}":
                return self._json(401, {"detail": "không nhận token"})
            return self._json(200, {"models": [
                {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "visibility": "list"},
                {"slug": "gpt-hidden", "display_name": "Ẩn", "visibility": "hide"},
                {"slug": "gpt-6-luna", "display_name": "GPT-6 Luna", "visibility": "list"}]})
        self._json(404, {"detail": "không có"})

    def do_POST(self):  # noqa: N802
        server = self.server
        if self.path == "/api/accounts/oauth/token":
            form = self._form()
            server.log.append(("POST", self.path, form))
            if form.get("grant_type") == "authorization_code":
                pending = server.codes.pop(form.get("code"), None)
                expected = jwt_rs256.b64url_encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
                if (pending is None or pending["challenge"] != expected or form.get("client_id") != server.client_id
                        or form.get("redirect_uri") != pending["redirect_uri"]
                        or form.get("resource") != chatgpt_auth.RESOURCE):
                    return self._json(400, {"error": "invalid_grant", "error_description": "mã không đúng"})
                return self._json(200, server.tokens(nonce=pending["nonce"]))
            if form.get("grant_type") == "refresh_token":
                if form.get("refresh_token") != server.refresh or form.get("client_id") != server.client_id:
                    return self._json(400, {"error": server.refresh_error, "error_description": "refresh hỏng"})
                return self._json(200, server.tokens(nonce=None))
            return self._json(400, {"error": "unsupported_grant_type"})
        if self.path == "/api/accounts/oauth/revoke":
            form = self._form()
            server.log.append(("POST", self.path, form))
            server.revoked.append(form)
            return self._json(200)
        if self.path == "/v1/responses":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            server.log.append(("POST", self.path, self.headers.get("Authorization")))
            server.responses.append({"auth": self.headers.get("Authorization"), "body": body})
            status, payload = server.reply(body, self.headers.get("Authorization"))
            if status != 200:
                return self._json(status, payload)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for event in payload:
                self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
            return None
        self._json(404, {"detail": "không có"})

    def log_message(self, *args):
        pass


def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def completed(*output, tokens=9000):
    text = "".join(part["text"] for item in output if item.get("type") == "message" for part in item["content"])
    return 200, [*([{"type": "response.output_text.delta", "delta": text}] if text else []),
                 {"type": "response.completed", "response": {"status": "completed", "output": list(output),
                                                              "usage": {"input_tokens": tokens, "output_tokens": 200}}}]


@pytest.fixture
def openai(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), OpenAI)
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    server.log, server.codes, server.revoked, server.responses = [], {}, [], []
    server.client_id = "app_issued_" + secrets.token_hex(6)
    server.access = server.refresh = server.id_token = ""
    server.scopes, server.sub, server.refresh_error = PLAN_SCOPES, SUB, "invalid_grant"
    server.reply = lambda body, auth: completed(message("Xong."))

    def tokens(nonce):
        server.access, server.refresh = secret_token("at"), secret_token("rt")
        claims = {"iss": server.url, "aud": server.client_id, "sub": server.sub, "email": EMAIL,
                  "exp": time.time() + 3600, "iat": time.time()}
        if nonce is not None:
            claims["nonce"] = nonce
        server.id_token = sign(claims)
        return {"access_token": server.access, "refresh_token": server.refresh, "id_token": server.id_token,
                "token_type": "Bearer", "expires_in": 3600, "scope": server.scopes}

    server.tokens = tokens
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Không bao giờ mở trình duyệt thật trong test.
    monkeypatch.setattr(webbrowser, "open", lambda url: False)
    monkeypatch.setattr(chatgpt_auth, "ISSUER", server.url)
    monkeypatch.setattr(chatgpt_auth, "API_BASE", f"{server.url}/v1")
    monkeypatch.setattr(chatgpt_auth, "PREFERRED_PORT", 0)
    yield server
    server.shutdown()
    server.server_close()


def browser(server, *, deny=False, issue=True, wrong_state=False, scope=None):
    """Trình duyệt giả: đọc địa chỉ đăng nhập rồi gọi callback trên 127.0.0.1 như OpenAI chuyển về."""
    seen = {}

    def open_browser(url: str) -> bool:
        query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        seen.update(query)
        code = secrets.token_urlsafe(16)
        server.codes[code] = {"challenge": query["code_challenge"], "nonce": query["nonce"],
                              "redirect_uri": query["redirect_uri"]}
        params = {"state": "khac" if wrong_state else query["state"]}
        if deny:
            params["error"] = "access_denied"
        else:
            params.update(code=code, scope=scope or server.scopes)
            if issue and query["client_id"] == chatgpt_auth.DYNAMIC_CLIENT:
                params["client_id"] = server.client_id

        def call():
            from urllib.parse import urlencode
            try:
                urllib.request.urlopen(f"{query['redirect_uri']}?{urlencode(params)}", timeout=5).read()
            except OSError:
                pass

        threading.Thread(target=call, daemon=True).start()
        return True

    open_browser.seen = seen
    return open_browser


# ---- Chữ ký RS256 --------------------------------------------------------------------------------------------

def test_rs256_accepts_only_exact_signatures():
    claims = {"sub": "a", "exp": 1}
    token = sign(claims)
    assert jwt_rs256.verify(token, [JWK]) == claims
    head, body, signature = token.split(".")
    forged_body = jwt_rs256.b64url_encode(json.dumps({"sub": "b", "exp": 1}).encode())
    for bad in (f"{head}.{forged_body}.{signature}", f"{head}.{body}.{signature[:-4]}AAAA",
                sign(claims, alg="none"), sign(claims, kid="khac"), "a.b", token + "x"):
        with pytest.raises(jwt_rs256.TokenError):
            jwt_rs256.verify(bad, [JWK])
    other = int("f" * 255 + "1", 16) | 1
    with pytest.raises(jwt_rs256.TokenError):
        jwt_rs256.verify(token, [{**JWK, "n": jwt_rs256.b64url_encode(other.to_bytes(128, "big"))}])  # khóa < 2048 bit
    with pytest.raises(jwt_rs256.TokenError):
        jwt_rs256.verify(token, [{**JWK, "e": jwt_rs256.b64url_encode(b"\x02")}])
    huge = jwt_rs256.b64url_encode((N + 1).to_bytes(256, "big"))
    assert not jwt_rs256.verify_signature(f"{head}.{body}".encode(), jwt_rs256.b64url_decode(huge), JWK)


# ---- Đăng nhập ------------------------------------------------------------------------------------------------

def test_first_sign_in_registers_dynamically_verifies_the_id_token_and_stores_a_plan_connection(openai, agent_home):
    opened = browser(openai)
    result = chatgpt_auth.sign_in(chatgpt_auth.Attempt(), open_browser=opened, timeout=10)
    seen = opened.seen
    assert seen["client_id"] == "dynamic_agent_client" and seen["agent_name_hint"] == "Peto Agent"
    assert seen["response_type"] == "code" and seen["code_challenge_method"] == "S256"
    assert seen["resource"] == "https://api.openai.com/v1" and "chatgpt.tokens.use.direct" in seen["scope"].split()
    assert urlsplit(seen["redirect_uri"]).hostname == "127.0.0.1" and seen["redirect_uri"].endswith("/auth/callback")
    host = seen["ext_agent_host_id"]
    assert host == config.load()["chatgpt_host_id"] and EMAIL not in host and SUB not in host
    exchange = next(entry[2] for entry in openai.log if entry[1] == "/api/accounts/oauth/token")
    assert exchange["client_id"] == openai.client_id, "đổi mã bằng client ID được cấp, không phải dynamic_agent_client"
    assert exchange["redirect_uri"] == seen["redirect_uri"] and "client_secret" not in exchange
    assert result.plan and result.sub == SUB and result.client_id == openai.client_id

    item = chatgpt_auth.store(result)
    assert item.provider == "chatgpt" and item.label == EMAIL and item.models == ("gpt-6.1-sol", "gpt-6-luna")
    assert item.extra["client_id"] == openai.client_id and item.extra["plan"] is True
    assert chatgpt_auth.registrations() == {SUB: {"client_id": openai.client_id, "email": EMAIL}}
    assert credentials.load_record(item.id)["refresh_token"] == openai.refresh
    on_disk = (agent_home / "connections.json").read_text(encoding="utf-8") + json.dumps(config.load())
    assert openai.access not in on_disk and openai.refresh not in on_disk and openai.id_token not in on_disk
    assert [row["label"] for row in catalog.direct_models()] == ["GPT-6.1 Sol", "GPT-6 Luna"]

    again = browser(openai)
    chatgpt_auth.sign_in(chatgpt_auth.attempt_for(item), open_browser=again, timeout=10)
    assert again.seen["client_id"] == openai.client_id and "agent_name_hint" not in again.seen
    assert again.seen["ext_agent_host_id"] == host and again.seen["login_hint"] == EMAIL
    assert again.seen["id_token_hint"], "đăng nhập lại gửi ID token cũ để bỏ qua bước chọn tài khoản"


def test_sign_in_refusals_mismatches_and_identity_only(openai):
    with pytest.raises(chatgpt_auth.AuthError) as denied:
        chatgpt_auth.sign_in(chatgpt_auth.Attempt(), open_browser=browser(openai, deny=True), timeout=10)
    assert denied.value.kind == "declined"
    with pytest.raises(chatgpt_auth.AuthError) as missing:
        chatgpt_auth.sign_in(chatgpt_auth.Attempt(), open_browser=browser(openai, issue=False), timeout=10)
    assert missing.value.kind == "incomplete", "đăng ký mới không có client ID thì chưa xong"
    with pytest.raises(chatgpt_auth.AuthError) as stray:
        chatgpt_auth.sign_in(chatgpt_auth.Attempt(), open_browser=browser(openai, wrong_state=True), timeout=0.6)
    assert stray.value.kind == "timeout", "callback mang state khác bị bỏ qua"
    with pytest.raises(chatgpt_auth.AuthError) as cancelled:
        chatgpt_auth.sign_in(chatgpt_auth.Attempt(), open_browser=lambda url: True, cancelled=lambda: True)
    assert cancelled.value.kind == "cancelled"

    openai.scopes = "openid email profile offline_access"
    identity = chatgpt_auth.sign_in(chatgpt_auth.Attempt(), open_browser=browser(openai), timeout=10)
    assert not identity.plan, "có ID token chưa đủ: thiếu chatgpt.tokens.use.direct thì không dùng gói"
    item = chatgpt_auth.store(identity)
    assert catalog.direct_models() == [] and item.extra["plan"] is False

    openai.scopes, openai.sub = PLAN_SCOPES, "user-khac"
    with pytest.raises(chatgpt_auth.AuthError) as other:
        chatgpt_auth.sign_in(chatgpt_auth.attempt_for(item), open_browser=browser(openai), timeout=10)
    assert other.value.kind == "mismatch", "đăng nhập lại bằng tài khoản khác không thay thông tin của tài khoản này"


def test_id_token_checks_issuer_audience_expiry_and_nonce(openai):
    good = {"iss": openai.url, "aud": "app_x", "sub": SUB, "exp": time.time() + 60, "nonce": "n1"}
    assert chatgpt_auth.verify_id_token(sign(good), client_id="app_x", nonce="n1")["sub"] == SUB
    for change, word in (({"iss": "https://khac"}, "nơi cấp"), ({"aud": "app_y"}, "client ID"),
                         ({"exp": time.time() - 3600}, "hạn"), ({"nonce": "n2"}, "nonce")):
        with pytest.raises(chatgpt_auth.AuthError) as err:
            chatgpt_auth.verify_id_token(sign({**good, **change}), client_id="app_x", nonce="n1")
        assert word in str(err.value)


def signed_in(openai):
    result = chatgpt_auth.sign_in(chatgpt_auth.Attempt(), open_browser=browser(openai), timeout=10)
    return chatgpt_auth.store(result)


def test_refresh_rotates_serially_and_a_dead_refresh_token_signs_out(openai):
    item = signed_in(openai)
    first = openai.access
    record = credentials.load_record(item.id)
    record["expires_at"] = time.time() + 30
    credentials.save_record(item.id, record)
    old_refresh = record["refresh_token"]
    token = chatgpt_auth.access_token(connections.get(item.id))
    assert token == openai.access != first
    refresh = [entry[2] for entry in openai.log if entry[1] == "/api/accounts/oauth/token"][-1]
    assert refresh["grant_type"] == "refresh_token" and refresh["refresh_token"] == old_refresh
    assert refresh["client_id"] == openai.client_id and "scope" not in refresh
    saved = credentials.load_record(item.id)
    assert saved["refresh_token"] == openai.refresh != old_refresh, "refresh token xoay vòng được lưu"
    assert chatgpt_auth.access_token(connections.get(item.id)) == token, "còn hạn thì không làm mới"

    openai.refresh, openai.refresh_error = "da-thu-hoi", "refresh_token_reused"
    with pytest.raises(chatgpt_auth.AuthError) as err:
        chatgpt_auth.access_token(connections.get(item.id), force=True)
    assert err.value.kind == "signed_out" and connections.get(item.id).extra["status"] == "signed_out"
    assert credentials.load_record(item.id)["refresh_token"] == ""
    assert connections.get(item.id).extra["client_id"] == openai.client_id, "giữ client ID để đăng nhập lại"


# ---- Gọi model ------------------------------------------------------------------------------------------------

def plan_session(project, openai, ui=None):
    item = signed_in(openai)
    work = Session(cli._offline_client({}), Workspace(project), ui or FakeUI(), log=TaskLog(project.name))
    direct = [*FEATURES, *(feature for feature in NEW_FEATURES if feature in cli.BUNDLE_FEATURES)]
    work.source_features = {"peto": list(FEATURES), "openai-key": direct, "chatgpt-plan": direct}
    work.configure_models(catalog.budget_rows(catalog.direct_models()))
    work.select("chatgpt-plan", "gpt-6.1-sol", connection=item.id, step_cost=0)
    work.supported_efforts = ["low", "medium", "high"]
    return work, item


def test_requests_follow_the_chatgpt_route_rules_and_namespaced_calls_run(project, openai, agent_home):
    (project / "README.md").write_text("# Dự án\n", encoding="utf-8")
    call = {"type": "function_call", "call_id": "c1", "namespace": "peto", "name": "read_file",
            "arguments": json.dumps({"path": "README.md", "start_line": None, "end_line": None})}

    def reply(body, auth):
        if any(item.get("type") == "function_call_output" for item in body["input"]):
            return completed(message("README chỉ có tiêu đề."))
        if body.get("instructions", "").startswith("Write a short title"):
            return completed(message("Đọc README"))
        return completed(call)

    openai.reply = reply
    work, item = plan_session(project, openai)
    work.run_task("Đọc README giúp mình")
    assert "README chỉ có tiêu đề." in work.ui.text
    work_requests = [entry["body"] for entry in openai.responses if entry["body"].get("tools")]
    assert len(work_requests) >= 2
    for body in work_requests:
        assert set(body) <= chatgpt_provider.ALLOWED
        assert body["store"] is False and body["stream"] is True and "max_output_tokens" not in body
        assert [tool["type"] for tool in body["tools"]] == ["namespace"]
        assert body["tools"][0]["name"] == "peto" and all(tool["type"] == "function" for tool in body["tools"][0]["tools"])
        assert not any(entry.get("role") == "system" for entry in body["input"])
    follow = work_requests[1]["input"]
    assert any(entry.get("type") == "function_call" and entry.get("namespace") == "peto" for entry in follow)
    assert all(entry["auth"] == f"Bearer {openai.access}" for entry in openai.responses)
    assert work.models.usage[("chatgpt-plan", item.id)]["calls"] >= 2
    # Token không nằm trong tệp hội thoại, nhật ký hay bất cứ đâu ngoài kho DPAPI.
    work.save()
    needles = [token.encode() for token in (openai.access, openai.refresh, openai.id_token)]
    # Tệp -shm của SQLite chỉ là chỉ mục WAL (không chứa dữ liệu hàng) và bị khóa khi nhật ký còn mở; WAL và tệp chính
    # vẫn được quét.
    leaks = [str(path) for root in (agent_home, project) for path in root.rglob("*") if path.is_file()
             and path.parent.name != "credentials" and not path.name.endswith("-shm")
             and any(needle in path.read_bytes() for needle in needles)]
    assert leaks == []
    assert all("namespace" not in entry for entry in portable(work.items)), "chuyển sang nguồn khác bỏ namespace"


def test_usage_limit_points_to_manage_usage_and_a_revoked_token_is_refreshed_once(project, openai):
    work, item = plan_session(project, openai)
    openai.reply = lambda body, auth: (200, [{"type": "response.failed", "response": {"error": {
        "code": "subscription_sharing_usage_limit_exceeded", "message": "limit"}}}])
    work.run_task("Chào")
    assert "Manage usage: ChatGPT → Settings → Usage" in work.ui.text and work.source == "chatgpt-plan"
    assert not [entry for entry in openai.log if entry[1] == "/api/accounts/oauth/token" and
                entry[2].get("grant_type") == "refresh_token"], "lỗi hạn mức không đăng nhập lại"

    stale = openai.access
    openai.reply = lambda body, auth: ((401, {"error": {"code": "subscription_sharing_invalid_user", "message": "x"}})
                                       if auth == f"Bearer {stale}" else completed(message("Đã làm mới.")))
    work.run_task("Lại nhé")
    assert "Đã làm mới." in work.ui.text and openai.access != stale


def test_disconnect_revokes_and_keeps_the_registration(openai, agent_home):
    item = signed_in(openai)
    refresh = openai.refresh
    ui = FakeUI()
    assert cli.disconnect(ui, item.id) == 0
    assert openai.revoked == [{"token": refresh, "token_type_hint": "refresh_token", "client_id": openai.client_id}]
    assert connections.load_all() == [] and not (agent_home / "credentials" / f"{item.id}.bin").exists()
    assert "Đã đăng xuất ChatGPT" in ui.text and SUB in chatgpt_auth.registrations()
    assert chatgpt_auth.attempt_for(None, sub=SUB).client_id == openai.client_id


def test_text_connect_chatgpt_selects_a_default(openai):
    ui = FakeUI()
    assert cli.connect_chatgpt(ui, open_browser=browser(openai)) == 0
    item = connections.load_all()[0]
    assert config.load()["selection"] == {"source": "chatgpt-plan", "connection": item.id, "model": "gpt-6.1-sol"}
    assert "Using ChatGPT plan" in ui.text and "Manage usage" in ui.text


# ---- Bảng /connect ------------------------------------------------------------------------------------------

def test_continue_with_chatgpt_from_the_connect_dialog(run, project, openai, monkeypatch):  # noqa: F811
    screen = run(100, 34)
    work = Session(cli._offline_client({}), Workspace(project), screen.ui)
    cat = catalog.Catalog([{"key": "peto", "label": "Peto", "step_cost": 1}], account="Bình", logged_in=True)
    work.model_catalog = cat
    work.supported_efforts = ["low", "medium", "high"]
    gate = threading.Event()
    real = browser(openai)
    monkeypatch.setattr(webbrowser, "open", lambda url: gate.wait(5) and real(url))
    thread = threading.Thread(target=lambda: model_dialogs.sources(screen.ui, work, cat), daemon=True)
    thread.start()
    assert settle(lambda: "Kết nối nguồn" in rows(screen))
    screen.press(Key("down"), Key("enter"))
    assert settle(lambda: "Kết nối OpenAI" in rows(screen))
    screen.press(Key("enter"))
    assert settle(lambda: "Đang chờ đăng nhập trong trình duyệt" in rows(screen))
    gate.set()
    assert settle(lambda: "You're using your ChatGPT plan" in rows(screen), timeout=8)
    screen.press(Key("enter"))
    assert settle(lambda: "Chọn model · ban@example.com" in rows(screen))
    screen.press(Key("enter"))
    thread.join(timeout=5)
    assert work.source == "chatgpt-plan" and work.model == "gpt-6.1-sol"
    assert "Using ChatGPT plan" in rows(screen) and config.load()["chatgpt_welcome_shown"] is True

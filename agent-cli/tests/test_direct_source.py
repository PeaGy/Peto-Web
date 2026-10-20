"""Nguồn khóa OpenAI riêng, mốc M3: CLI gọi thẳng Responses API (máy chủ OpenAI giả trên 127.0.0.1), không cần máy chủ
Peto, không tính bước Peto, khóa không lọt ra đâu ngoài phần đầu yêu cầu tới đúng địa chỉ của kết nối."""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import FakeUI, handoff
from test_loop_client import Handler as PetoHandler

from peto_agent import __main__ as cli
from peto_agent import config, connections, credentials, export, history, loop
from peto_agent.bundle import agent_prompts, assembly
from peto_agent.loop import Session, TaskLog
from peto_agent.providers import classify
from peto_agent.providers.transport import ProviderHTTP, ProviderHTTPError
from peto_agent.tools import FEATURES, NEW_FEATURES, Tools
from peto_agent.workspace import Workspace

pytestmark = pytest.mark.skipif(not credentials.available(), reason="Kho khóa DPAPI chỉ có trên Windows.")

# Khóa giả, đủ dài để mọi lần quét tìm rò rỉ có ý nghĩa; không phải khóa thật của ai.
KEY = "sk-peto-test-" + "Qx7" * 15
COMMAND = f'"{sys.executable}" -c "print(\'ok\')"'
PATCH = "*** Begin Patch\n*** Update File: README.md\n@@\n-# Dự án thử\n+# Dự án thử (Peto)\n*** End Patch"


def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def call(stage, name, **arguments):
    return {"type": "function_call", "call_id": f"call_{stage}", "name": name, "arguments": json.dumps(arguments)}


def answer(text, *calls, tokens=12000):
    """Sự kiện SSE của Responses API cho một bước: chữ rồi response.completed."""
    return 200, [{"type": "response.output_text.delta", "delta": text},
                 {"type": "response.completed", "response": {
                     "status": "completed", "output": [message(text), *calls],
                     "usage": {"input_tokens": tokens, "output_tokens": 300,
                               "input_tokens_details": {"cached_tokens": 4000}}}}]


def purpose_of(body):
    instructions = body.get("instructions") or ""
    if instructions == agent_prompts.TITLE_PROMPT:
        return "title"
    if instructions == agent_prompts.COMPACT_PROMPT:
        return "compact"
    for marker, purpose in (("## Side question (/btw)", "btw"), ("You are a Peto Agent subagent", "explore"),
                            ("## Step limit reached for this request", "wrapup")):
        if marker in instructions:
            return purpose
    return "work"


def outputs(body):
    return [json.loads(item["output"]) for item in body["input"] if item.get("type") == "function_call_output"]


def workflow(body):
    """Đọc README → sửa bằng apply_patch → chạy lệnh kiểm → trả kết quả; lượt phụ trả chữ theo mục đích."""
    purpose = purpose_of(body)
    if purpose == "title":
        return answer("Sửa dòng đầu README")
    if purpose == "compact":
        return answer(handoff("Đã sửa README và chạy lệnh kiểm."))
    if purpose == "btw":
        return answer("Peto đang sửa README.")
    if purpose == "wrapup":
        return answer("Đã đủ bước cho yêu cầu này: đã đọc README, chưa sửa.")
    done = outputs(body)
    if not done:
        return answer("", call(0, "read_file", path="README.md", start_line=None, end_line=None))
    if len(done) == 1:
        return answer("", call(1, "apply_patch", patch_text=PATCH))
    if len(done) == 2:
        return answer("", call(2, "run_command", command=COMMAND, timeout_seconds=None, cwd=None, shell=None))
    return answer("Đã sửa dòng đầu README và lệnh kiểm chạy được.")


class OpenAIHandler(BaseHTTPRequestHandler):
    def _record(self, body):
        self.server.requests.append({"method": self.command, "path": self.path,
                                     "auth": self.headers.get("Authorization"), "body": body})

    def _json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 - tên do http.server quy định
        self._record(None)
        self._json(*self.server.models)

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self._record(body)
        status, payload = self.server.reply(body)
        if payload == "hold":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b": waiting\n\n")
            self.wfile.flush()
            self.server.hold.wait(5)
            return
        if status == 302:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/khac")
            self.end_headers()
            return
        if status != 200:
            self._json(status, {"error": payload})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in payload:
            self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode())

    def log_message(self, *args):
        pass


def serve(handler, **attributes):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.requests = []
    for name, value in attributes.items():
        setattr(server, name, value)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    return server


@pytest.fixture
def openai():
    server = serve(OpenAIHandler, reply=workflow,
                   models=(200, {"data": [{"id": "gpt-6-luna"}, {"id": "gpt-6.1-sol"}, {"id": "dall-e-9"}]}))
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def peto_server():
    """Máy chủ Peto giả: hết bước trong ngày, /step luôn từ chối. Đếm mọi lượt gọi tới nó."""
    def reply(path, body):
        if path == "/api/agent/me":
            return 200, {"account": "Bình", "steps_used": 200, "steps_limit": 200, "agent_features": [],
                         "models": [{"key": "peto", "label": "Peto", "step_cost": 1}]}
        return 429, "Hôm nay đã dùng hết bước của Peto Agent."

    server = serve(PetoHandler, reply=reply)
    yield server
    server.shutdown()
    server.server_close()


def connect(openai, models=("gpt-6-luna",)):
    item = connections.add("openai", KEY, endpoint=f"{openai.url}/v1", models=models)
    settings = config.load()
    settings["selection"] = {"source": "openai-key", "connection": item.id, "model": models[0]}
    config.save(settings)
    return item


def readme(project):
    (project / "README.md").write_bytes("# Dự án thử\r\nnội dung\r\n".encode())


def responses(openai, purpose=None):
    found = [request for request in openai.requests if request["path"] == "/v1/responses"]
    return [request for request in found if purpose is None or purpose_of(request["body"]) == purpose]


def wait_for(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.02)
    return predicate()


def direct_session(project, openai, *, max_steps=None, ui=None):
    """Phiên dùng nguồn trực tiếp như cli.session dựng, nhưng gọi thẳng từ test."""
    item = connect(openai)
    work = Session(cli._offline_client({}), Workspace(project), ui or FakeUI(), max_steps=max_steps,
                   log=TaskLog(project.name))
    direct = [*FEATURES, *(feature for feature in NEW_FEATURES if feature in cli.BUNDLE_FEATURES)]
    work.source_features = {"peto": list(FEATURES), "openai-key": direct}
    work.configure_models(cli._budget_rows(cli._direct_models()))
    work.select("openai-key", "gpt-6-luna", connection=item.id, step_cost=0)
    work.supported_efforts = ["low", "medium", "high"]
    return work


def leaked(root: Path) -> list[str]:
    """Tệp dưới ``root`` có chứa khóa (dạng UTF-8 hay UTF-16 của Windows)."""
    needles = (KEY.encode("utf-8"), KEY.encode("utf-16-le"))
    return [str(path) for path in root.rglob("*") if path.is_file()
            and any(needle in path.read_bytes() for needle in needles)]


def test_direct_workflow_needs_no_peto_login_and_spends_no_peto_steps(project, openai, agent_home, monkeypatch):
    readme(project)
    connect(openai)
    monkeypatch.chdir(project)
    ui = FakeUI(answers=["Sửa dòng đầu README", "/usage", "/exit"])
    assert cli.session(ui) == 0
    assert (project / "README.md").read_bytes() == "# Dự án thử (Peto)\r\nnội dung\r\n".encode()
    assert "Đã sửa dòng đầu README và lệnh kiểm chạy được." in ui.text
    assert "peto login" not in ui.text and "chưa đăng nhập" not in ui.text
    assert "khóa riêng nên không tính bước Peto" in ui.text, "/usage chạy được khi không có máy chủ Peto"
    assert "Khóa riêng trong phiên này · OpenAI: " in ui.text and "từ cache" in ui.text
    assert "platform.openai.com/usage" in ui.text, "token khóa riêng là số OpenAI trả, không phải hóa đơn"
    work = responses(openai, "work")
    assert len(work) >= 4
    for request in work:
        body = request["body"]
        assert request["auth"] == f"Bearer {KEY}"
        assert body["model"] == "gpt-6-luna" and body["store"] is False and body["stream"] is True
        assert body["max_output_tokens"] <= 16_000 and body["reasoning"] == {"effort": "medium"}
        names = {tool["name"] for tool in body["tools"]}
        # Model GPT dùng apply_patch thay edit_file, như khi đi qua máy chủ Peto; không có tìm web ở nguồn này.
        assert "apply_patch" in names and "edit_file" not in names and "update_plan" not in names
        assert not any(tool.get("type") == "web_search" for tool in body["tools"])
        assert "context" not in body and "effort" not in body, "trường riêng của máy chủ Peto không gửi cho OpenAI"
        assert KEY not in json.dumps(body)
    # Đặt tên hội thoại cũng đi qua khóa riêng, không về máy chủ Peto.
    assert wait_for(lambda: responses(openai, "title"))
    title = responses(openai, "title")[0]["body"]
    assert title["model"] == "gpt-6-luna" and title["reasoning"] == {"effort": "low"} and title["tools"] == []
    assert wait_for(lambda: history.load(project, cli.LOCAL_SERVER) is not None
                    and history.load(project, cli.LOCAL_SERVER).title == "Sửa dòng đầu README")
    saved = history.load(project, cli.LOCAL_SERVER)
    assert saved.source == "openai-key" and saved.model == "gpt-6-luna"
    assert leaked(agent_home) == [] and leaked(project) == []


def test_peto_out_of_steps_and_vps_requests_stay_at_one_account_check(project, openai, peto_server, monkeypatch):
    readme(project)
    config.save({"server": peto_server.url, "token": "peto_token_thu"})
    connect(openai)
    monkeypatch.chdir(project)
    ui = FakeUI(answers=["Sửa dòng đầu README", "/exit"])
    assert cli.session(ui) == 0
    assert "Đã sửa dòng đầu README" in ui.text and "hết bước" not in ui.text
    assert wait_for(lambda: responses(openai, "title"))
    # Lượt gọi duy nhất tới VPS là đọc tài khoản lúc mở phiên; không một bước model nào đi qua /step.
    assert [(request["path"]) for request in peto_server.requests] == ["/api/agent/me"]
    assert all(KEY not in json.dumps(request) for request in peto_server.requests)


def test_vps_offline_still_starts_resumes_and_runs(project, openai, monkeypatch):
    readme(project)
    closed = ThreadingHTTPServer(("127.0.0.1", 0), PetoHandler)
    offline = f"http://127.0.0.1:{closed.server_address[1]}"
    closed.server_close()
    config.save({"server": offline, "token": "peto_token_thu"})
    connect(openai)
    monkeypatch.chdir(project)
    first = FakeUI(answers=["Sửa dòng đầu README", "/exit"])
    assert cli.session(first) == 0
    assert "Chưa lấy được tài khoản Peto" in first.text and "vẫn làm việc bình thường" in first.text
    assert "Đã sửa dòng đầu README" in first.text
    assert wait_for(lambda: history.load(project, offline) is not None
                    and history.load(project, offline).title == "Sửa dòng đầu README")
    openai.requests.clear()
    second = FakeUI(answers=["/resume", "Làm tiếp nhé", "/exit"])
    assert cli.session(second) == 0
    assert "Đã mở lại hội thoại" in second.text
    step = responses(openai, "work")[0]["body"]
    assert step["input"][0] == {"type": "message", "role": "user", "content": "Sửa dòng đầu README"}
    assert step["input"][-1] == {"type": "message", "role": "user", "content": "Làm tiếp nhé"}


def test_every_side_purpose_uses_the_direct_source(project, openai):
    readme(project)
    ui = FakeUI()
    work = direct_session(project, openai, ui=ui)
    work.auto_title = False
    work.run_task("Sửa dòng đầu README")
    assert work.side_question("Đang làm gì?") == "Peto đang sửa README."
    work.compact()
    assert history.SUMMARY_NOTE in json.dumps(work.items, ensure_ascii=False)
    btw = responses(openai, "btw")[0]["body"]
    compact = responses(openai, "compact")[0]["body"]
    assert btw["tools"] == [] and btw["reasoning"] == {"effort": "low"}
    assert compact["tools"] == [] and compact["max_output_tokens"] <= 16_000
    assert all(request["auth"] == f"Bearer {KEY}" for request in openai.requests)


def test_wrapup_and_explore_run_on_the_direct_source(project, openai):
    readme(project)

    def reply(body):
        purpose = purpose_of(body)
        if purpose == "explore":
            if not outputs(body):
                return answer("", call(10, "read_file", path="README.md", start_line=None, end_line=None))
            return answer("README có hai dòng; dòng đầu là tiêu đề dự án.")
        if purpose == "wrapup":
            return answer("Đã đủ bước: đã khám phá README, chưa sửa gì.")
        done = outputs(body)
        if not done:
            return answer("", call(0, "explore", task="Đọc README và nói nó có gì", depth="quick"))
        return answer("", call(len(done), "list_files", path=".", depth=None))

    openai.reply = reply
    ui = FakeUI()
    work = direct_session(project, openai, max_steps=2, ui=ui)
    work.auto_title = False
    work.run_task("Xem dự án có gì")
    explore = responses(openai, "explore")
    assert len(explore) == 2 and explore[0]["body"]["reasoning"] == {"effort": "low"}
    assert {tool["name"] for tool in explore[0]["body"]["tools"]} == {"list_files", "find_files", "search_files",
                                                                         "read_file"}
    result = next(json.loads(item["output"]) for item in work.items
                  if item.get("type") == "function_call_output" and item["call_id"] == "call_0")
    assert result["summary"] == "README có hai dòng; dòng đầu là tiêu đề dự án." and result["files_read"] == ["README.md"]
    wrapup = responses(openai, "wrapup")
    assert len(wrapup) == 1 and wrapup[0]["body"].get("tool_choice") == "none"
    assert "Đã đủ bước: đã khám phá README" in ui.text


@pytest.mark.parametrize("status,error,expected,category", [
    (401, {"code": "invalid_api_key", "message": "Incorrect API key provided: sk-peto****Qx7"},
     "không dùng được (sai hoặc đã bị thu hồi). Chạy peto connect openai", "authentication"),
    (429, {"code": "insufficient_quota", "type": "insufficient_quota", "message": "You exceeded your current quota"},
     "đã hết hạn mức hoặc hết tiền", "quota"),
    (404, {"code": "model_not_found", "message": "The model does not exist"}, "không có model gpt-6-luna", "capability"),
])
def test_key_and_billing_errors_belong_to_the_direct_source(project, openai, status, error, expected, category):
    readme(project)
    openai.reply = lambda body: (status, error)
    ui = FakeUI()
    work = direct_session(project, openai, ui=ui)
    work.auto_title = False
    work.run_task("Sửa README")
    assert expected in ui.text
    assert "peto login" not in ui.text and "máy chủ Peto" not in ui.text and "sk-peto" not in ui.text
    assert len(responses(openai)) == 1, "lỗi khóa hay tiền không được tự gửi lại"
    assert not work.can_retry
    logged = [json.loads(line) for line in work.log.path.read_text(encoding="utf-8").splitlines()]
    assert [entry["category"] for entry in logged if entry["kind"] == "error"] == [category]
    assert classify(code=category) == category


def test_rate_limits_and_outages_retry_a_bounded_number_of_times(project, openai, monkeypatch):
    readme(project)
    monkeypatch.setattr(loop, "RETRY_WAITS", (0, 0, 0))
    attempts = []

    def reply(body):
        attempts.append(1)
        if len(attempts) == 1:
            return 429, {"code": "rate_limit_exceeded", "message": "Rate limit reached"}
        if len(attempts) == 2:
            return 503, {"message": "overloaded"}
        return answer("Xong.")

    openai.reply = reply
    ui = FakeUI()
    work = direct_session(project, openai, ui=ui)
    work.auto_title = False
    work.run_task("Chào")
    assert len(attempts) == 3 and "Xong." in ui.text


def test_ctrl_c_during_a_silent_direct_stream_stops_at_once_without_retry(project, openai, monkeypatch):
    from peto_agent.providers import transport

    readme(project)
    openai.hold = threading.Event()
    openai.reply = lambda body: (200, "hold")
    original = transport.ProviderHTTP.stream

    def interrupted(self, path, body, **options):
        def cancel():
            raise KeyboardInterrupt
        return original(self, path, body, timeout=options.get("timeout", 600.0), on_idle=cancel)

    monkeypatch.setattr(transport.ProviderHTTP, "stream", interrupted)
    ui = FakeUI()
    work = direct_session(project, openai, ui=ui)
    work.auto_title = False
    try:
        started = time.monotonic()
        work.run_task("Xin chào")
        assert time.monotonic() - started < 2
        assert not work.can_retry and "Đã dừng yêu cầu" in ui.text
        assert len(responses(openai)) == 1
    finally:
        openai.hold.set()


def test_redirects_are_not_followed_and_the_key_stays_at_the_connection_endpoint(project, openai):
    readme(project)
    openai.reply = lambda body: (302, {})
    ui = FakeUI()
    work = direct_session(project, openai, ui=ui)
    work.auto_title = False
    work.run_task("Chào")
    assert "không theo để giữ an toàn cho khóa" in ui.text
    assert [request["path"] for request in openai.requests] == ["/v1/responses"]


def test_secret_never_reaches_history_journal_logs_or_export(project, openai, agent_home):
    readme(project)
    work = direct_session(project, openai)
    work.auto_title = False
    work.run_task("Sửa dòng đầu README")
    work.save()
    text = export.markdown(work.items, title="Thử", model=work.model, folder=str(project), when=history_time(),
                           version="0")
    assert KEY not in text
    assert leaked(agent_home) == [] and leaked(project) == []
    stored = next((agent_home / "credentials").glob("*.bin")).read_bytes()
    assert KEY.encode() not in stored and KEY.encode("utf-16-le") not in stored, "khóa lưu dạng DPAPI, không bản rõ"
    assert credentials.load(connections.load_all()[0].id) == KEY
    assert KEY not in json.dumps(dict(__import__("os").environ)), "khóa không vào biến môi trường của tiến trình con"


def history_time():
    from datetime import datetime
    return datetime(2026, 10, 20, 9, 0)


def test_connect_checks_the_key_saves_it_and_selects_the_cheapest_model(openai, agent_home):
    ui = FakeUI()
    assert cli.connect(ui, "openai", endpoint=f"{openai.url}/v1", read_secret=lambda prompt: KEY + "\n") == 0
    assert [request["path"] for request in openai.requests] == ["/v1/models"]
    assert openai.requests[0]["auth"] == f"Bearer {KEY}"
    item = connections.load_all()[0]
    assert item.models == ("gpt-6-luna", "gpt-6.1-sol"), "chỉ giữ model danh mục Peto biết giới hạn"
    assert config.load()["selection"] == {"source": "openai-key", "connection": item.id, "model": "gpt-6-luna"}
    assert credentials.load(item.id) == KEY and KEY not in ui.text and leaked(agent_home) == []
    listed = FakeUI()
    assert cli.list_connections(listed) == 0 and f"{item.id}" in listed.text and "đang dùng" in listed.text
    status = FakeUI()
    assert cli.status(status) == 0, "chưa đăng nhập Peto mà đã chọn khóa riêng thì status vẫn thành công"
    assert "Nguồn đang chọn: GPT-6 Luna" in status.text and "peto login" not in status.text
    gone = FakeUI()
    assert cli.disconnect(gone, item.id) == 0
    assert connections.load_all() == [] and "selection" not in config.load()
    with pytest.raises(credentials.CredentialError):
        credentials.load(item.id)


def test_connect_saves_nothing_when_the_key_is_refused_or_the_endpoint_is_foreign(openai, agent_home):
    openai.models = (401, {"error": {"code": "invalid_api_key", "message": "bad"}})
    ui = FakeUI()
    assert cli.connect(ui, "openai", endpoint=f"{openai.url}/v1", read_secret=lambda prompt: KEY) == 1
    assert "OpenAI không nhận khóa này" in ui.text and "Chưa lưu gì" in ui.text
    assert connections.load_all() == [] and not (agent_home / "credentials").exists()
    foreign = FakeUI()
    asked = []
    assert cli.connect(foreign, "openai", endpoint="https://api.example.com/v1",
                       read_secret=lambda prompt: asked.append(prompt) or KEY) == 2
    assert asked == [] and "không được phép" in foreign.text
    for bad in ("https://api.example.com/v1", "https://api.openai.com/v1?x=1", "http://api.openai.com/v1",
                "https://user:pass@api.openai.com/v1"):
        assert not connections.endpoint_allowed("openai", bad)
    assert connections.endpoint_allowed("openai", "https://api.openai.com/v1")
    with pytest.raises(ValueError):
        ProviderHTTP("http://example.com/v1", {})


def test_model_command_moves_between_peto_and_the_direct_source(project, openai, monkeypatch):
    from test_loop_client import demo_reply

    peto = serve(PetoHandler, reply=lambda path, body: (200, {
        "account": "Bình", "steps_used": 1, "steps_limit": 200, "agent_features": [],
        "models": [{"key": "peto", "label": "Peto", "step_cost": 1}]}) if path == "/api/agent/me"
        else demo_reply(path, body))
    try:
        readme(project)
        config.save({"server": peto.url, "token": "peto_token_thu"})
        item = connections.add("openai", KEY, endpoint=f"{openai.url}/v1", models=("gpt-6-luna",))
        monkeypatch.chdir(project)
        ui = FakeUI(answers=["/models", "/connect", "/model gpt-6-luna", "Chào", "/model peto", "/exit"])
        assert cli.session(ui) == 0
        assert "gpt-6-luna" in ui.text and "tiền tính vào tài khoản OpenAI của bạn" in ui.text
        assert "    gpt-6-luna  GPT-6 Luna · OpenAI (khóa API riêng) · không tính bước Peto" in ui.text
        assert "chạy peto connect openai" in ui.text and item.id in ui.text, "/connect không có khung nổi thì chỉ cách"
        assert "Khóa riêng trong phiên này" not in ui.text
        assert responses(openai, "work") and not [r for r in peto.requests if r["path"] == "/api/agent/step"]
        settings = config.load()
        assert "model" not in settings and "selection" not in settings, "đổi trong phiên không đổi mặc định (M4)"
        assert settings["recent_models"] == ["peto||peto", f"openai-key|{item.id}|gpt-6-luna"]
        settings = config.load()
        settings["selection"] = {"source": "openai-key", "connection": item.id, "model": "gpt-6-luna"}
        config.save(settings)
        again = FakeUI(answers=["/exit"])
        assert cli.session(again) == 0 and "GPT-6 Luna" in again.text
    finally:
        peto.shutdown()
        peto.server_close()


def test_bundle_matches_the_backend_sources():
    path = Path(__file__).resolve().parents[1] / "tools" / "make_bundle.py"
    spec = importlib.util.spec_from_file_location("make_bundle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected, current = module.render(), module.current()
    assert sorted(expected) == sorted(current)
    assert [name for name in expected if expected[name] != current[name]] == []


def test_every_tool_the_direct_source_offers_has_a_handler_with_matching_parameters(project):
    tools = Tools(Workspace(project), FakeUI())
    declared = [*FEATURES, *(feature for feature in NEW_FEATURES if feature in cli.BUNDLE_FEATURES)]
    assert set(declared) - set(cli.BUNDLE_FEATURES) == set(), "mọi khả năng khai báo đều có trong bản chép"
    schemas = []
    for service in ("openai", "anthropic", "xai"):
        schemas += assembly.prepare({"features": declared}, service=service, web_search=False, clock="").tools
    schemas += assembly.prepare({"features": declared, "purpose": "explore"}, service="openai", web_search=False,
                                clock="").tools
    for schema in schemas:
        name = schema["name"]
        handler = tools._handlers.get(name)
        assert handler is not None, f"công cụ {name} không có handler"
        parameters = set(inspect.signature(handler).parameters)
        assert set(schema["parameters"]["properties"]) <= parameters, name

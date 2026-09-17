"""Vòng làm việc với máy chủ giả trên 127.0.0.1, và các quy tắc an toàn của client."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import FakeUI

from peto_agent import __main__ as cli
from peto_agent import config
from peto_agent.client import ApiError, Client, normalize_server
from peto_agent.loop import Session
from peto_agent.workspace import Workspace

COMMAND = f'"{sys.executable}" -c "print(\'ok\')"'


def message(text: str) -> dict:
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def call(stage: int, name: str, **arguments) -> dict:
    return {"type": "function_call", "call_id": f"call_{stage}", "name": name, "arguments": json.dumps(arguments)}


def demo_reply(path: str, body: dict):
    """Kịch bản giống mock của máy chủ: đọc README → sửa dòng đầu → chạy lệnh → tóm tắt."""
    if path != "/api/agent/step":
        return 404, "Không có"
    results = [json.loads(item["output"]) for item in body["input"] if item.get("type") == "function_call_output"]
    events = [{"type": "meta", "steps_used": len(results) + 1, "steps_limit": 200}, {"type": "thinking", "text": "…"}]
    if not results:
        text, calls = "Để Peto xem README.", [call(0, "read_file", path="README.md", start_line=None, end_line=None)]
    elif len(results) == 1:
        first = results[0]["content"].splitlines()[0]
        text, calls = "Sửa dòng đầu nhé.", [call(1, "edit_file", path="README.md", old_text=first, new_text=first + " (Peto)")]
    elif len(results) == 2 and results[1].get("ok"):
        text, calls = "Chạy thử lệnh.", [call(2, "run_command", command=COMMAND, timeout_seconds=None)]
    elif len(results) == 2:
        text, calls = "Bạn chưa cho sửa nên Peto dừng.", []
    else:
        text, calls = "Xong rồi nè.", []
    usage = {"input_tokens": 12000 + 2000 * len(results), "output_tokens": 400}
    return 200, [*events, {"type": "delta", "text": text},
                 {"type": "done", "output": [message(text), *calls], "usage": usage}]


class Handler(BaseHTTPRequestHandler):
    def _reply(self, body: dict) -> None:
        self.server.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.com/")
            self.end_headers()
            return
        status, payload = self.server.reply(self.path, body)
        if status != 200 or not isinstance(payload, list):
            data = json.dumps(payload if status == 200 else {"detail": payload}, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in payload:
            self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())

    def do_POST(self):  # noqa: N802 - tên do http.server quy định
        length = int(self.headers.get("Content-Length") or 0)
        self._reply(json.loads(self.rfile.read(length) or b"{}"))

    def do_GET(self):  # noqa: N802
        self._reply({})

    def log_message(self, *args):
        pass


@pytest.fixture
def peto():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.reply = demo_reply
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server
    server.shutdown()
    server.server_close()


def start(project, peto, answers):
    (project / "README.md").write_bytes("# Dự án thử\r\nnội dung\r\n".encode())
    ui = FakeUI(answers=answers)
    return Session(Client(peto.url, "peto_token_thu"), Workspace(project), ui), ui


def assert_every_call_has_output(items):
    calls = {item["call_id"] for item in items if item.get("type") == "function_call"}
    outputs = {item["call_id"] for item in items if item.get("type") == "function_call_output"}
    assert calls == outputs


def test_task_reads_edits_runs_and_summarizes(project, peto):
    session, ui = start(project, peto, ["y", "y"])
    session.run_task("Sửa README")
    assert (project / "README.md").read_bytes() == "# Dự án thử (Peto)\r\nnội dung\r\n".encode()
    assert "Peto › Xong rồi nè." in ui.text
    assert "· xong" in ui.text
    assert "  Xong trong 0 giây · sửa 1 tệp · chạy 1 lệnh · hội thoại 18k token · hôm nay còn 196/200 bước" in ui.text
    assert "Peto đang nghĩ" not in ui.text, "không có màu thì không vẽ dòng trạng thái tạm"
    assert all(request["body"]["effort"] == "medium" for request in peto.requests)
    assert all(request["auth"] == "Bearer peto_token_thu" for request in peto.requests)
    assert len(peto.requests) == 4
    assert_every_call_has_output(session.items)
    assert peto.requests[0]["body"]["context"]["project"] == "project"


def test_refusing_an_edit_stops_without_changes(project, peto):
    session, ui = start(project, peto, ["n"])
    session.run_task("Sửa README")
    assert (project / "README.md").read_bytes() == "# Dự án thử\r\nnội dung\r\n".encode()
    assert "Bạn chưa cho sửa nên Peto dừng." in ui.text
    assert session.tools.commands == []
    assert_every_call_has_output(session.items)


def test_ctrl_c_at_a_question_leaves_a_valid_history(project, peto):
    session, ui = start(project, peto, [KeyboardInterrupt()])
    session.run_task("Sửa README")
    assert "Đã dừng yêu cầu" in ui.text
    assert (project / "README.md").read_bytes() == "# Dự án thử\r\nnội dung\r\n".encode()
    assert_every_call_has_output(session.items)
    assert json.loads(session.items[-1]["output"])["error"].startswith("Người dùng đã dừng")


def test_server_errors_are_shown_and_stop_the_task(project, peto):
    peto.reply = lambda path, body: (200, [{"type": "error", "message": "Hết bước hôm nay."}])
    session, ui = start(project, peto, [])
    session.run_task("Sửa README")
    assert "Hết bước hôm nay." in ui.text
    peto.reply = lambda path, body: (429, "Hôm nay bạn đã dùng hết 200 bước Peto Agent.")
    session.run_task("Thử lại")
    assert "dùng hết 200 bước" in ui.text


def test_client_rules(peto):
    assert normalize_server("https://peto.example.com/") == "https://peto.example.com"
    assert normalize_server("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    for bad in ["http://peto.example.com", "https://user:pw@peto.example.com", "https://peto.example.com/app", "ftp://x"]:
        with pytest.raises(ValueError):
            normalize_server(bad)
    with pytest.raises(ApiError) as redirect:
        Client(peto.url).json("POST", "/redirect", {}, auth=False)
    assert redirect.value.status == 302 and "chuyển hướng" in redirect.value.message
    with pytest.raises(ApiError) as no_token:
        Client(peto.url).json("GET", "/api/agent/me")
    assert no_token.value.status == 401 and peto.requests == [{"path": "/redirect", "auth": None, "body": {}}]


def test_login_uses_the_server_bundled_by_the_installer(peto, tmp_path, monkeypatch):
    assert config.default_server() == ""
    bundled = tmp_path / "default_server.txt"
    bundled.write_text(f"{peto.url}\n", encoding="utf-8")
    monkeypatch.setattr(config, "DEFAULT_SERVER_FILE", bundled)
    monkeypatch.delenv("PETO_AGENT_SERVER", raising=False)

    def reply(path, body):
        if path == "/api/agent/device/start":
            return 200, {"device_code": "bi-mat", "user_code": "KXMT-4P2Q", "interval": 1, "expires_in": 60}
        if path == "/api/agent/device/token":
            return 200, {"token": "peto_moi", "device_name": "MAY-THU", "account": "Bình"}
        return 404, "Không có"

    peto.reply = reply
    ui = FakeUI()
    assert cli.login(ui, None) == 0
    assert config.load()["server"] == peto.url
    assert [request["path"] for request in peto.requests] == ["/api/agent/device/start", "/api/agent/device/token"]
    assert f"{peto.url}/?agent_code=KXMT-4P2Q" in ui.text


def test_effort_is_remembered_and_resume_reopens_the_last_conversation(project, peto, monkeypatch):
    def reply(path, body):
        if path == "/api/agent/me":
            return 200, {"account": "Bình", "device_name": "MAY-THU", "steps_used": 4, "steps_limit": 200,
                         "tokens_used": 45210, "default_effort": "low"}
        return demo_reply(path, body)

    peto.reply = reply
    config.save({"server": peto.url, "token": "peto_token_thu"})
    (project / "README.md").write_bytes("# Dự án thử\r\nnội dung\r\n".encode())
    monkeypatch.chdir(project)

    first = FakeUI(answers=["/effort", "/effort cao", "/efort", "Sửa README", "y", "y", "/thoat"])
    assert cli.session(first) == 0
    assert "mức thấp" in first.text and "Mức suy nghĩ: thấp." in first.text
    assert "Đã chuyển sang mức cao; mỗi bước tính 2 bước." in first.text
    assert "Không có lệnh này" in first.text and "gõ /resume" not in first.text
    assert config.load()["effort"] == "high"
    steps = [request for request in peto.requests if request["path"] == "/api/agent/step"]
    assert len(steps) == 4 and all(request["body"]["effort"] == "high" for request in steps)

    peto.requests.clear()
    second = FakeUI(answers=["/resume", "Làm tiếp nhé", "/thoat"])
    assert cli.session(second) == 0
    assert "mức cao" in second.text and "(5 tin) · gõ /resume để mở lại." in second.text
    assert "Đã mở lại hội thoại lúc" in second.text
    assert "    Bạn › Sửa README" in second.text and "    Peto › Xong rồi nè." in second.text
    step = next(request for request in peto.requests if request["path"] == "/api/agent/step")
    assert step["body"]["input"][0] == {"type": "message", "role": "user", "content": "Sửa README"}
    assert step["body"]["input"][-1] == {"type": "message", "role": "user", "content": "Làm tiếp nhé"}

    status = FakeUI()
    assert cli.status(status) == 0
    assert "· mức cao · hôm nay còn 196/200 bước · đã dùng 45k token." in status.text

"""Vòng làm việc với máy chủ giả trên 127.0.0.1, và các quy tắc an toàn của client."""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import FakeUI

from peto_agent import __main__ as cli
from peto_agent import __version__, config, history
from peto_agent.client import ApiError, Client, normalize_server
from peto_agent.images import Image
from peto_agent.loop import OLD_IMAGE_NOTE, Session, TaskLog
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
        if isinstance(payload, bytes):
            self.send_response(status)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
            if hold := getattr(self.server, "hold", None):
                hold.wait(3)
            return
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
    # Máy bận thì vòng này có thể quá nửa giây, nên không đòi đúng "0 giây".
    assert re.search(r"  Xong trong \d+ giây · sửa 1 tệp · chạy 1 lệnh · hội thoại 18k token · hôm nay còn 196/200 bước",
                     ui.text)
    assert "Peto đang nghĩ" not in ui.text, "không có màu thì không vẽ dòng trạng thái tạm"
    assert all(request["body"]["effort"] == "medium" for request in peto.requests)
    assert all(request["auth"] == "Bearer peto_token_thu" for request in peto.requests)
    assert len(peto.requests) == 5, "printing ok is not a project check; ask for verification once"
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
    assert len(steps) == 5 and all(request["body"]["effort"] == "high" for request in steps)

    peto.requests.clear()
    second = FakeUI(answers=["/resume", "Làm tiếp nhé", "/thoat"])
    assert cli.session(second) == 0
    assert "mức cao" in second.text and "(7 tin) · gõ /resume để mở lại." in second.text
    assert "Đã mở lại hội thoại lúc" in second.text
    assert "    Bạn › Sửa README" in second.text and "    Peto › Xong rồi nè." in second.text
    step = next(request for request in peto.requests if request["path"] == "/api/agent/step")
    assert step["body"]["input"][0] == {"type": "message", "role": "user", "content": "Sửa README"}
    assert step["body"]["input"][-1] == {"type": "message", "role": "user", "content": "Làm tiếp nhé"}

    status = FakeUI()
    assert cli.status(status) == 0
    assert f"· mức cao · hôm nay còn 196/200 bước · đã dùng 45k token · peto {__version__}." in status.text
    assert "Có bản peto mới" not in status.text, "máy chủ không báo phiên bản thì không nhắc"


def test_commands_usage_and_update_notice(project, peto, monkeypatch):
    major, minor, _ = (int(part) for part in __version__.split("."))
    # Số phụ hai chữ số: so theo chuỗi thì bản mới này lại "nhỏ hơn", so theo từng số mới đúng.
    newer = f"{major}.{minor + 7}.0"
    me = {"account": "Bình", "device_name": "MAY-THU", "steps_used": 10, "steps_limit": 200, "tokens_used": 1234,
          "default_effort": "medium", "cli_version": newer}

    def reply(path, body):
        if path == "/api/agent/me":
            return 200, me
        text = "Để Peto xem route đó."
        return 200, [{"type": "delta", "text": text},
                     {"type": "done", "output": [message(text)], "usage": {"input_tokens": 900, "output_tokens": 100}}]

    peto.reply = reply
    config.save({"server": peto.url, "token": "peto_token_thu"})
    monkeypatch.chdir(project)

    ui = FakeUI(answers=["/help", "/api/users lỗi 500", "/usage", "/moi thêm", "/xyz", "/thoát", "/usage"])
    assert cli.session(ui) == 0
    notice = (f"Có bản peto mới {newer} (máy này đang dùng {__version__}). Thoát peto rồi chạy lệnh cài để cập nhật:\n"
              f"  irm {peto.url}/install.ps1 | iex\n")
    assert notice in ui.text, "so phiên bản theo từng số"
    assert f"Peto Agent {__version__} · project · Bình" in ui.text and "/help xem các lệnh" in ui.text
    assert re.search(r"/effort\s+Xem hoặc đổi mức suy nghĩ: thap, vua, cao", ui.text)
    steps = [request["body"] for request in peto.requests if request["path"] == "/api/agent/step"]
    assert [step["input"][0]["content"] for step in steps] == ["/api/users lỗi 500"], "đường dẫn API không phải lệnh"
    assert "  Hôm nay còn 190/200 bước · đã dùng 1.2k token · hội thoại này 1k token · Peto · mức vừa." in ui.text
    assert "Lệnh /moi không nhận thêm gì phía sau." in ui.text and "Không có lệnh này" in ui.text
    assert ui.answers == ["/usage"], "/thoát gõ có dấu vẫn thoát"

    me["cli_version"] = __version__
    same = FakeUI(answers=["/thoat"])
    assert cli.session(same) == 0
    assert "Có bản peto mới" not in same.text


def test_pasted_images_are_sent_and_only_the_last_four_are_kept(project, peto):
    def reply(path, body):
        return 200, [{"type": "delta", "text": "Đã xem ảnh."}, {"type": "done", "output": [message("Đã xem ảnh.")],
                                                                "usage": {"input_tokens": 3000, "output_tokens": 20}}]

    peto.reply = reply
    shot = Image(b"\x89PNG\r\n\x1a\nanh-chup", "image/png", 1920, 1080)
    log = TaskLog("project")
    session = Session(Client(peto.url, "peto_token_thu"), Workspace(project), FakeUI(), log=log)
    session.run_task("giao diện lỗi như [Ảnh 1]", [(1, shot)])
    assert peto.requests[-1]["body"]["input"][0]["content"] == [
        {"type": "input_text", "text": "giao diện lỗi như [Ảnh 1]"},
        {"type": "input_text", "text": "[Ảnh 1]"},
        {"type": "input_image", "image_url": shot.data_url(), "detail": "high"},
    ]

    for number in range(2, 6):
        session.run_task(f"còn đây nữa [Ảnh {number}]", [(number, shot)])
    sent = peto.requests[-1]["body"]["input"]
    parts = [part for item in sent if isinstance(item.get("content"), list) for part in item["content"]]
    assert sum(part["type"] == "input_image" for part in parts) == 4
    assert sent[0]["content"][1:] == [{"type": "input_text", "text": "[Ảnh 1]"},
                                      {"type": "input_text", "text": OLD_IMAGE_NOTE}], "ảnh cũ nhất thành ghi chú"
    assert history.recap(session.items) == [("Bạn", "còn đây nữa [Ảnh 5]"), ("Peto", "Đã xem ảnh.")]
    logged = log.path.read_text(encoding="utf-8")
    assert '"images": 1' in logged and "base64" not in logged, "nhật ký không chứa dữ liệu ảnh"


PETO = {"key": "peto", "label": "Peto", "description": "Mặc định", "step_cost": 1}
LUNA = {"key": "luna", "label": "5.6 Luna", "description": "Nhanh, của OpenAI", "step_cost": 1}
SOL = {"key": "sol", "label": "5.6 Sol", "description": "Mạnh nhất, của OpenAI", "step_cost": 4}


def test_model_command_switches_models_and_remembers_the_choice(project, peto, monkeypatch):
    me = {"account": "Bình", "device_name": "MAY-THU", "steps_used": 10, "steps_limit": 200, "tokens_used": 0,
          "default_effort": "medium", "models": [PETO, LUNA, SOL]}

    def reply(path, body):
        if path == "/api/agent/me":
            return 200, me
        text = "Xong rồi nè."
        return 200, [{"type": "delta", "text": text},
                     {"type": "done", "output": [message(text)], "usage": {"input_tokens": 900, "output_tokens": 100}}]

    peto.reply = reply
    config.save({"server": peto.url, "token": "peto_token_thu"})
    monkeypatch.chdir(project)

    ui = FakeUI(answers=["/model", "/model terra", "/model Luna", "làm việc", "/effort cao", "/model 5.6 sol",
                         "/usage", "/thoat"])
    assert cli.session(ui) == 0
    assert "Peto Agent" in ui.text and "· Bình · Peto · mức vừa ·" in ui.text
    assert "  Model: Peto. Đổi bằng /model peto, /model luna, /model sol." in ui.text
    assert "    sol   5.6 Sol · Mạnh nhất, của OpenAI · tính 4 bước" in ui.text
    assert "Tài khoản này không dùng được model đó." in ui.text
    assert "Đã chuyển sang 5.6 Luna." in ui.text and "Đã chuyển sang mức cao; mỗi bước tính 2 bước." in ui.text
    assert "Đã chuyển sang 5.6 Sol; mỗi bước tính 8 bước." in ui.text
    assert "· 5.6 Sol · mức cao, mỗi bước tính 8 bước." in ui.text
    steps = [request["body"] for request in peto.requests if request["path"] == "/api/agent/step"]
    assert [step["model"] for step in steps] == ["luna"]
    assert config.load()["model"] == "sol"

    me["models"] = [PETO, LUNA]
    again = FakeUI(answers=["/thoat"])
    assert cli.session(again) == 0
    assert "Tài khoản này không còn dùng được model sol nên peto dùng Peto." in again.text
    assert "· Bình · Peto · mức cao ·" in again.text


def test_switching_models_drops_what_only_the_old_model_can_read(project, peto):
    session = Session(Client(peto.url, "peto_token_thu"), Workspace(project), FakeUI())
    session.items = [
        {"type": "message", "role": "user", "content": "sửa README"},
        {"type": "reasoning", "id": "rs_1", "encrypted_content": "bí mật của xAI"},
        {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "read_file", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "{}"},
        {"type": "message", "id": "msg_1", "role": "assistant", "content": [{"type": "output_text", "text": "Xong"}]},
    ]
    kept = list(session.items)
    session.set_model("peto")
    assert session.items == kept, "chọn lại đúng model đang dùng thì không đụng hội thoại"
    session.set_model("sol", 4)
    assert session.items == [
        {"type": "message", "role": "user", "content": "sửa README"},
        {"type": "function_call", "call_id": "call_1", "name": "read_file", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "{}"},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Xong"}]},
    ]
    assert (session.model, session.model_step_cost) == ("sol", 4)

    session.resume(kept, model="sol")
    assert session.items == kept, "mở lại hội thoại của đúng model thì giữ nguyên"
    session.resume(kept, model="peto")
    assert not any(item.get("type") == "reasoning" or "id" in item for item in session.items)

    history.save(project, peto.url, kept, model="luna")
    assert history.load(project, peto.url).model == "luna"


def test_split_command():
    assert cli.split_command("/effort Cao") == ("/effort", "Cao")
    assert cli.split_command("/Thoát") == ("/thoat", "")
    assert cli.split_command("/") == ("/", "")
    for text in ("/api/users lỗi 500", "sửa /moi", "/moi\nthêm dòng"):
        assert cli.split_command(text) == ("", "")


def test_disconnect_after_edit_and_command_can_resume_without_replaying(project, peto, monkeypatch):
    """Cắt TCP thật sau một phần câu trả lời; mở lại phiên và thử bước đó với lịch sử đã lưu."""
    attempts = 0

    def broken(path, body):
        nonlocal attempts
        results = [item for item in body.get("input", []) if item.get("type") == "function_call_output"]
        if len(results) == 3:
            attempts += 1
            # JSON bị cắt, không có done: phần trả lời này không được đưa vào lịch sử đã xác nhận.
            return 200, b'data: {"type":"delta","text":"Partial reply"}\n\ndata: {"type":"done","output":['
        return demo_reply(path, body)

    peto.reply = broken
    session, ui = start(project, peto, ["a"])
    session.run_task("Sửa README")
    saved = history.load(project, peto.url)
    assert attempts == 1 and session.can_retry and saved.retryable
    assert "gõ /retry" in ui.text
    assert not session.tools.approve_all
    assert_every_call_has_output(saved.items)
    assert "Partial reply" not in json.dumps(saved.items)
    assert (project / "README.md").read_text(encoding="utf-8").count("(Peto)") == 1

    before = len(peto.requests)
    resumed = Session(Client(peto.url, "peto_token_thu"), Workspace(project), FakeUI())
    cli._resume(resumed.ui, resumed)
    assert resumed.can_retry and not resumed.ws.read_digests
    peto.reply = demo_reply
    monkeypatch.setattr(resumed.tools, "call", lambda *args: pytest.fail("công cụ cũ bị chạy lại"))
    resumed.retry_task()
    assert len(peto.requests) == before + 1
    assert peto.requests[-1]["body"]["input"] == saved.items
    assert "Xong rồi nè." in resumed.ui.text
    assert not resumed.can_retry and not history.load(project, peto.url).retryable
    assert sum(item.get("role") == "user" for item in resumed.items) == 1


def test_retry_requires_fresh_permission_for_new_tools(project, peto):
    session, ui = start(project, peto, ["a", "n"])

    def interrupted(path, body):
        results = [item for item in body["input"] if item.get("type") == "function_call_output"]
        if len(results) == 2:
            return 200, [{"type": "delta", "text": "Chưa xong"}]
        return demo_reply(path, body)

    peto.reply = interrupted
    session.run_task("Sửa README")
    assert session.can_retry and ui.answers == ["n"]
    peto.reply = demo_reply
    session.retry_task()
    assert ui.answers == [] and session.tools.commands == []
    assert "Không chạy lệnh" in ui.text
    assert_every_call_has_output(session.items)


@pytest.mark.parametrize("events", [b'data: []\n\n', b'data: {"type":"done","output":{}}\n\n'])
def test_malformed_stream_is_an_error_not_a_crash(project, peto, events):
    peto.reply = lambda path, body: (200, events)
    session, ui = start(project, peto, [])
    session.run_task("Xin chào")
    assert session.can_retry and "không đúng định dạng" in ui.text
    assert session.items == [{"type": "message", "role": "user", "content": "Xin chào"}]


def test_done_does_not_wait_for_socket_close(peto):
    peto.hold = threading.Event()
    peto.reply = lambda path, body: (200, b'data: {"type":"done","output":[]}\n\n')
    try:
        started = time.monotonic()
        assert list(Client(peto.url, "test").stream("/step", {})) == [{"type": "done", "output": []}]
        assert time.monotonic() - started < 2
    finally:
        peto.hold.set()


def test_ctrl_c_during_a_silent_stream_closes_connection_and_does_not_enable_retry(project, peto):
    peto.hold = threading.Event()
    peto.reply = lambda path, body: (200, b': waiting\n\n')
    session, ui = start(project, peto, [])
    original = session.client.stream

    def interrupted(path, body, **kwargs):
        def cancel():
            raise KeyboardInterrupt
        return original(path, body, on_idle=cancel)

    session.client.stream = interrupted
    try:
        started = time.monotonic()
        session.run_task("Xin chào")
        assert time.monotonic() - started < 2
        assert not session.can_retry and "Đã dừng yêu cầu" in ui.text
        assert not history.load(project, peto.url).retryable
    finally:
        peto.hold.set()


def test_slash_retry_dispatches_only_when_a_step_was_interrupted(project, peto, monkeypatch):
    attempts = 0

    def reply(path, body):
        nonlocal attempts
        if path == "/api/agent/me":
            return 200, {"account": "Bình", "steps_used": 0, "steps_limit": 200}
        attempts += 1
        if attempts == 1:
            return 200, [{"type": "delta", "text": "Đang xem"}]
        return 200, [{"type": "delta", "text": "Đã xong"}, {"type": "done", "output": [message("Đã xong")]}]

    peto.reply = reply
    config.save({"server": peto.url, "token": "test"})
    monkeypatch.chdir(project)
    ui = FakeUI(answers=["/retry", "Xin chào", "/retry", "/retry", "/thoat"])
    assert cli.session(ui) == 0
    assert attempts == 2
    assert ui.text.count("Không có bước bị gián đoạn") == 2

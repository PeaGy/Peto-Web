"""Lệnh /init và phần tìm web: CLI chỉ hiển thị, việc tìm chạy ở phía dịch vụ AI."""

from __future__ import annotations

import copy
import json

from conftest import FakeUI

from peto_agent.loop import Session, portable
from peto_agent.workspace import Workspace


def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


class Client:
    """Máy chủ giả: mỗi lần gọi phát một danh sách sự kiện đã dựng sẵn."""

    server = "https://example.test"

    def __init__(self, turns):
        self.turns = list(turns)
        self.bodies = []

    def stream(self, path, body, **kwargs):
        self.bodies.append(copy.deepcopy(body))
        yield from self.turns.pop(0)


def session(project, client, answers=()):
    return Session(client, Workspace(project), FakeUI(answers))


def task_text(client) -> str:
    return client.bodies[0]["input"][0]["content"]


def test_init_describes_the_project_and_what_agents_md_is_for(project):
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("print(1)\n")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "x.js").write_text("x\n")
    client = Client([[{"type": "done", "output": [message("Đã ghi AGENTS.md.")]}]])
    work = session(project, client)

    work.init_guide()
    text = task_text(client)
    assert "AGENTS.md" in text and "dưới 60 dòng" in text
    assert "src/app.py" in text, "cấu trúc gửi kèm để bước đầu khỏi phải liệt kê lại"
    assert "node_modules/" not in text, "cấu trúc bỏ thư mục nặng như mọi công cụ khác"
    assert "Dự án đã có AGENTS.md" not in text


def test_init_on_a_project_that_already_has_a_guide_asks_to_keep_what_is_right(project):
    (project / "AGENTS.md").write_text("# Hướng dẫn cũ\n", encoding="utf-8")
    client = Client([[{"type": "done", "output": [message("Đã cập nhật.")]}]])
    session(project, client).init_guide()
    assert "Dự án đã có AGENTS.md" in task_text(client)


def test_web_search_shows_one_line_and_the_search_item_stays_in_the_conversation(project):
    search_item = {"type": "web_search_call", "id": "ws_1", "status": "completed"}
    client = Client([[
        {"type": "search", "text": "searching"},
        {"type": "search", "text": "searching"},
        {"type": "search", "text": "completed"},
        {"type": "done", "output": [search_item, message("Bản mới nhất là 2.0.")],
         "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]])
    work = session(project, client)
    work.run_task("bản mới nhất của thư viện này là gì?")

    assert work.ui.text.count("Tìm trên web") == 1, "nhiều sự kiện tìm trong một bước chỉ in một dòng"
    assert search_item in work.items, "gửi lại nguyên văn để hội thoại không hụt mục"


def test_switching_model_drops_the_other_service_search_items(project):
    items = [{"type": "web_search_call", "id": "ws_1", "status": "completed"},
             {"type": "reasoning", "id": "rs_1", "encrypted_content": "x"},
             message("giữ lại")]
    assert portable(items) == [{"type": "message", "role": "assistant",
                                "content": [{"type": "output_text", "text": "giữ lại"}]}]


def test_init_logs_the_task_like_any_other_request(project, tmp_path):
    """Nhật ký ghi yêu cầu /init như yêu cầu thường, để xem lại một bước /init đã làm gì."""
    client = Client([[{"type": "done", "output": [message("xong")]}]])
    work = session(project, client)
    entries = []
    work.log = type("Log", (), {"write": lambda self, kind, **data: entries.append((kind, data))})()
    work.init_guide()
    assert entries[0][0] == "task" and "AGENTS.md" in entries[0][1]["text"]
    assert json.dumps(entries, ensure_ascii=False)

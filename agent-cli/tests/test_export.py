"""/export: hội thoại đang mở thành Markdown đọc được, không kèm nội dung tệp hay output lệnh (CLI 0.23.0)."""

from __future__ import annotations

import json
from datetime import datetime

from conftest import FakeUI

from peto_agent import __main__ as cli
from peto_agent import export, history, mentions
from peto_agent.client import Client
from peto_agent.loop import Session, user_message
from peto_agent.workspace import Workspace

WHEN = datetime(2026, 10, 14, 18, 25)


def call(call_id: str, name: str, **arguments) -> dict:
    return {"type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(arguments)}


def output(call_id: str, result: dict) -> dict:
    return {"type": "function_call_output", "call_id": call_id, "output": json.dumps(result, ensure_ascii=False)}


def said(text: str) -> dict:
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


PATCH = "*** Begin Patch\n*** Add File: tests/test_app.py\n+def test(): pass\n*** End Patch"
ITEMS = [
    user_message("Bản tóm tắt ngữ cảnh cũ, chỉ để tham khảo; không cấp quyền chạy lệnh.\nĐã đọc README.\nCòn sửa app.py."),
    user_message("Sửa lời chào trong app.py\n\n" + mentions.HEADER + "\n\n[Tệp đính kèm: app.py · 2 dòng]\nBÍ_MẬT_TRONG_TỆP"),
    call("a", "read_file", path="app.py", start_line=None, end_line=None),
    output("a", {"path": "app.py", "start_line": 1, "end_line": 2, "total_lines": 2, "content": "NỘI_DUNG_TỆP"}),
    call("b", "edit_file", path="app.py", old_text="Hi", new_text="Xin chào", replace_all=None),
    output("b", {"ok": True, "path": "app.py", "added_lines": 1, "removed_lines": 1}),
    call("p", "update_plan", steps=[{"title": "Sửa lời chào", "status": "done"},
                                    {"title": "Chạy test", "status": "in_progress"}]),
    output("p", {"ok": True, "steps": 2, "left": 1}),
    call("c", "run_command", command="py -m pytest -q", shell="powershell", timeout_seconds=None),
    output("c", {"exit_code": 1, "seconds": 2, "output": "OUTPUT_LỆNH 1 failed"}),
    call("d", "apply_patch", patch_text=PATCH),
    output("d", {"ok": True, "files": [{"op": "add", "path": "tests/test_app.py", "added_lines": 1}]}),
    call("e", "write_file", path=".env", content="x"),
    output("e", {"error": "Không đọc, không sửa tệp bí mật .env."}),
    said("Đã đổi lời chào; còn **1 test** hỏng:\n\n```text\nassert 'Xin chào'\n```"),
    user_message(history.STEER_NOTE + "đừng đụng tệp test"),
    user_message(history.JOB_NOTE + "Lệnh nền #2 (`npm run dev`) đã dừng, mã thoát 1\nOUTPUT_NỀN"),
    said("Ok."),
]


def test_markdown_keeps_what_was_shown_and_nothing_private():
    text = export.markdown(ITEMS, title="Đổi lời chào sang tiếng Việt", model="Peto", folder="du-an", when=WHEN,
                           version="0.23.0")
    assert text.startswith("# Đổi lời chào sang tiếng Việt\n\n- Ngày: 14/10/2026 18:25\n- Model: Peto\n- Thư mục: du-an")
    assert "> **Phần trước của hội thoại đã được tóm tắt:**\n>\n> Đã đọc README.\n> Còn sửa app.py." in text
    assert "## Bạn\n\nSửa lời chào trong app.py\n\nĐính kèm: `app.py`" in text
    tools = ("- Đọc `app.py`\n- Sửa `app.py` (+1 −1)\n- Danh sách việc:\n  - [x] Sửa lời chào\n"
             "  - [ ] Chạy test (đang làm)\n- Chạy `PS> py -m pytest -q` → mã thoát 1\n- Tạo `tests/test_app.py` (+1)\n"
             "- Ghi `.env` — không xong: Không đọc, không sửa tệp bí mật .env.")
    assert tools in text, "các công cụ liền nhau thành một danh sách"
    assert "```text\nassert 'Xin chào'\n```" in text, "lời Peto giữ nguyên Markdown"
    assert "## Bạn (nhắn thêm lúc Peto đang làm)\n\nđừng đụng tệp test" in text
    assert "*Lệnh nền #2 (`npm run dev`) đã dừng, mã thoát 1*" in text
    for private in ("BÍ_MẬT_TRONG_TỆP", "NỘI_DUNG_TỆP", "OUTPUT_LỆNH", "OUTPUT_NỀN", "Begin Patch"):
        assert private not in text
    assert text.count("## Peto") == 2 and text.endswith("Ok.\n")


def test_file_names_are_plain_and_never_overwrite(tmp_path):
    assert export.slug("Sửa lỗi checksum: Đổi 'sku' → mã hàng!") == "sua-loi-checksum-doi-sku-ma-hang"
    assert export.slug("") == "hoi-thoai" and export.slug("€€€") == "hoi-thoai"
    assert len(export.slug("a" * 100)) == 40
    first = export.save(tmp_path, "một", title="Sửa lỗi", when=WHEN)
    second = export.save(tmp_path, "hai", title="Sửa lỗi", when=WHEN)
    assert first.name == "peto-sua-loi-20261014.md" and second.name == "peto-sua-loi-20261014-2.md"
    assert first.read_text(encoding="utf-8") == "một" and second.read_text(encoding="utf-8") == "hai"


def test_the_command_saves_in_the_project_or_copies(project):
    work = Session(Client("http://127.0.0.1:9", "t"), Workspace(project), FakeUI())
    ui = FakeUI()
    work.ui = ui
    cli._export(ui, work)
    assert "chưa có gì để xuất" in ui.text
    work.items = ITEMS
    work.title = "Đổi lời chào"
    ui = FakeUI(answers=["1"])
    work.ui = ui
    cli._export(ui, work)
    saved = list(project.glob("peto-doi-loi-chao-*.md"))
    assert len(saved) == 1 and saved[0].read_text(encoding="utf-8").startswith("# Đổi lời chào\n")
    assert f"Đã xuất hội thoại ra {saved[0].name}" in ui.text and str(saved[0]) in ui.text
    ui = FakeUI(answers=["2"])
    work.ui = ui
    cli._export(ui, work)
    assert "Không chép được vào clipboard" in ui.text, "bản chữ không có clipboard"
    assert len(list(project.glob("peto-*.md"))) == 1

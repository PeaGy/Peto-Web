"""Tệp dài đã gửi: phần đọc sẵn (document_reader.condense_text) và công cụ tìm/đọc thêm (attachment_tools)."""
from features.chat import history as chat_history


import base64
import json
import uuid
from types import SimpleNamespace

import pytest

from shared import attachment_tools
import storage as db
from features.documents import reader
from features.chat import service as chat_service
from ai.base import ChatMessage, StreamChunk
from conftest import TEST_OWNER, read_events
from test_clock_tools import FakeStream, call, done, fake_provider
from test_documents import pdf_bytes

COUNT = 20_000
# Đường dẫn đổi theo từng dòng: các dòng liền nhau khác dạng nên không gộp được, phần đọc sẵn phải chọn đầu, giữa, cuối.
ROUTES = ("companion", "chat", "voice/speak", "imagine", "docs", "profile", "agent/step")


def log_lines(count: int = COUNT) -> list[str]:
    lines = []
    for index in range(count):
        stamp = f"2026-09-29 10:{index // 600 % 60:02d}:{index // 10 % 60:02d}.{index % 1000:03d}"
        if index == count // 2:
            lines.append(f"{stamp} ERROR db timeout after 30000ms on query get_messages")
        elif index == count - 5:
            lines.append(f'{stamp} ERROR worker-3 KeyError: "voice_id" in speech_cloud.py line 212')
        elif index == count // 3:
            lines.append(f"{stamp} WARN Lỗi kết nối tới máy nhà")
        else:
            lines.append(f"{stamp} INFO GET /api/{ROUTES[index % len(ROUTES)]} 200 {index % 90}ms user={index % 997}")
    return lines


LOG = "\n".join(log_lines())


def args(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


async def attached(tmp_path, name: str, data: bytes, mime: str) -> list[dict]:
    return (await attach(tmp_path, name, data, mime))[1]


async def attach(tmp_path, name: str, data: bytes, mime: str) -> tuple[str, list[dict]]:
    await db.init_db()
    cid = await db.create_conversation(TEST_OWNER)
    mid = await db.add_message(cid, "user", "Xem tệp giúp mình")
    path = tmp_path / name
    path.write_bytes(data)
    await db.add_attachment(attachment_id=uuid.uuid4().hex, owner=TEST_OWNER, conversation_id=cid, message_id=mid,
                            filename=name, mime=mime, kind="file", size=len(data), path=str(path))
    return cid, await db.get_messages(TEST_OWNER, cid)


@pytest.fixture
async def log_rows(tmp_path):
    return await attached(tmp_path, "app.log", LOG.encode(), "text/plain")


# ---------- Phần đọc sẵn ----------

def test_long_log_keeps_the_start_the_end_and_the_errors_in_between():
    document = reader.extract_document(LOG.encode(), "text/plain", 80_000, 100)
    text = document["text"]
    assert document["status"] == "partial" and len(text) <= 80_000
    # Trước 29/9 chỉ giữ phần đầu, nên lỗi ở cuối và ở giữa tệp không bao giờ tới được Peto.
    assert "KeyError" in text and "db timeout" in text
    assert text.startswith("[Dòng 1–") and "[… bỏ qua dòng" in text
    assert document["lines"] == COUNT and document["total_characters"] == len(LOG)
    assert "phần cuối" in document["notice"] and "lỗi" in document["notice"]
    # Chỉ cắt ở ranh giới dòng: mỗi dòng là một dòng thật của tệp hoặc một dòng đánh dấu.
    originals = set(LOG.splitlines())
    assert all(line in originals or line.startswith("[") for line in text.splitlines())


def test_repeated_log_lines_are_collapsed():
    text = "\n".join(f"10:00:{index % 60:02d} INFO heartbeat ok seq={index}" for index in range(30_000))
    document = reader.extract_document(text.encode(), "text/plain", 5_000, 100)
    assert "dòng cùng dạng" in document["text"] and len(document["text"]) <= 5_000


def test_a_few_huge_lines_keep_the_start_and_the_end():
    text = "a" * 60_000 + "\n" + "b" * 60_000 + "\n" + "c" * 60_000
    document = reader.extract_document(text.encode(), "text/plain", 80_000, 100)
    assert document["text"].startswith("a" * 100) and document["text"].endswith("c" * 100)
    assert "ký tự ở giữa" in document["text"] and len(document["text"]) <= 80_000


def test_partial_files_tell_peto_how_to_reach_the_rest():
    item = {"id": "tep-1", "filename": "app.log", "mime": "text/plain", "kind": "file", "path": "app.log",
            "document": reader.extract_document(LOG.encode(), "text/plain", 80_000, 100)}
    excerpt = chat_history._to_chat_messages([{"role": "user", "content": "Lỗi gì?", "attachments": [item]}])[0].attachments[0].text_excerpt
    assert "search_attachment" in excerpt and 'file="app.log"' in excerpt
    item["document"] = reader.result("ready", "Đã đọc tệp chữ.", "ngắn")
    excerpt = chat_history._to_chat_messages([{"role": "user", "content": "Lỗi gì?", "attachments": [item]}])[0].attachments[0].text_excerpt
    assert "search_attachment" not in excerpt


# ---------- Công cụ ----------

async def test_search_reaches_the_whole_file_with_real_line_numbers(log_rows):
    result = await attachment_tools.AttachmentFiles(log_rows).run(
        "search_attachment", args(file="app.log", query="keyerror", context_lines=1))
    assert result["matches"] == 1 and result["lines_total"] == COUNT
    assert "19.996: " in result["text"] and "KeyError" in result["text"]
    assert "19.995- " in result["text"] and "19.997- " in result["text"]
    assert attachment_tools.DATA_NOTE in result["note"]


async def test_search_ignores_case_and_vietnamese_marks_and_takes_alternatives(log_rows):
    result = await attachment_tools.AttachmentFiles(log_rows).run(
        "search_attachment", args(file="app.log", query="loi ket noi | DB TIMEOUT", context_lines=0))
    assert result["matches"] == 2
    assert "Lỗi kết nối" in result["text"] and "db timeout" in result["text"]


async def test_search_output_is_bounded(log_rows):
    result = await attachment_tools.AttachmentFiles(log_rows).run(
        "search_attachment", args(file="app.log", query="INFO", context_lines=5))
    assert result["matches"] > 19_000 and result["shown"] <= attachment_tools.MAX_MATCHES
    assert len(result["text"]) <= attachment_tools.MAX_OUTPUT_CHARS
    assert "Còn" in result["note"]


async def test_read_returns_the_exact_lines_within_limits(log_rows):
    files = attachment_tools.AttachmentFiles(log_rows)
    result = await files.run("read_attachment_lines", args(file="app.log", start_line=10_000, end_line=10_002))
    expected = LOG.splitlines()[9_999:10_002]
    assert result["text"].splitlines() == [f"{reader.number(10_000 + index)}: {line}" for index, line in enumerate(expected)]
    wide = await files.run("read_attachment_lines", args(file="app.log", start_line=1, end_line=COUNT))
    assert wide["end_line"] <= attachment_tools.MAX_READ_LINES and "Đọc tiếp từ dòng" in wide["note"]
    assert "error" in await files.run("read_attachment_lines", args(file="app.log", start_line=COUNT + 1, end_line=COUNT + 2))


@pytest.mark.parametrize("name, arguments", [
    ("search_attachment", "{hong"),
    ("search_attachment", args(file="khac.log", query="x", context_lines=0)),
    ("search_attachment", args(file="app.log", query=" | ", context_lines=0)),
    ("read_attachment_lines", args(file="app.log", start_line=True, end_line=2)),
    ("run_command", args(file="app.log")),
])
async def test_bad_calls_come_back_as_errors(log_rows, name, arguments):
    assert "error" in await attachment_tools.AttachmentFiles(log_rows).run(name, arguments)


async def test_unknown_file_lists_what_can_be_searched(log_rows):
    result = await attachment_tools.AttachmentFiles(log_rows).run(
        "search_attachment", args(file="khac.log", query="x", context_lines=0))
    assert '"app.log"' in result["error"]


async def test_pdf_is_searched_in_full(tmp_path):
    rows = await attached(tmp_path, "ke-hoach.pdf", pdf_bytes(), reader.PDF_MIME)
    result = await attachment_tools.AttachmentFiles(rows).run(
        "search_attachment", args(file="ke-hoach.pdf", query="7300", context_lines=1))
    assert result["matches"] == 1 and "[Trang 2]" in result["text"]


async def test_other_accounts_get_no_files(tmp_path):
    cid, rows = await attach(tmp_path, "app.log", LOG.encode(), "text/plain")
    assert attachment_tools.AttachmentFiles(rows).schemas()
    # Lịch sử lọc theo chủ tài khoản ngay trong SQL: tài khoản khác không có dòng nào, nên không có tệp nào để tra.
    assert attachment_tools.AttachmentFiles(await db.get_messages("github:nguoi-khac", cid)).schemas() == []


async def test_real_provider_offers_the_tools_and_returns_results(monkeypatch, log_rows):
    first = FakeStream([done(call("search_attachment", args(file="app.log", query="KeyError", context_lines=1)))])
    second = FakeStream([SimpleNamespace(type="response.output_text.delta", delta="Lỗi ở dòng 19.996."), done()])
    provider, requests = fake_provider(monkeypatch, [first, second])
    token = attachment_tools.current_files.set(attachment_tools.AttachmentFiles(log_rows))
    try:
        chunks = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[ChatMessage("user", "Lỗi gì?")])]
    finally:
        attachment_tools.current_files.reset(token)
    names = [tool.get("name") for tool in requests[0]["tools"]]
    assert "search_attachment" in names and "read_attachment_lines" in names
    output = json.loads(requests[1]["input"][-1]["output"])
    assert output["matches"] == 1 and "KeyError" in output["text"]
    lookups = [(chunk.kind, chunk.text) for chunk in chunks
               if isinstance(chunk, StreamChunk) and chunk.kind.startswith("file_lookup")]
    assert lookups == [("file_lookup", "Đang tìm “KeyError” trong app.log…"),
                       ("file_lookup_done", "Đã tìm “KeyError” trong app.log: 1 dòng khớp")]
    assert "".join(chunk for chunk in chunks if isinstance(chunk, str)) == "Lỗi ở dòng 19.996."


async def test_tools_are_not_offered_without_files(monkeypatch):
    stream = FakeStream([SimpleNamespace(type="response.output_text.delta", delta="Chào"), done()])
    provider, requests = fake_provider(monkeypatch, [stream])
    token = attachment_tools.current_files.set(attachment_tools.AttachmentFiles([]))
    try:
        _ = [chunk async for chunk in provider.stream(system_prompt="Peto", messages=[ChatMessage("user", "Chào")])]
    finally:
        attachment_tools.current_files.reset(token)
    assert all(tool.get("name") not in attachment_tools.NAMES for tool in requests[0]["tools"])


async def test_chat_shows_each_lookup_and_answers_from_the_whole_file(client):
    data = base64.b64encode(LOG.encode()).decode()
    events = await read_events(await client.post("/api/chat", json={
        "message": "__timtep__:KeyError", "attachments": [{"name": "app.log", "mime": "text/plain", "data": data}]}))
    assert events[-1]["type"] == "done", events
    lookups = [event for event in events if event["type"] == "file_lookup"]
    assert [event["live"] for event in lookups] == [True, False]
    assert lookups[-1]["text"] == "Đã tìm “KeyError” trong app.log: 1 dòng khớp"
    assert "KeyError" in "".join(event["text"] for event in events if event["type"] == "delta")

"""Tài liệu giả kiểm tra đọc chữ, giới hạn và cách ly hội thoại; không gọi AI thật."""

import base64
import io
import json
import zipfile

import anyio
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import attachments
import db
import document_reader as reader
import main
from ai.xai import build_input_payload
from conftest import OTHER_DISCORD_ID, TEST_OWNER, read_events


def pdf_bytes(pages=("Project Peto", "Budget: 7300 USD"), password=None):
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    for text in pages:
        page = writer.add_blank_page(width=600, height=800)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        if text:
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def docx_bytes(body=None, prefix="", extra=None):
    body = body if body is not None else """<w:p><w:r><w:t>Kế hoạch Peto tháng 9</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Hạng mục</w:t></w:r></w:p></w:tc>
    <w:tc><w:p><w:r><w:t>Số tiền</w:t></w:r></w:p></w:tc></w:tr>
    <w:tr><w:tc><w:p><w:r><w:t>Máy chủ</w:t></w:r></w:p></w:tc>
    <w:tc><w:p><w:r><w:t>350.000 đồng</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    <w:p><w:r><w:t>Hoàn thành ngày 18/9.</w:t></w:r></w:p>"""
    xml = f'{prefix}<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("word/document.xml", xml)
        if extra:
            archive.writestr(*extra)
    return output.getvalue()


def extract(data, mime=reader.PDF_MIME, chars=80_000, pages=100):
    return reader.extract_document(data, mime, chars, pages)


def outgoing(data, name="ke-hoach.pdf", mime=reader.PDF_MIME):
    return {"name": name, "mime": mime, "data": base64.b64encode(data).decode()}


def test_pdf_text_has_real_page_numbers():
    document = extract(pdf_bytes())
    assert document["status"] == "ready"
    assert document["pages"] == document["pages_processed"] == 2
    assert "[Trang 2]\nBudget: 7300 USD" in document["text"]


@pytest.mark.parametrize("pages,status", [(('', ''), 'no_text'), (('Hello', ''), 'partial')])
def test_pdf_empty_pages_are_honest(pages, status):
    document = extract(pdf_bytes(pages))
    assert document["status"] == status
    assert "OCR" in document["notice"]


def test_pdf_password_and_broken_file():
    assert extract(pdf_bytes(password="bi-mat"))["status"] == "encrypted"
    assert extract(b"%PDF-1.7\nhong")["status"] == "unreadable"


def test_pdf_page_and_text_caps():
    capped = extract(pdf_bytes(), pages=1)
    assert capped["status"] == "partial"
    assert capped["pages"] == 2 and capped["pages_processed"] == 1
    assert "7300" not in capped["text"]
    assert "phần đầu" in capped["notice"]
    capped = extract(pdf_bytes(), chars=14)
    assert len(capped["text"]) <= 14 and capped["status"] == "partial"


def test_pdf_compressed_content_is_bounded():
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    stream = DecodedStreamObject()
    stream.set_data(b" " * (reader.MAX_PAGE_BYTES + 1))
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    output = io.BytesIO()
    writer.write(output)
    document = extract(output.getvalue())
    assert document["status"] == "unreadable" and not document["text"]
    assert "quá phức tạp" in document["notice"]


def test_docx_vietnamese_tables_and_order():
    document = extract(docx_bytes(), reader.DOCX_MIME)
    assert document["status"] == "ready"
    assert "[Đoạn 1]\nKế hoạch Peto tháng 9" in document["text"]
    assert "[Bảng 1]\nHạng mục | Số tiền\nMáy chủ | 350.000 đồng" in document["text"]
    assert "[Đoạn 2]\nHoàn thành ngày 18/9." in document["text"]
    assert "pages" not in document


def test_docx_limits_empty_and_entity_rejected():
    assert extract(docx_bytes(), reader.DOCX_MIME, chars=30)["status"] == "partial"
    assert extract(docx_bytes(""), reader.DOCX_MIME)["status"] == "no_text"
    hostile = docx_bytes('<w:p><w:r><w:t>&secret;</w:t></w:r></w:p>',
                         '<!DOCTYPE w:document [<!ENTITY secret SYSTEM "file:///etc/passwd">]>')
    document = extract(hostile, reader.DOCX_MIME)
    assert document["status"] == "unreadable" and not document["text"]


def test_docx_empty_table_does_not_claim_readable_text():
    body = "<w:tbl><w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc></w:tr></w:tbl>"
    document = extract(docx_bytes(body), reader.DOCX_MIME)
    assert document["status"] == "no_text"
    assert document["text"] == ""


def test_docx_zip_bomb_rejected(monkeypatch):
    monkeypatch.setattr(reader, "MAX_ZIP_BYTES", 5000)
    document = extract(docx_bytes(extra=("word/media/test.bin", "a" * 6000)), reader.DOCX_MIME)
    assert document["status"] == "unreadable"
    assert "quá lớn" in document["notice"]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_text_unicode_boundary_and_bom(encoding):
    text = "a" * 2047 + "Tiếng Việt thật đẹp"
    data = text.encode(encoding)
    assert attachments.classify("ghi-chu.txt", "text/plain", data) == ("file", "text/plain")
    assert extract(data, "text/plain")["text"] == text


async def test_process_reader_really_extracts():
    document = await reader.read_document(pdf_bytes(), reader.PDF_MIME)
    assert document["status"] == "ready"
    assert "7300" in document["text"]


async def test_timeout_and_cancellation(monkeypatch):
    import config
    monkeypatch.setattr(config, "DOCUMENT_TIMEOUT", .02)
    cancelled = []

    async def slow(*args, **kwargs):
        assert kwargs["cancellable"] is True
        try:
            await anyio.sleep(10)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(reader.to_process, "run_sync", slow)
    assert (await reader.read_document(b"test", "text/plain"))["status"] == "timeout"
    assert cancelled
    with anyio.move_on_after(.001) as scope:
        await reader.read_document(b"test", "text/plain")
    assert scope.cancel_called


@pytest.mark.parametrize("name,mime,data,expected", [
    ("ke-hoach.pdf", reader.PDF_MIME, pdf_bytes(), "[Trang 2]\nBudget: 7300 USD"),
    ("ke-hoach.docx", reader.DOCX_MIME, docx_bytes(), "Máy chủ | 350.000 đồng"),
], ids=["pdf", "docx"])
async def test_upload_provider_followup_cache_and_privacy(client, monkeypatch, name, mime, data, expected):
    import auth
    from config import SESSION_COOKIE, owner_key
    histories = []

    async def spy(self, **kwargs):
        histories.append(kwargs["messages"])
        yield "Đã nhận nội dung kiểm thử."

    class SpyProvider:
        stream = spy

    monkeypatch.setattr(main, "get_provider", SpyProvider)
    events = await read_events(await client.post("/api/chat", json={"message": "Tóm tắt tài liệu", "attachments": [outgoing(data, name, mime)]}))
    assert events[0]["type"] == "reading"
    assert events[-1]["type"] == "done", events
    meta = next(event for event in events if event["type"] == "meta")
    attachment = meta["message"]["attachments"][0]
    assert attachment["document"]["status"] == "ready"
    assert "text" not in attachment["document"] and "path" not in attachment
    assert expected in histories[0][-1].attachments[0].text_excerpt
    assert expected in json.dumps(build_input_payload(histories[0]), ensure_ascii=False).replace("\\n", "\n")
    cid = meta["conversation_id"]
    stored = (await client.get(f"/api/conversations/{cid}/messages")).json()
    assert stored["messages"][0]["attachments"][0]["document"] == attachment["document"]

    async def no_read(*args):
        pytest.fail("Không được phân tích lại tệp đã lưu chữ")

    monkeypatch.setattr(reader, "read_document", no_read)
    followup = await read_events(await client.post("/api/chat", json={"message": "Giải thích thêm", "conversation_id": cid}))
    assert followup[-1]["type"] == "done"
    assert expected in histories[-1][0].attachments[0].text_excerpt
    assert (await client.get(attachment["url"])).content == data
    client.cookies.set(SESSION_COOKIE, auth._sign(owner_key("discord", OTHER_DISCORD_ID)))
    assert (await client.get(attachment["url"])).status_code == 404
    assert (await client.get(f"/api/conversations/{cid}/messages")).status_code == 404


async def test_legacy_pdf_read_once_and_owner_checked(client, tmp_path):
    cid = await db.create_conversation(TEST_OWNER)
    mid = await db.add_message(cid, "user", "Tệp cũ")
    path = tmp_path / "cu.pdf"
    path.write_bytes(pdf_bytes())
    await db.add_attachment(attachment_id="legacy-pdf", owner=TEST_OWNER, conversation_id=cid,
                            message_id=mid, filename="cu.pdf", mime=reader.PDF_MIME,
                            kind="file", size=path.stat().st_size, path=str(path))
    rows = await db.get_messages(TEST_OWNER, cid)
    await main._read_legacy_documents(TEST_OWNER, rows, 4)
    assert "7300" in main._to_chat_messages(rows)[0].attachments[0].text_excerpt
    await db.save_document("guest:someone-else", "legacy-pdf", reader.result("unreadable", "ghi đè"))
    saved = (await db.get_messages(TEST_OWNER, cid))[0]["attachments"][0]
    assert reader.cached_document(saved["document"])["status"] == "ready"


def test_context_cap_shares_current_files_before_old_history(monkeypatch):
    monkeypatch.setattr(main, "MAX_DOCUMENT_CONTEXT_CHARS", 100)

    def file(key, text):
        return {"id": key, "filename": key + ".txt", "mime": "text/plain", "kind": "file",
                "document": reader.result("ready", "Đã đọc", text)}

    rows = [{"role": "user", "content": "cũ", "attachments": [file("cu", "z" * 100)]},
            {"role": "user", "content": "mới", "attachments": [file("a", "a" * 100), file("b", "b" * 100)]}]
    history = main._to_chat_messages(rows)
    assert "a" * 50 in history[1].attachments[0].text_excerpt
    assert "a" * 51 not in history[1].attachments[0].text_excerpt
    assert "b" * 50 in history[1].attachments[1].text_excerpt
    assert "z" * 10 not in history[0].attachments[0].text_excerpt
    assert "ngữ cảnh lượt này" in history[0].attachments[0].text_excerpt


def test_small_files_leave_context_for_long_files(monkeypatch):
    monkeypatch.setattr(main, "MAX_DOCUMENT_CONTEXT_CHARS", 100)
    files = [{"id": str(index), "filename": f"{index}.txt", "mime": "text/plain", "kind": "file",
              "document": reader.result("ready", "Đã đọc", text)}
             for index, text in enumerate(["a" * 80, "b" * 15, "c" * 5])]
    history = main._to_chat_messages([{"role": "user", "content": "Đọc cả ba", "attachments": files}])
    assert "a" * 80 in history[0].attachments[0].text_excerpt
    assert "b" * 15 in history[0].attachments[1].text_excerpt
    assert "c" * 5 in history[0].attachments[2].text_excerpt
    assert all("ngữ cảnh lượt này" not in file.text_excerpt for file in history[0].attachments)


async def test_cancel_before_read_does_not_create_conversation(client):
    import asyncio
    before = await db.list_conversations(TEST_OWNER, limit=1000)
    response = await main.chat(main.ChatRequest(message="Đọc giúp", attachments=[main.AttachmentIn(**outgoing(pdf_bytes()))]), owner=TEST_OWNER)
    stream = response.body_iterator
    assert '"type": "reading"' in await anext(stream)
    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError())
    assert await db.list_conversations(TEST_OWNER, limit=1000) == before


async def test_delete_during_read_does_not_recreate_conversation(client, monkeypatch):
    cid = await db.create_conversation(TEST_OWNER)

    async def read_and_delete(*args):
        await db.delete_conversation(TEST_OWNER, cid)
        return reader.result("ready", "Đã đọc", "Nội dung giả")

    monkeypatch.setattr(reader, "read_document", read_and_delete)
    events = await read_events(await client.post("/api/chat", json={"message": "Đọc giúp", "conversation_id": cid, "attachments": [outgoing(pdf_bytes())]}))
    assert events[-1]["type"] == "error"
    assert not any(event["type"] == "meta" for event in events)
    assert not await db.owns_conversation(TEST_OWNER, cid)


async def test_document_migration_preserves_old_attachment(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "tai-lieu-cu.db"
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE attachments (id TEXT PRIMARY KEY, owner TEXT, conversation_id TEXT, message_id INTEGER, filename TEXT, mime TEXT, kind TEXT, size INTEGER, path TEXT, created_at REAL)')
        connection.execute("INSERT INTO attachments VALUES ('cu', 'guest:cu', 'hoi-thoai', 1, 'giu.pdf', 'application/pdf', 'file', 12, 'giu.pdf', 0)")
    monkeypatch.setattr(db, "DB_PATH", path)
    await db.init_db()
    await db.init_db()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT filename, document FROM attachments").fetchone() == ("giu.pdf", "")


PNG_1x1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _code_item(index: int) -> dict:
    return {
        "name": f"mod{index}.py",
        "mime": "text/x-python",
        "data": base64.b64encode(f"print({index})\n".encode()).decode(),
    }


def test_sixteen_code_files_are_accepted():
    files = attachments.validate_batch([_code_item(i) for i in range(16)])
    assert len(files) == 16


def test_seventeenth_code_file_is_rejected():
    with pytest.raises(attachments.AttachmentError, match="16 tệp"):
        attachments.validate_batch([_code_item(i) for i in range(17)])


def test_fifth_image_is_rejected():
    items = [
        {"name": f"anh{i}.png", "mime": "image/png", "data": PNG_1x1_B64}
        for i in range(5)
    ]
    with pytest.raises(attachments.AttachmentError, match="ảnh, PDF hoặc Word"):
        attachments.validate_batch(items)


def test_four_images_and_twelve_code_files_are_accepted():
    items = [
        {"name": f"anh{i}.png", "mime": "image/png", "data": PNG_1x1_B64}
        for i in range(4)
    ]
    items.extend(_code_item(i) for i in range(12))
    assert len(attachments.validate_batch(items)) == 16

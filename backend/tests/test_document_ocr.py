"""PDF scan và hỗn hợp: số trang, giới hạn, hủy OCR, cache và quyền riêng tư; không gọi AI thật."""
import io
import json
import shutil
import sys

import anyio
from PIL import Image
import pytest

from core import config
from features.documents import ocr, reader
from shared.attachment_tools import AttachmentFiles
from test_documents import pdf_bytes


def scanned_pdf():
    """PDF chỉ chứa ảnh, không có lớp chữ; dùng chung để kiểm tra renderer và bộ OCR thật nếu có."""
    from PIL import ImageDraw, ImageFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    picture = Image.new("RGB", (1200, 700), "white")
    ImageDraw.Draw(picture).multiline_text((70, 100), "Peto project plan\nBudget: 7300 USD", fill="black",
                                         font=ImageFont.load_default(size=60), spacing=50)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(600, 350))
    pdf.drawImage(ImageReader(picture), 0, 0, width=600, height=350)
    pdf.showPage()
    pdf.save()
    picture.close()
    return output.getvalue()


@pytest.fixture
def fake_ocr(monkeypatch):
    monkeypatch.setattr(ocr, "engine_settings", lambda: (sys.executable, "bộ-ocr-giả"))
    calls = []

    async def recognize(png, executable):
        assert png.startswith(b"\x89PNG")
        calls.append(png)
        return f"Kế hoạch tiếng Việt, trang scan {len(calls)}. Tổng cộng: 350.000 đồng."

    monkeypatch.setattr(ocr, "recognize", recognize)
    async def ready(executable):
        return True
    monkeypatch.setattr(ocr, "check_languages", ready)
    return calls


async def test_mixed_pdf_preserves_pages_and_public_privacy(fake_ocr):
    document = await reader.read_document(pdf_bytes(("Native first", "", "Native last")), reader.PDF_MIME)
    assert document["status"] == "ready"
    assert document["pages_read"] == 3 and document["ocr_pages"] == 1
    assert document["reading_method"] == "mixed"
    text = document["text"]
    assert text.index("[Trang 1]") < text.index("[Trang 2 · OCR]") < text.index("[Trang 3]")
    assert "350.000" in text and "có thể nhận sai" in document["notice"]
    public = reader.public_document(json.dumps(document))
    assert public["pages_read"] == 3 and public["ocr_pages"] == 1
    assert not any(key.startswith("_") for key in public)
    assert "text" not in public and "path" not in public
    assert len(fake_ocr) == 1


async def test_ocr_page_limit_and_character_cap(fake_ocr, monkeypatch):
    monkeypatch.setattr(config, "MAX_DOCUMENT_OCR_PAGES", 1)
    document = await reader.read_document(pdf_bytes(("", "", "")), reader.PDF_MIME)
    assert document["status"] == "partial" and document["pages_read"] == 1
    assert "tối đa 1 trang" in document["notice"] and "2 trang chưa" in document["notice"]
    assert len(fake_ocr) == 1
    partial = await ocr.complete_pdf(pdf_bytes(("",)), reader.extract_document(pdf_bytes(("",)), reader.PDF_MIME, 24, 100), 24)
    assert len(partial["text"]) <= 24 and partial["status"] == "partial"


@pytest.mark.parametrize("enabled", [True, False])
async def test_missing_or_disabled_engine_keeps_native_text(monkeypatch, enabled):
    monkeypatch.setattr(config, "DOCUMENT_OCR_ENABLED", enabled)
    monkeypatch.setattr(ocr, "engine_settings", lambda: (None, "không-có-ocr"))
    document = await reader.read_document(pdf_bytes(("Native", "")), reader.PDF_MIME)
    assert document["status"] == "partial" and "Native" in document["text"]
    assert document["pages_read"] == 1 and document["ocr_pages"] == 0
    assert "chưa có bộ OCR" in document["notice"] if enabled else "đang tắt" in document["notice"]
    scan = await reader.read_document(pdf_bytes(("",)), reader.PDF_MIME)
    assert scan["status"] == "no_text" and scan["characters"] == 0


@pytest.mark.parametrize("failure", ["timeout", "error", "empty"])
async def test_ocr_failures_keep_native_text(fake_ocr, monkeypatch, failure):
    async def fail(*args):
        if failure == "timeout":
            raise TimeoutError
        if failure == "error":
            raise ValueError("Lỗi bộ nhận dạng giả")
        return ""
    monkeypatch.setattr(ocr, "recognize", fail)
    document = await reader.read_document(pdf_bytes(("Native", "")), reader.PDF_MIME)
    assert document["status"] == "partial" and document["ocr_pages"] == 0
    assert "Native" in document["text"] and "1 trang chưa" in document["notice"]


async def test_missing_language_does_not_fallback_to_english(fake_ocr, monkeypatch):
    async def missing(executable):
        return False
    monkeypatch.setattr(ocr, "check_languages", missing)
    document = await reader.read_document(pdf_bytes(("Native", "")), reader.PDF_MIME)
    assert document["status"] == "partial" and "Native" in document["text"]
    assert "thiếu gói ngôn ngữ" in document["notice"] and not fake_ocr


async def test_total_timeout_keeps_completed_ocr_pages(fake_ocr, monkeypatch):
    data = pdf_bytes(("Native", "", ""))
    document = reader.extract_document(data, reader.PDF_MIME, 80_000, 100)
    monkeypatch.setattr(config, "DOCUMENT_OCR_TIMEOUT", .05)
    calls = []
    async def render(*args, **kwargs):
        assert kwargs["cancellable"]
        return b"PNG"
    async def recognize(*args):
        calls.append(True)
        if len(calls) == 1:
            return "Trang scan đã đọc"
        await anyio.sleep(30)
    monkeypatch.setattr(ocr.to_process, "run_sync", render)
    monkeypatch.setattr(ocr, "recognize", recognize)
    partial = await ocr.complete_pdf(data, document, 80_000)
    assert partial["status"] == "partial" and partial["pages_read"] == 2
    assert "Trang scan đã đọc" in partial["text"] and "hết thời gian" in partial["notice"]


async def test_reader_cancellation_propagates_during_ocr(fake_ocr, monkeypatch):
    started = anyio.Event()
    cancelled = []
    async def recognize(*args):
        started.set()
        try:
            await anyio.sleep(30)
        finally:
            cancelled.append(True)
    monkeypatch.setattr(ocr, "recognize", recognize)
    async with anyio.create_task_group() as group:
        group.start_soon(reader.read_document, pdf_bytes(("",)), reader.PDF_MIME)
        await started.wait()
        group.cancel_scope.cancel()
    assert cancelled


async def test_tool_reuses_ocr_but_still_warns_about_accuracy(tmp_path, fake_ocr, monkeypatch):
    data = pdf_bytes(("", ""))
    document = await reader.read_document(data, reader.PDF_MIME)
    async def no_engine(executable):
        pytest.fail("Chữ OCR đã lưu không cần gọi lại bộ nhận dạng hay kiểm tra ngôn ngữ.")
    monkeypatch.setattr(ocr, "check_languages", no_engine)
    path = tmp_path / "scan.pdf"
    path.write_bytes(data)
    files = AttachmentFiles([{"attachments": [{"id": "scan", "filename": "scan.pdf", "mime": reader.PDF_MIME,
                                              "kind": "file", "path": str(path), "document": document}]}])
    result = await files.run("search_attachment", json.dumps({"file": "scan.pdf", "query": "350.000", "context_lines": 1}))
    assert result["matches"] == 2
    assert "có thể nhận sai" in result["note"]
    assert len(fake_ocr) == 2


async def test_cached_ocr_remains_readable_when_engine_is_disabled(fake_ocr, monkeypatch):
    data = pdf_bytes(("",))
    cached = await reader.read_document(data, reader.PDF_MIME)
    monkeypatch.setattr(ocr, "engine_settings", lambda: (None, "đã-tắt"))
    assert not ocr.needs_read(cached)
    document = await reader.read_full_document(data, reader.PDF_MIME, cached=cached)
    assert document["status"] == "ready" and "350.000" in document["text"]
    assert document["ocr_pages"] == 1 and len(fake_ocr) == 1


def test_retry_only_when_engine_configuration_changes(monkeypatch):
    document = reader.result("no_text", "Máy chủ chưa có OCR.", _scan_pages=[1], _ocr_signature="cũ")
    monkeypatch.setattr(ocr, "engine_settings", lambda: (None, "cũ"))
    assert not ocr.needs_read(document)
    monkeypatch.setattr(ocr, "engine_settings", lambda: (sys.executable, "mới"))
    assert ocr.needs_read(document)
    assert not ocr.needs_read(reader.result("ready", "Đã đọc chữ.", "Nội dung"))


def test_render_respects_pixel_budget(monkeypatch):
    monkeypatch.setattr(ocr, "MAX_PIXELS", 50_000)
    with Image.open(io.BytesIO(ocr.render_scan_page(pdf_bytes(), 1))) as picture:
        assert picture.width * picture.height <= 50_000
    with pytest.raises(ValueError):
        ocr.render_scan_page(pdf_bytes(), 3)


def test_oversized_source_image_is_rejected_before_render(monkeypatch):
    import pypdfium2 as pdfium
    monkeypatch.setattr(ocr, "MAX_SOURCE_IMAGE_PIXELS", 100)
    def no_render(*args, **kwargs):
        pytest.fail("Ảnh gốc quá lớn phải bị chặn trước khi dựng bitmap.")
    monkeypatch.setattr(pdfium.PdfPage, "render", no_render)
    with pytest.raises(ValueError, match="Ảnh gốc"):
        ocr.render_scan_page(scanned_pdf(), 1)


async def test_real_scan_upload_and_followup_metadata(client, monkeypatch, fake_ocr):
    from test_documents import test_upload_provider_followup_cache_and_privacy as verify_upload
    data = scanned_pdf()
    assert reader.extract_document(data, reader.PDF_MIME, 80_000, 100)["status"] == "no_text"
    await verify_upload(client, monkeypatch, "scan.pdf", reader.PDF_MIME, data, "[Trang 1 · OCR]\nKế hoạch tiếng Việt")
    assert len(fake_ocr) == 1


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Máy kiểm thử chưa cài Tesseract; kiểm tra thật chạy khi có chương trình.")
async def test_installed_tesseract_reads_real_scan(monkeypatch):
    monkeypatch.setattr(config, "DOCUMENT_OCR_ENABLED", True)
    monkeypatch.setattr(config, "DOCUMENT_OCR_COMMAND", shutil.which("tesseract"))
    monkeypatch.setattr(config, "DOCUMENT_OCR_LANGUAGES", "eng")
    document = await reader.read_document(scanned_pdf(), reader.PDF_MIME)
    assert document["status"] == "ready", document["notice"]
    assert document["ocr_pages"] == 1 and "7300" in document["text"]


async def test_subprocess_uses_arguments_and_stdin(monkeypatch):
    original = anyio.open_process
    calls = []
    async def fake(command, **kwargs):
        calls.append(command)
        return await original([sys.executable, "-c", "import sys; assert sys.stdin.buffer.read()==b'PNG'; sys.stdout.buffer.write('Tiếng Việt'.encode())"], **kwargs)
    monkeypatch.setattr(anyio, "open_process", fake)
    assert await ocr.recognize(b"PNG", sys.executable) == "Tiếng Việt"
    assert calls[0] == [sys.executable, "stdin", "stdout", "-l", config.DOCUMENT_OCR_LANGUAGES, "--psm", "3"]


async def test_subprocess_cancel_and_output_limit_kill_child(monkeypatch):
    original = anyio.open_process
    processes = []
    started = anyio.Event()
    script = "import sys,time; sys.stdin.buffer.read(); time.sleep(30)"
    async def fake(command, **kwargs):
        process = await original([sys.executable, "-c", script], **kwargs)
        processes.append(process)
        started.set()
        return process
    monkeypatch.setattr(anyio, "open_process", fake)
    async with anyio.create_task_group() as group:
        group.start_soon(ocr.recognize, b"PNG", sys.executable)
        await started.wait()
        group.cancel_scope.cancel()
    assert processes[0].returncode is not None
    script = "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'A'*200000); sys.stdout.flush()"
    with pytest.raises(ExceptionGroup):
        await ocr.recognize(b"PNG", sys.executable)
    assert processes[-1].returncode is not None

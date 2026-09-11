"""Đọc lớp chữ của tài liệu trong tiến trình riêng, không chạy mã trong tệp."""

from __future__ import annotations

import io
import json
import logging
import zipfile

import anyio
from anyio import to_process
from defusedxml.ElementTree import fromstring
from pypdf import PdfReader, apply_configuration

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
VERSION = 1
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_ZIP_BYTES = 32 * 1024 * 1024
MAX_PAGE_BYTES = 2 * 1024 * 1024
WORD_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}


def result(status: str, notice: str, text: str = "", **details) -> dict:
    return {"version": VERSION, "status": status, "notice": notice,
            "text": text, "characters": len(text), **details}


def decode_text(data: bytes) -> str:
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    text = data.decode(encoding)
    if "\x00" in text:
        raise ValueError("Tệp chứa dữ liệu nhị phân")
    return text


def _pdf(data: bytes, max_chars: int, max_pages: int) -> dict:
    # Giới hạn giải nén của thư viện áp dụng cả các stream lồng trong trang.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted:
        return result("encrypted", "PDF có mã hóa hoặc mật khẩu. Gửi bản đã mở khóa để Peto đọc nhé.")
    total = len(reader.pages)
    parts: list[str] = []
    used = 0
    processed = 0
    empty = 0
    skipped = 0
    shortened = False
    for index in range(min(total, max_pages)):
        processed += 1
        try:
            page = reader.pages[index]
            content = page.get_contents()
            if content is not None and len(content.get_data()) > MAX_PAGE_BYTES:
                skipped += 1
                continue
            text = (page.extract_text() or "").strip()
        except Exception:
            skipped += 1
            continue
        if not text:
            empty += 1
            continue
        block = f"[Trang {index + 1}]\n{text}\n\n"
        room = max_chars - used
        parts.append(block[:room])
        used += min(room, len(block))
        if len(block) > room or (used >= max_chars and processed < total):
            shortened = True
            break
    text = "".join(parts).strip()
    partial = shortened or processed < total or skipped > 0 or empty > 0
    notices = []
    if text:
        notices.append(f"Đã đọc lớp chữ ở {processed - empty - skipped}/{total} trang.")
    else:
        notices.append("Chưa lấy được chữ từ PDF.")
    if empty:
        notices.append(f"{empty} trang không có lớp chữ đọc được; có thể là ảnh scan. Chưa hỗ trợ OCR.")
    if skipped:
        notices.append(f"{skipped} trang bị lỗi hoặc quá phức tạp nên được bỏ qua.")
    if shortened or processed < total:
        notices.append("Tài liệu dài: chỉ đọc một phần đầu. Gửi riêng phần cần hỏi nếu bị thiếu.")
    return result("partial" if text and partial else "ready" if text else "unreadable" if skipped else "no_text",
                  " ".join(notices), text, pages=total, pages_processed=processed)


def _tag(element) -> str:
    namespace, _, local = element.tag[1:].partition("}") if element.tag.startswith("{") else ("", "", element.tag)
    return local if namespace in WORD_NAMESPACES else ""


def _paragraph(element) -> str:
    parts = []
    for child in element.iter():
        tag = _tag(child)
        if tag == "t":
            parts.append(child.text or "")
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _docx(data: bytes, max_chars: int) -> dict:
    # Đọc đúng thành phần cần dùng trong bộ nhớ; không giải nén ra ổ đĩa.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if (len(entries) > 2000 or sum(item.file_size for item in entries) > MAX_ZIP_BYTES
                or len({item.filename for item in entries}) != len(entries)):
            return result("unreadable", "Word có cấu trúc nén quá lớn hoặc không hợp lệ. Hãy xuất bản gọn hơn.")
        info = archive.getinfo("word/document.xml")
        if info.file_size > MAX_XML_BYTES or info.flag_bits & 1:
            return result("unreadable", "Nội dung Word quá lớn hoặc bị mã hóa. Hãy gửi bản gọn hơn đã mở khóa.")
        with archive.open(info) as member:
            xml = member.read(MAX_XML_BYTES + 1)
        if len(xml) > MAX_XML_BYTES:
            return result("unreadable", "Nội dung Word vượt giới hạn đọc. Hãy chia nhỏ tài liệu.")
    root = fromstring(xml, forbid_dtd=True)
    if _tag(root) != "document":
        raise ValueError("Không phải cấu trúc Word")
    body = next((child for child in root if _tag(child) == "body"), None)
    if body is None:
        raise ValueError("Word thiếu phần nội dung")
    parts: list[str] = []
    used = 0
    paragraphs = 0
    tables = 0
    shortened = False

    def blocks(parent):
        for child in parent:
            tag = _tag(child)
            if tag in {"p", "tbl"}:
                yield child
            elif tag in {"sdt", "sdtContent", "ins", "customXml"}:
                yield from blocks(child)

    for block in blocks(body):
        if _tag(block) == "p":
            value = _paragraph(block)
            if not value:
                continue
            paragraphs += 1
            value = f"[Đoạn {paragraphs}]\n{value}\n\n"
        else:
            tables += 1
            rows = []
            has_text = False
            for row in block:
                if _tag(row) == "tr":
                    cells = [" / ".join(_paragraph(p) for p in cell.iter() if _tag(p) == "p")
                             for cell in row if _tag(cell) == "tc"]
                    has_text = has_text or any(cell.strip(" /\t\n") for cell in cells)
                    rows.append(" | ".join(cells))
            if not has_text:
                continue
            value = f"[Bảng {tables}]\n" + "\n".join(rows) + "\n\n"
        room = max_chars - used
        parts.append(value[:room])
        used += min(room, len(value))
        if len(value) > room:
            shortened = True
            break
    text = "".join(parts).strip()
    notice = "Đã đọc phần thân văn bản và bảng biểu trong Word." if text else "Word chưa có chữ đọc được trong phần thân tài liệu."
    if shortened:
        notice += " Tài liệu dài: chỉ đọc một phần đầu. Gửi riêng phần cần hỏi nếu bị thiếu."
    return result("partial" if shortened else "ready" if text else "no_text", notice, text)


def extract_document(data: bytes, mime: str, max_chars: int, max_pages: int) -> dict:
    """Hàm thuần cho tiến trình con; lỗi tệp không làm hỏng cả lượt chat."""
    try:
        if mime == PDF_MIME:
            with apply_configuration(maximum_declared_stream_length=MAX_PAGE_BYTES,
                                     array_based_stream_maximum_output_length=MAX_PAGE_BYTES,
                                     zlib_maximum_output_length=MAX_PAGE_BYTES,
                                     lzw_maximum_output_length=MAX_PAGE_BYTES,
                                     run_length_maximum_output_length=MAX_PAGE_BYTES):
                return _pdf(data, max_chars, max_pages)
        if mime == DOCX_MIME:
            return _docx(data, max_chars)
        text = decode_text(data).strip()
        partial = len(text) > max_chars
        return result("partial" if partial else "ready" if text else "no_text",
                      "Tệp dài: chỉ đọc một phần đầu." if partial else "Đã đọc tệp chữ." if text else "Tệp không có chữ.",
                      text[:max_chars])
    except Exception:
        return result("unreadable", "Chưa đọc được tệp: định dạng không hợp lệ hoặc tệp bị lỗi. Thử xuất lại thành PDF có chữ hoặc DOCX nhé.")


async def read_document(data: bytes, mime: str) -> dict:
    from config import DOCUMENT_TIMEOUT, MAX_DOCUMENT_PAGES, MAX_TEXT_EXCERPT_CHARS

    try:
        with anyio.fail_after(DOCUMENT_TIMEOUT):
            return await to_process.run_sync(extract_document, data, mime,
                                            MAX_TEXT_EXCERPT_CHARS, MAX_DOCUMENT_PAGES,
                                            cancellable=True)
    except TimeoutError:
        return result("timeout", "Tệp mất quá lâu để đọc. Hãy chia nhỏ hoặc xuất lại tài liệu rồi gửi lại nhé.")
    except Exception:
        return result("unreadable", "Bộ đọc tài liệu đang gặp lỗi. Thử gửi lại tệp sau nhé.")


def cached_document(raw) -> dict | None:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(value, dict) and value.get("version") == VERSION:
            return value
    except (ValueError, TypeError):
        pass
    return None


def public_document(raw) -> dict | None:
    cached = cached_document(raw)
    if cached is None:
        return None
    return {key: cached[key] for key in ("status", "notice", "characters", "pages", "pages_processed") if key in cached}

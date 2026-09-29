"""Đọc lớp chữ của tài liệu trong tiến trình riêng, không chạy mã trong tệp."""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile

import anyio
from anyio import to_process
from defusedxml.ElementTree import fromstring
from pypdf import PdfReader, apply_configuration

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
# 2 (29/9/2026): tệp chữ dài giữ phần đầu, phần cuối và các đoạn có lỗi thay vì chỉ phần đầu. Đổi số này thì tệp cũ
# được đọc lại ở lượt sau (main._read_legacy_documents).
VERSION = 2
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_ZIP_BYTES = 32 * 1024 * 1024
MAX_PAGE_BYTES = 2 * 1024 * 1024
# Công cụ tìm/đọc trong tệp (attachment_tools) cần cả tài liệu chứ không chỉ phần đọc sẵn.
FULL_TEXT_CHARS = 8_000_000

# Tệp chữ dài (thường là log): lỗi mới nhất nằm ở cuối, nên phần đọc sẵn gồm phần đầu, các đoạn có dấu hiệu dưới đây ở
# giữa, và phần cuối. Tỉ lệ là phần của giới hạn chữ; phần cuối nhận phần còn lại.
SIGNAL = re.compile(r"error|exception|traceback|fatal|critical|panic|warn|fail|denied|refused|timed? ?out|lỗi|cảnh báo",
                    re.IGNORECASE)
HEAD_SHARE = 0.15
SIGNAL_SHARE = 0.35
# Số dòng lấy thêm trước và sau mỗi dòng có lỗi.
SIGNAL_CONTEXT = 2
# Một dòng quá dài (JSON trên một dòng) chỉ giữ phần đầu trong phần đọc sẵn.
LINE_CHARS = 2000
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


def number(value: int) -> str:
    """Số kiểu Việt Nam: 40.000."""
    return f"{value:,}".replace(",", ".")


def _shape(line: str) -> str:
    """Dạng của một dòng khi bỏ số, mã hex và mã dài: các dòng log chỉ khác giờ hay mã yêu cầu có cùng dạng."""
    return re.sub(r"0x[0-9a-f]+|[0-9a-f]{12,}|\d+", "#", line.casefold())


def _clip(line: str) -> str:
    return line if len(line) <= LINE_CHARS else f"{line[:LINE_CHARS]} …[cắt {number(len(line) - LINE_CHARS)} ký tự]"


def _units(lines: list[str]) -> list[tuple[int, int, str, bool, str]]:
    """Các mẩu (dòng đầu, dòng cuối, chữ, có lỗi, dạng). Từ 5 dòng liền nhau cùng dạng trở lên chỉ giữ dòng đầu, dòng cuối
    và một dòng báo số dòng lặp ở giữa; đoạn lặp ngắn hơn gộp lại chẳng bớt được bao nhiêu mà khó đọc."""
    shapes = [_shape(line) for line in lines]
    units = []
    start = 0
    while start < len(lines):
        end = start
        while end + 1 < len(lines) and shapes[end + 1] == shapes[start]:
            end += 1
        if end - start >= 4:
            signal = bool(SIGNAL.search(lines[start]))
            units += [(start + 1, start + 1, _clip(lines[start]), signal, shapes[start]),
                      (start + 2, end, f"[… {number(end - start - 1)} dòng cùng dạng …]", signal, shapes[start]),
                      (end + 1, end + 1, _clip(lines[end]), signal, shapes[start])]
        else:
            units += [(index + 1, index + 1, _clip(lines[index]), bool(SIGNAL.search(lines[index])), shapes[index])
                      for index in range(start, end + 1)]
        start = end + 1
    return units


def condense_text(text: str, max_chars: int) -> tuple[str, str]:
    """Phần đọc sẵn của một tệp chữ dài hơn giới hạn, kèm lời báo cho người dùng.

    Giữ phần đầu, các đoạn có lỗi hoặc cảnh báo ở giữa (mỗi dạng lỗi một lần) và phần cuối, cắt đúng ranh giới dòng, gộp
    các dòng lặp cùng dạng. Mỗi khối mở đầu bằng "[Dòng a–b]" theo số dòng thật của tệp, để Peto đọc tiếp đúng chỗ bằng
    công cụ read_attachment_lines. Tệp ít dòng mà dòng rất dài thì giữ đầu và cuối theo ký tự.
    """
    lines = text.splitlines()
    if len(lines) <= 20:
        head = int(max_chars * 0.3)
        tail = max_chars - head - 80
        skipped = len(text) - head - tail
        return (f"{text[:head]}\n[… bỏ qua {number(skipped)} ký tự ở giữa …]\n{text[-tail:]}",
                f"Tệp dài {number(len(text))} ký tự: Peto đọc phần đầu và phần cuối. Khi cần, Peto tìm thêm trong tệp.")
    units = _units(lines)
    cost = [len(unit[2]) + 1 for unit in units]
    if sum(cost) <= max_chars:
        return ("\n".join(unit[2] for unit in units),
                f"Tệp dài {number(len(lines))} dòng: các dòng lặp cùng dạng được gộp, phần còn lại đọc đủ.")
    # Chừa chỗ cho các dòng "[Dòng …]" và "[… bỏ qua …]".
    budget = max_chars - 400
    head_end, used = 0, 0
    while head_end < len(units) and used + cost[head_end] <= budget * HEAD_SHARE:
        used += cost[head_end]
        head_end += 1
    tail_start, tail_used = len(units), 0
    while tail_start > head_end and tail_used + cost[tail_start - 1] <= budget * (1 - HEAD_SHARE - SIGNAL_SHARE):
        tail_start -= 1
        tail_used += cost[tail_start]
    seen = {unit[4] for unit in units[:head_end] + units[tail_start:] if unit[3]}
    blocks: list[list[int]] = []
    signal_used = 0
    index = head_end
    while index < tail_start:
        unit = units[index]
        if not unit[3] or unit[4] in seen:
            index += 1
            continue
        seen.add(unit[4])
        start = max(index - SIGNAL_CONTEXT, blocks[-1][1] if blocks else head_end)
        end = min(index + SIGNAL_CONTEXT + 1, tail_start)
        extra = sum(cost[start:end]) + 60
        if signal_used + extra > budget * SIGNAL_SHARE:
            break
        signal_used += extra
        if blocks and start == blocks[-1][1]:
            blocks[-1][1] = end
        else:
            blocks.append([start, end])
        index = end
    # Chỗ còn thừa dành cho phần cuối: với log, đoạn mới nhất đáng đọc nhất.
    spare = budget - used - tail_used - signal_used
    limit = blocks[-1][1] if blocks else head_end
    while tail_start > limit and cost[tail_start - 1] <= spare:
        tail_start -= 1
        spare -= cost[tail_start]
    parts: list[str] = []
    last_line = 0
    for start, end, label in [(0, head_end, ""), *((s, e, " · có lỗi hoặc cảnh báo") for s, e in blocks),
                              (tail_start, len(units), "")]:
        if start >= end:
            continue
        first, final = units[start][0], units[end - 1][1]
        if first > last_line + 1:
            parts.append(f"[… bỏ qua dòng {number(last_line + 1)}–{number(first - 1)} …]")
        parts.append(f"[Dòng {number(first)}–{number(final)}{label}]")
        parts.extend(unit[2] for unit in units[start:end])
        last_line = final
    excerpt = "\n".join(parts)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:excerpt.rfind("\n", 0, max_chars)]
    found = f" và {number(len(blocks))} đoạn có lỗi hoặc cảnh báo ở giữa" if blocks else ""
    return (excerpt, f"Tệp dài {number(len(lines))} dòng: Peto đọc phần đầu, phần cuối{found}; các dòng lặp cùng dạng "
                     "được gộp. Khi cần, Peto tìm thêm trong tệp.")


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
        notices.append("Tài liệu dài: Peto đọc sẵn phần đầu, khi cần sẽ tìm thêm trong tệp."
                       + (f" Riêng các trang sau trang {processed} thì chưa đọc được." if processed < total else ""))
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
        notice += " Tài liệu dài: Peto đọc sẵn phần đầu, khi cần sẽ tìm thêm trong tệp."
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
        text = decode_text(data)
        if len(text.strip()) <= max_chars:
            text = text.strip()
            return result("ready" if text else "no_text", "Đã đọc tệp chữ." if text else "Tệp không có chữ.", text)
        excerpt, notice = condense_text(text, max_chars)
        return result("partial", notice, excerpt, total_characters=len(text), lines=len(text.splitlines()))
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


async def read_full_document(data: bytes, mime: str) -> dict:
    """Toàn bộ chữ của tệp cho công cụ tìm/đọc: tệp chữ giữ nguyên từng dòng; PDF và Word đọc lại trong tiến trình
    riêng với giới hạn chữ nới rộng, giới hạn trang và thời gian như bộ đọc thường."""
    from config import DOCUMENT_TIMEOUT, MAX_DOCUMENT_PAGES

    if mime not in (PDF_MIME, DOCX_MIME):
        try:
            text = await anyio.to_thread.run_sync(decode_text, data)
        except ValueError:
            return result("unreadable", "Tệp không phải chữ đọc được.")
        if not text.strip():
            return result("no_text", "Tệp không có chữ.")
        return result("ready", "Đã đọc tệp chữ.", text)
    try:
        with anyio.fail_after(DOCUMENT_TIMEOUT):
            return await to_process.run_sync(extract_document, data, mime, FULL_TEXT_CHARS, MAX_DOCUMENT_PAGES,
                                            cancellable=True)
    except TimeoutError:
        return result("timeout", "Tệp mất quá lâu để đọc lại.")
    except Exception:
        return result("unreadable", "Bộ đọc tài liệu đang gặp lỗi.")


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

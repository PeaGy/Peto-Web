"""Nhận dạng chữ PDF scan bằng Tesseract trên máy chủ, có giới hạn và hủy được."""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

import anyio
from anyio import to_process

from core import config

MAX_PIXELS = 4_000_000
MAX_SOURCE_IMAGE_PIXELS = 20_000_000
MAX_SOURCE_PAGE_PIXELS = 40_000_000
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 128_000
_capacity = anyio.CapacityLimiter(2)


def engine_settings() -> tuple[str | None, str]:
    """Dấu cấu hình giúp tệp cũ được đọc lại khi bật hoặc cài bộ OCR."""
    executable = shutil.which(config.DOCUMENT_OCR_COMMAND) if config.DOCUMENT_OCR_ENABLED else None
    try:
        modified = Path(executable).stat().st_mtime_ns if executable else 0
    except OSError:
        executable, modified = None, 0
    signature = f"{executable or ''}|{modified}|{config.DOCUMENT_OCR_ENABLED}|{config.DOCUMENT_OCR_LANGUAGES}|{config.MAX_DOCUMENT_OCR_PAGES}"
    return executable, signature


def needs_read(document: dict | None) -> bool:
    if document is None:
        return True
    if not document.get("_scan_pages"):
        return False
    executable, signature = engine_settings()
    if not executable and any(document.get("_ocr_text", {}).values()):
        return False
    return document.get("_ocr_signature") != signature


def render_scan_page(data: bytes, page_number: int) -> bytes:
    """Chạy trong tiến trình riêng; giới hạn kích thước trước khi tạo bitmap."""
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(data) as pdf:
        if not 1 <= page_number <= len(pdf):
            raise ValueError("Không tìm thấy trang PDF.")
        page = pdf[page_number - 1]
        try:
            objects = 0
            source_pixels = 0
            def check_images(form=None, depth=0):
                nonlocal objects, source_pixels
                for item in page.get_objects(max_depth=0, form=form):
                    objects += 1
                    if objects > 2000:
                        raise ValueError("Trang PDF quá phức tạp để OCR.")
                    if item.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
                        width, height = item.get_px_size()
                        pixels = width * height
                        source_pixels += pixels
                        if pixels > MAX_SOURCE_IMAGE_PIXELS or source_pixels > MAX_SOURCE_PAGE_PIXELS:
                            raise ValueError("Ảnh gốc trong PDF vượt giới hạn OCR.")
                    elif item.type == pdfium.raw.FPDF_PAGEOBJ_FORM:
                        if depth >= 8:
                            raise ValueError("Trang PDF có cấu trúc lồng quá sâu.")
                        check_images(item.raw, depth + 1)
            # Bitmap đầu ra nhỏ vẫn có thể cần giải mã ảnh gốc rất lớn; kiểm tra trước khi render.
            check_images()
            width, height = page.get_size()
            if not all(math.isfinite(size) and size > 0 for size in (width, height)):
                raise ValueError("Kích thước trang không hợp lệ.")
            scale = min(3, math.sqrt(MAX_PIXELS / (width * height)), 4096 / max(width, height))
            # Chừa chỗ cho PDFium làm tròn kích thước lên tới pixel nguyên.
            while math.ceil(width * scale) * math.ceil(height * scale) > MAX_PIXELS:
                scale *= 0.99
            bitmap = page.render(scale=scale)
            try:
                picture = bitmap.to_pil()
                try:
                    output = io.BytesIO()
                    picture.save(output, format="PNG")
                    if output.tell() > MAX_IMAGE_BYTES:
                        raise ValueError("Ảnh trang vượt giới hạn OCR.")
                    return output.getvalue()
                finally:
                    picture.close()
            finally:
                bitmap.close()
        finally:
            page.close()


def languages() -> list[str]:
    languages = config.DOCUMENT_OCR_LANGUAGES
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", languages):
        raise ValueError("Ngôn ngữ OCR chưa được cấu hình đúng.")
    return languages.split("+")


async def _engine_output(command: list[str], data: bytes = b"") -> str:
    """Không qua shell, không ghi ảnh scan ra đĩa; hủy hoặc quá hạn sẽ dừng tiến trình."""
    environment = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    output = bytearray()
    async with await anyio.open_process(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ) as process:
        async def send_image():
            try:
                if data:
                    await process.stdin.send(data)
            except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                pass
            finally:
                await process.stdin.aclose()

        async with anyio.create_task_group() as group:
            group.start_soon(send_image)
            async for chunk in process.stdout:
                output.extend(chunk)
                if len(output) > MAX_OUTPUT_BYTES:
                    raise ValueError("Chữ OCR vượt giới hạn mỗi trang.")
        if await process.wait() != 0:
            raise ValueError("OCR chưa chạy được; cần kiểm tra bộ nhận dạng và gói ngôn ngữ trên máy chủ.")
    return output.decode("utf-8", errors="replace").strip()


async def check_languages(executable: str) -> bool:
    available = set((await _engine_output([executable, "--list-langs"])).splitlines())
    # Tesseract có thể trả thành công khi chỉ tải được một trong các ngôn ngữ; không âm thầm bỏ tiếng Việt.
    return all(language in available for language in languages())


async def recognize(png: bytes, executable: str) -> str:
    return await _engine_output([executable, "stdin", "stdout", "-l", "+".join(languages()), "--psm", "3"], png)


async def complete_pdf(data: bytes, document: dict, max_chars: int, *, cached: dict | None = None) -> dict:
    """Ghép chữ theo trang gốc; giữ kết quả đã đọc nếu OCR lỗi, quá hạn hoặc thiếu bộ nhận dạng."""
    from features.documents.reader import result

    if "_page_text" not in document:
        return document
    native = document.pop("_page_text")
    candidates = document.get("_scan_pages", [])
    if not candidates:
        return document
    executable, signature = engine_settings()
    saved = (cached or {}).get("_ocr_text", {}) if not executable or (cached or {}).get("_ocr_signature") == signature else {}
    selected = candidates[:config.MAX_DOCUMENT_OCR_PAGES] if executable else candidates
    recognized = {str(page): saved[str(page)] for page in selected if str(page) in saved}
    pending = [page for page in selected if str(page) not in recognized]
    attempted = len(recognized)
    failures = 0
    timed_out = False
    language_error = False
    unavailable = not executable
    if executable and pending:
        try:
            with anyio.fail_after(config.DOCUMENT_OCR_TIMEOUT):
                async with _capacity:
                    language_error = not await check_languages(executable)
                    for page in ([] if language_error else pending):
                        key = str(page)
                        attempted += 1
                        try:
                            with anyio.fail_after(config.DOCUMENT_OCR_PAGE_TIMEOUT):
                                png = await to_process.run_sync(render_scan_page, data, page, cancellable=True)
                                recognized[key] = await recognize(png, executable)
                        except TimeoutError:
                            timed_out = True
                        except Exception:
                            failures += 1
        except TimeoutError:
            timed_out = True
        except Exception:
            failures += 1
    parts = []
    used = 0
    read_pages = 0
    ocr_pages = 0
    shortened = document.get("truncated", False)
    for page in sorted({int(key) for key in native} | {int(key) for key, value in recognized.items() if value}):
        key = str(page)
        is_ocr = key in recognized
        block = f"[Trang {page} · OCR]\n{recognized[key]}\n\n" if is_ocr else native[key]
        room = max_chars - used
        if room <= 0:
            shortened = True
            break
        parts.append(block[:room])
        used += min(room, len(block))
        read_pages += 1
        ocr_pages += int(is_ocr)
        if len(block) > room:
            shortened = True
            break
    text = "".join(parts).strip()
    total = document["pages"]
    missing = total - read_pages
    notices = [f"Đã đọc chữ ở {read_pages}/{total} trang."]
    if ocr_pages:
        notices.append(f"{ocr_pages} trang được nhận dạng từ ảnh scan (OCR); chữ, số và bố cục có thể nhận sai. Kiểm tra bản gốc khi cần trích chính xác.")
    if unavailable and any(str(page) not in recognized for page in candidates):
        notices.append("OCR đang tắt trên máy chủ." if not config.DOCUMENT_OCR_ENABLED else
                       "Máy chủ chưa có bộ OCR; các trang scan chưa đọc được. Gửi PDF có lớp chữ hoặc bản Word nếu cần đọc ngay.")
    if missing:
        notices.append(f"{missing} trang chưa có chữ đọc được đầy đủ; không suy đoán nội dung các trang này.")
    if language_error:
        notices.append("Máy chủ thiếu gói ngôn ngữ OCR đã cấu hình; các trang scan chưa được nhận dạng.")
    if document.get("_skipped_pages"):
        notices.append(f"{document['_skipped_pages']} trang bị lỗi hoặc quá phức tạp nên được bỏ qua.")
    if document["pages_processed"] < total:
        notices.append(f"Chỉ kiểm tra {document['pages_processed']}/{total} trang đầu theo giới hạn đọc tài liệu.")
    if len(candidates) > config.MAX_DOCUMENT_OCR_PAGES:
        notices.append(f"Mỗi tệp nhận dạng tối đa {config.MAX_DOCUMENT_OCR_PAGES} trang scan; hãy chia nhỏ PDF nếu cần đọc thêm.")
    if timed_out:
        notices.append("OCR hết thời gian chờ ở một số trang; phần đã đọc vẫn được giữ lại.")
    if failures:
        notices.append("Một số trang không nhận dạng được: ảnh quá lớn/phức tạp, tệp bị lỗi hoặc bộ OCR chưa sẵn sàng. Thử PDF có chữ hoặc bản nhẹ hơn.")
    if shortened:
        notices.append("Tài liệu dài: chỉ gửi phần đầu đã đọc vào ngữ cảnh; Peto có thể dùng công cụ để tra thêm phần chữ trong giới hạn đọc.")
    return result("partial" if text and (missing or shortened) else "ready" if text else "no_text",
                  " ".join(notices), text, pages=total, pages_processed=document["pages_processed"],
                  pages_read=read_pages, ocr_pages=ocr_pages, reading_method="mixed" if ocr_pages and native else "ocr" if ocr_pages else "text",
                  truncated=shortened, _scan_pages=candidates, _ocr_text=recognized,
                  _ocr_signature=signature, _ocr_attempted=attempted)

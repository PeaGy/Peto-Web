"""Kiểm tra, lưu và đọc tệp đính kèm của hội thoại.

Ảnh được gửi sang xAI dưới dạng data URL. Tệp chữ được trích nội dung rồi
nhét vào prompt. PDF và các file nhị phân khác chỉ được lưu để xem lại —
mô hình nhận một dòng mô tả, không đọc nội dung.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from pathlib import Path

from config import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS,
    MAX_TEXT_EXCERPT_CHARS,
    MAX_TOTAL_ATTACHMENT_BYTES,
    UPLOAD_DIR,
)

IMAGE_MIMES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

TEXT_MIMES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/x-python",
    "text/javascript",
    "text/css",
    "text/html",
    "text/xml",
    "text/x-yaml",
    "application/json",
    "application/javascript",
    "application/xml",
    "application/x-yaml",
}

EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/plain",
    ".tsx": "text/plain",
    ".jsx": "text/plain",
    ".css": "text/css",
    ".html": "text/html",
    ".xml": "text/xml",
    ".yml": "text/x-yaml",
    ".yaml": "text/x-yaml",
    ".rs": "text/plain",
    ".go": "text/plain",
    ".java": "text/plain",
    ".c": "text/plain",
    ".cpp": "text/plain",
    ".h": "text/plain",
    ".sql": "text/plain",
    ".log": "text/plain",
}

class AttachmentError(ValueError):
    """Lỗi tệp đính kèm, đã diễn đạt để hiện cho người dùng."""


@dataclass(frozen=True)
class ValidatedAttachment:
    name: str
    mime: str
    kind: str  # "image" | "file"
    data: bytes


def _safe_filename(name: str) -> str:
    cleaned = Path(str(name or "tep")).name.strip() or "tep"
    return cleaned[:180]


def _ext_of(name: str) -> str:
    return Path(name).suffix.lower()


def sniff_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _looks_like_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def _is_probably_text(data: bytes) -> bool:
    sample = data[:2048]
    if b"\x00" in sample:
        return False
    if not sample:
        return True
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def decode_base64_payload(raw: str) -> bytes:
    text = (raw or "").strip()
    if not text:
        raise AttachmentError("Tệp đính kèm trống")
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    try:
        data = base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError) as err:
        raise AttachmentError("Tệp đính kèm không đọc được") from err
    if not data:
        raise AttachmentError("Tệp đính kèm trống")
    return data


def classify(name: str, declared_mime: str, data: bytes) -> tuple[str, str]:
    """Trả về (kind, mime) sau khi đối chiếu magic bytes và phần mở rộng."""
    filename = _safe_filename(name)
    ext = _ext_of(filename)
    declared = (declared_mime or "").split(";")[0].strip().lower()
    sniffed = sniff_image_mime(data)

    if sniffed:
        return "image", sniffed
    if declared in IMAGE_MIMES or ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise AttachmentError(
            f"«{filename}» không phải ảnh hợp lệ (chỉ nhận JPEG, PNG, WebP, GIF)"
        )

    mime = declared if declared in TEXT_MIMES or declared == "application/pdf" else ""
    if not mime:
        mime = EXT_MIME.get(ext, "")

    if mime == "application/pdf" or ext == ".pdf":
        if not _looks_like_pdf(data):
            raise AttachmentError(f"«{filename}» không phải file PDF hợp lệ")
        return "file", "application/pdf"

    if mime in TEXT_MIMES or ext in EXT_MIME:
        if not _is_probably_text(data):
            raise AttachmentError(f"«{filename}» không phải tệp chữ đọc được")
        return "file", mime or "text/plain"

    raise AttachmentError(
        f"Không nhận loại tệp «{filename}». "
        "Gửi ảnh (JPEG/PNG/WebP/GIF) hoặc tệp chữ/PDF nhé."
    )


def validate_batch(items: list[dict]) -> list[ValidatedAttachment]:
    if len(items) > MAX_ATTACHMENTS:
        raise AttachmentError(f"Mỗi tin chỉ gửi tối đa {MAX_ATTACHMENTS} tệp")

    out: list[ValidatedAttachment] = []
    total = 0
    for item in items:
        name = _safe_filename(str(item.get("name") or "tep"))
        data = decode_base64_payload(str(item.get("data") or ""))
        if len(data) > MAX_ATTACHMENT_BYTES:
            limit_mb = MAX_ATTACHMENT_BYTES / (1024 * 1024)
            raise AttachmentError(
                f"«{name}» quá nặng (tối đa {limit_mb:.0f} MB mỗi tệp)"
            )
        total += len(data)
        if total > MAX_TOTAL_ATTACHMENT_BYTES:
            limit_mb = MAX_TOTAL_ATTACHMENT_BYTES / (1024 * 1024)
            raise AttachmentError(f"Tổng tệp đính kèm vượt {limit_mb:.0f} MB")
        kind, mime = classify(name, str(item.get("mime") or ""), data)
        out.append(ValidatedAttachment(name=name, mime=mime, kind=kind, data=data))
    return out


def write_file(conversation_id: str, item: ValidatedAttachment) -> tuple[str, Path]:
    if item.mime in IMAGE_MIMES:
        ext = IMAGE_MIMES[item.mime]
    elif item.mime == "application/pdf":
        ext = ".pdf"
    else:
        ext = _ext_of(item.name) or ".txt"

    attachment_id = uuid.uuid4().hex
    folder = UPLOAD_DIR / conversation_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{attachment_id}{ext}"
    path.write_bytes(item.data)
    return attachment_id, path


def delete_files(paths: list[str | Path]) -> None:
    for raw in paths:
        path = Path(raw)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        parent = path.parent
        if parent.is_dir() and parent != UPLOAD_DIR:
            try:
                next(parent.iterdir())
            except StopIteration:
                try:
                    parent.rmdir()
                except OSError:
                    pass
            except OSError:
                pass


def as_data_url(path: str | Path, mime: str) -> str:
    data = Path(path).read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def read_text_excerpt(path: str | Path, mime: str) -> str:
    if mime == "application/pdf":
        return ""
    raw = Path(path).read_bytes()
    if not _is_probably_text(raw):
        return ""
    text = raw.decode("utf-8", errors="replace")
    if len(text) > MAX_TEXT_EXCERPT_CHARS:
        return text[:MAX_TEXT_EXCERPT_CHARS] + "\n… (đã cắt bớt)"
    return text

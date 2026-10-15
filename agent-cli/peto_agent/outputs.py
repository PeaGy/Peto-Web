"""Output đầy đủ của lệnh in quá dài (CLI 0.25.0, theo tool-output.ts của opencode).

Kết quả gửi cho Peto chỉ giữ phần đầu và phần cuối (runner.cap_text). Trước đây phần giữa mất hẳn, nên lỗi nằm giữa một
log build dài thì Peto phải chạy lại lệnh. Giờ cả luồng output được ghi vào một tệp trong hồ sơ người dùng (cạnh nhật
ký, không bao giờ trong dự án), tối đa MAX_BYTES; Peto tìm hay đọc phần cần bằng read_output. Output ngắn thì xóa tệp
ngay. Tệp giữ RETENTION_DAYS ngày như ảnh chụp trang.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from pathlib import Path

from .config import outputs_dir

MAX_BYTES = 20 * 1024 * 1024
RETENTION_DAYS = 7
MAX_MATCHES = 40
MAX_LINES = 400
MAX_CHARS = 20_000
ID = re.compile(r"out_[0-9a-f]{12}")


class OutputError(ValueError):
    pass


class Spool:
    """Ghi output của một lệnh khi nó tới. Lỗi đĩa thì thôi ghi: mất bản đầy đủ không được làm hỏng lệnh đang chạy."""

    def __init__(self):
        self.id = "out_" + secrets.token_hex(6)
        self.path = outputs_dir() / f"{self.id}.log"
        self.written = 0
        self.truncated = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self.path, "wb")
        except OSError:
            self._file = None

    def write(self, chunk: bytes) -> None:
        if self._file is None:
            return
        room = MAX_BYTES - self.written
        if room <= 0:
            self.truncated = True
            return
        if len(chunk) > room:
            chunk, self.truncated = chunk[:room], True
        try:
            self._file.write(chunk)
            # Lệnh nền còn đang ghi thì read_output đọc cùng lúc bằng một handle khác: đẩy ra đĩa ngay.
            self._file.flush()
            self.written += len(chunk)
        except OSError:
            self.close()
            self.discard()

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None

    def discard(self) -> None:
        self.close()
        try:
            self.path.unlink()
        except OSError:
            pass

    def keep(self) -> dict | None:
        """Đóng tệp và trả thông tin gửi kèm kết quả lệnh; ghi lỗi giữa chừng thì None."""
        self.close()
        if not self.path.exists():
            return None
        lines = _lines(self.path)
        return {"output_id": self.id, "output_lines": len(lines),
                **({"output_file_truncated": True} if self.truncated else {})}


def _lines(path: Path) -> list[str]:
    text = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    return lines


def prune() -> None:
    cutoff = time.time() - RETENTION_DAYS * 24 * 3600
    try:
        entries = list(outputs_dir().glob("out_*.log"))
    except OSError:
        return
    for entry in entries:
        try:
            if entry.stat().st_mtime < cutoff:
                os.unlink(entry)
        except OSError:
            pass


def read(output_id: str, pattern: str | None = None, start_line: int | None = None,
         end_line: int | None = None) -> dict:
    """Tìm (``pattern``) hoặc đọc theo khoảng dòng trong một output đã lưu."""
    if not ID.fullmatch(output_id or ""):
        raise OutputError("output_id không hợp lệ; dùng đúng mã trong kết quả lệnh.")
    path = outputs_dir() / f"{output_id}.log"
    if not path.is_file():
        raise OutputError(f"Không còn output {output_id} (output chỉ giữ {RETENTION_DAYS} ngày, hoặc lệnh không in "
                          "quá dài nên không lưu).")
    lines = _lines(path)
    total = len(lines)
    if pattern:
        try:
            regex = re.compile(pattern)
        except re.error as err:
            raise OutputError(f"pattern không phải biểu thức chính quy hợp lệ: {err}") from None
        matches, count = [], 0
        for number, line in enumerate(lines, 1):
            if regex.search(line):
                count += 1
                if len(matches) < MAX_MATCHES:
                    matches.append({"line": number, "text": line[:500]})
        return {"output_id": output_id, "total_lines": total, "matches": matches, "total_matches": count,
                "truncated": count > len(matches)}
    start = max(1, start_line or 1)
    if total and start > total:
        raise OutputError(f"Output này chỉ có {total} dòng.")
    end = min(total, end_line or total, start + MAX_LINES - 1)
    chosen, size = [], 0
    for number in range(start, end + 1):
        text = f"{number:>6}\t{lines[number - 1]}"
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + f" … (dòng này dài {len(lines[number - 1])} ký tự, đã cắt)"
        if chosen and size + len(text) + 1 > MAX_CHARS:
            end = number - 1
            break
        chosen.append(text)
        size += len(text) + 1
    return {"output_id": output_id, "start_line": start, "end_line": end, "total_lines": total,
            "content": "\n".join(chosen), **({"next_start_line": end + 1, "truncated": True} if end < total else {})}

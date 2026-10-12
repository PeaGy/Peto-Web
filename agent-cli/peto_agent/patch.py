"""Đọc và áp bản patch kiểu apply_patch cho model GPT (CLI 0.21.0, chủ web chọn ngày 2026-10-12).

Chuyển từ ``packages/util/src/patch.ts`` của opencode (MIT License, Copyright (c) 2025 opencode,
https://github.com/anomalyco/opencode). opencode thay edit/write bằng công cụ này khi model là GPT, vì GPT được huấn
luyện với định dạng đó:

    *** Begin Patch
    *** Add File: đường/mới.py          (mọi dòng sau bắt đầu bằng +)
    *** Delete File: đường/cũ.txt
    *** Update File: đường/app.py
    *** Move to: đường/main.py          (tùy chọn)
    @@ def greet():                     (ngữ cảnh: tìm đoạn từ sau dòng này)
     dòng giữ nguyên
    -dòng bỏ
    +dòng thêm
    *** End Patch

Khác opencode: tìm đoạn khớp theo luật "chặt" chủ web đã duyệt cho edit_v2 (nguyên văn, rồi bỏ khoảng trắng cuối
dòng, rồi bỏ khoảng trắng hai đầu; không đổi dấu nháy hay gạch ngang Unicode), và đoạn phải khớp đúng một chỗ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BEGIN, END = "*** Begin Patch", "*** End Patch"
ADD, DELETE, UPDATE, MOVE = "*** Add File: ", "*** Delete File: ", "*** Update File: ", "*** Move to: "
END_OF_FILE = "*** End of File"
HEREDOC = re.compile(r"^(?:cat\s+)?<<(['\"]?)(\w+)\1\s*\n([\s\S]*?)\n\2\s*$")


class PatchError(ValueError):
    """Bản patch sai định dạng hay không khớp tệp; chữ lỗi gửi lại cho Peto để sửa rồi gọi lại."""


@dataclass
class Chunk:
    old: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    context: str | None = None
    end_of_file: bool = False


@dataclass
class Op:
    kind: str  # "add", "delete", "update"
    path: str
    contents: str = ""
    move_to: str | None = None
    chunks: list[Chunk] = field(default_factory=list)


def _boundary(line: str) -> bool:
    return line == END or line.startswith((ADD, DELETE, UPDATE))


def parse(text: str) -> list[Op]:
    """Các thao tác của bản patch; sai định dạng thì PatchError nói đúng dòng sai."""
    stripped = text.strip()
    if match := HEREDOC.match(stripped):
        stripped = match.group(3)
    lines = [line[:-1] if line.endswith("\r") else line for line in stripped.split("\n")]
    if not lines or lines[0].strip() != BEGIN:
        raise PatchError(f"Dòng đầu của bản patch phải là '{BEGIN}'.")
    if len(lines) < 2 or lines[-1].strip() != END:
        raise PatchError(f"Dòng cuối của bản patch phải là '{END}'.")
    end = len(lines) - 1
    ops: list[Op] = []
    index = 1
    while index < end:
        header = lines[index].strip()
        if header.startswith(ADD):
            path = header[len(ADD):].strip()
            index += 1
            content = []
            while index < end and not _boundary(lines[index].strip()):
                if not lines[index].startswith("+"):
                    raise PatchError(f"Dòng {index + 1}: tệp mới {path} chỉ gồm các dòng bắt đầu bằng '+', gặp "
                                     f"'{lines[index].strip()}'.")
                content.append(lines[index][1:])
                index += 1
            ops.append(Op("add", path, "\n".join(content) + ("\n" if content else "")))
            continue
        if header.startswith(DELETE):
            path = header[len(DELETE):].strip()
            if index + 1 < end and not _boundary(lines[index + 1].strip()):
                raise PatchError(f"Dòng {index + 2}: mục xóa {path} không có dòng nào theo sau.")
            ops.append(Op("delete", path))
            index += 1
            continue
        if header.startswith(UPDATE):
            path = header[len(UPDATE):].strip()
            index += 1
            move_to = None
            if index < end and lines[index].rstrip().startswith(MOVE.rstrip()):
                move_to = lines[index].rstrip()[len(MOVE.rstrip()):].strip()
                if not move_to:
                    raise PatchError(f"Dòng {index + 1}: '{MOVE.strip()}' của {path} thiếu đường dẫn mới.")
                index += 1
            chunks, index = _update(lines, index, end, path)
            ops.append(Op("update", path, move_to=move_to, chunks=chunks))
            continue
        raise PatchError(f"Dòng {index + 1}: '{header}' không phải đầu mục hợp lệ (dùng '{ADD.strip()}', "
                         f"'{DELETE.strip()}' hoặc '{UPDATE.strip()}').")
    return ops


def _update(lines: list[str], index: int, end: int, path: str) -> tuple[list[Chunk], int]:
    chunks: list[Chunk] = []
    start = index
    while index < end:
        line = lines[index]
        bare = line.rstrip()
        if bare == END_OF_FILE:
            if chunks:
                chunks[-1].end_of_file = True
            index += 1
            continue
        if _boundary(bare):
            break
        if bare == "@@" or bare.startswith("@@ "):
            if chunks and not chunks[-1].old and not chunks[-1].new:
                raise PatchError(f"Dòng {index + 1}: đoạn @@ trước của {path} không có dòng nào.")
            chunks.append(Chunk(context=None if bare == "@@" else bare[3:]))
            index += 1
            continue
        if not chunks:
            chunks.append(Chunk())
        chunk = chunks[-1]
        if line == "":
            chunk.old.append("")
            chunk.new.append("")
        elif line[0] == " ":
            chunk.old.append(line[1:])
            chunk.new.append(line[1:])
        elif line[0] == "-":
            chunk.old.append(line[1:])
        elif line[0] == "+":
            chunk.new.append(line[1:])
        else:
            raise PatchError(f"Dòng {index + 1}: trong mục sửa {path}, mỗi dòng phải bắt đầu bằng ' ' (giữ), '-' "
                             f"(bỏ) hoặc '+' (thêm); gặp '{line}'.")
        index += 1
    if not chunks or (not chunks[-1].old and not chunks[-1].new):
        raise PatchError(f"Dòng {start}: mục sửa {path} không có thay đổi nào.")
    return chunks, index


COMPARES = (lambda a, b: a == b, lambda a, b: a.rstrip() == b.rstrip(), lambda a, b: a.strip() == b.strip())


def _seek(lines: list[str], pattern: list[str], start: int, path: str, *, end_of_file: bool = False,
          unique: bool = True) -> int:
    """Chỗ đoạn ``pattern`` khớp, tìm từ ``start``; theo thứ tự nguyên văn, bỏ khoảng trắng cuối, hai đầu. ``unique``
    bắt chỉ một chỗ khớp; sau dòng @@ ngữ cảnh thì lấy chỗ đầu tiên sau nó, vì dòng đó đã neo vị trí."""
    if not pattern:
        return -1
    for compare in COMPARES:
        offsets = [len(lines) - len(pattern)] if end_of_file else range(start, len(lines) - len(pattern) + 1)
        found = [offset for offset in offsets if offset >= start
                 and all(compare(lines[offset + i], line) for i, line in enumerate(pattern))]
        if len(found) > 1 and unique:
            numbers = ", ".join(str(offset + 1) for offset in found[:8])
            raise PatchError(f"Đoạn cần sửa khớp {len(found)} chỗ trong {path} (dòng {numbers}); thêm vài dòng giữ "
                             "nguyên xung quanh, hoặc dòng @@ ngữ cảnh, cho chỉ khớp một chỗ.")
        if found:
            return found[0]
    return -1


def apply(text: str, chunks: list[Chunk], path: str) -> str:
    """Nội dung mới của tệp (chữ đã bỏ BOM, xuống dòng \\n). Không khớp thì PatchError, không đổi gì."""
    lines = text.split("\n")
    final_newline = lines[-1] == ""
    if final_newline:
        lines.pop()
    replacements: list[tuple[int, int, list[str]]] = []
    position = 0
    for chunk in chunks:
        if chunk.context:
            found = _seek(lines, [chunk.context], position, path)
            if found < 0:
                raise PatchError(f"Không thấy dòng ngữ cảnh '@@ {chunk.context}' trong {path}. Đọc lại tệp rồi chép "
                                 "đúng dòng đó.")
            position = found + 1
        if not chunk.old:
            replacements.append((len(lines), 0, chunk.new))
            continue
        old, new = chunk.old, chunk.new
        found = _seek(lines, old, position, path, end_of_file=chunk.end_of_file, unique=not chunk.context)
        if found < 0 and old[-1] == "":
            old, new = old[:-1], (new[:-1] if new and new[-1] == "" else new)
            found = _seek(lines, old, position, path, end_of_file=chunk.end_of_file, unique=not chunk.context)
        if found < 0:
            preview = "\n".join(chunk.old[:12])
            raise PatchError(f"Không thấy đoạn cần sửa trong {path} (kể cả khi bỏ qua khoảng trắng đầu, cuối dòng):\n"
                             f"{preview}\nĐọc lại tệp rồi chép đúng các dòng ' ' và '-'.")
        replacements.append((found, len(old), new))
        position = found + len(old)
    for start, remove, insert in sorted(replacements, key=lambda item: item[0], reverse=True):
        lines[start:start + remove] = insert
    return "\n".join(lines) + ("\n" if final_newline or not text else "")

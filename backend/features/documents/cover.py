"""Trang bìa: thông tin ghi ở đầu nội dung Markdown trong khối --- … ---, mỗi dòng "khóa: giá trị".

Ví dụ:

    ---
    trường: Trường Đại học Công nghệ
    khoa: Khoa Công nghệ Thông tin
    loại: Báo cáo thực hành giữa kỳ
    môn: Dịch vụ mạng
    giảng viên: ThS. Nguyễn Văn A
    nhóm: Nhóm 7
    thành viên:
    - Nguyễn Văn B | 124001022 | Nhóm trưởng
    - Trần Thị C | 124001764
    nơi: TP. Hồ Chí Minh
    ---

Thông tin nằm ngay trong nội dung nên người dùng sửa được tên trường hay MSSV trong ô "Sửa nội dung" mà không cần nhờ
Peto. Peto chỉ ghi điều người dùng đã đưa: thiếu tên trường, khoa hay giảng viên thì bìa để dòng chấm cho họ điền, không
tự bịa. Thiếu ngày thì lấy tháng năm hiện tại theo giờ máy chủ.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

DOTS = "……………………………"
MAX_MEMBERS = 15
MAX_VALUE = 200
IMAGE_REF = re.compile(r"#?(?:anh|ảnh)[-_: ]?(\d{1,3})", re.IGNORECASE)

# Khóa viết không dấu, chữ thường → thuộc tính. Có thêm tên tiếng Anh cho người viết bằng tiếng Anh.
_KEYS = {
    "co quan": "authority", "co quan chu quan": "authority", "bo": "authority", "authority": "authority",
    "truong": "school", "school": "school", "university": "school",
    "khoa": "faculty", "vien": "faculty", "faculty": "faculty", "department": "faculty",
    "loai": "kind", "loai bai": "kind", "kind": "kind", "type": "kind",
    "mon": "course", "mon hoc": "course", "hoc phan": "course", "course": "course", "subject": "course",
    "de tai": "topic", "ten de tai": "topic", "topic": "topic",
    "phu de": "subtitle", "subtitle": "subtitle",
    "giang vien": "instructor", "giang vien huong dan": "instructor", "gvhd": "instructor", "instructor": "instructor",
    "supervisor": "instructor",
    "nhom": "group", "nhom thuc hien": "group", "group": "group", "team": "group",
    "lop": "class_name", "class": "class_name",
    "thanh vien": "members", "sinh vien": "members", "sinh vien thuc hien": "members", "nguoi thuc hien": "members",
    "hoc vien": "members", "hoc sinh": "members", "tac gia": "members", "members": "members", "students": "members",
    "authors": "members",
    "noi": "place", "dia diem": "place", "place": "place", "city": "place",
    "ngay": "date", "thoi gian": "date", "thang": "date", "date": "date",
    "logo": "logo",
}
ALLOWED = "trường, khoa, cơ quan, loại, môn, đề tài, phụ đề, giảng viên, nhóm, lớp, thành viên, nơi, ngày, logo"


@dataclass
class Member:
    name: str
    code: str = ""
    note: str = ""


@dataclass
class Cover:
    authority: str = ""
    school: str = ""
    faculty: str = ""
    kind: str = ""
    course: str = ""
    topic: str = ""
    subtitle: str = ""
    instructor: str = ""
    group: str = ""
    class_name: str = ""
    place: str = ""
    date: str = ""
    logo: int = 0
    members: list[Member] = field(default_factory=list)

    def when(self) -> str:
        """Nơi và thời gian ở chân bìa: "TP. Hồ Chí Minh, tháng 10 năm 2026"."""
        date = self.date or current_month()
        return f"{self.place}, {date}" if self.place else date[:1].upper() + date[1:]


def current_month() -> str:
    from zoneinfo import ZoneInfo

    from core.config import DEFAULT_TIMEZONE
    try:
        now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    except Exception:
        now = datetime.now()
    return f"tháng {now.month} năm {now.year}"


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.strip().casefold()).replace("đ", "d")
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def _member(text: str) -> Member:
    text = text.strip().lstrip("-*+").strip()
    text = re.sub(r"^\d+[.)]\s+", "", text)
    parts = [part.strip() for part in (text.split("|") if "|" in text else re.split(r"\s+[-–—]\s+", text))]
    parts = [part for part in parts if part] or [text]
    name = parts[0][:MAX_VALUE]
    code = parts[1][:60] if len(parts) > 1 else ""
    note = " – ".join(parts[2:])[:80] if len(parts) > 2 else ""
    return Member(name, code, note)


def split_cover(content: str) -> tuple[Cover | None, str]:
    """(Bìa, phần nội dung còn lại). Không có khối --- … --- ở đầu thì không có bìa. Khóa lạ bị từ chối kèm danh sách
    khóa dùng được, để Peto sửa rồi gọi lại công cụ."""
    stripped = content.lstrip("﻿")
    lines = stripped.split("\n")
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None or lines[first].strip() != "---":
        return None, content
    end = next((index for index in range(first + 1, min(len(lines), first + 80)) if lines[index].strip() == "---"), None)
    if end is None:
        return None, content
    cover = Cover()
    current = None
    for raw in lines[first + 1:end]:
        line = raw.strip()
        if not line:
            continue
        if current == "members" and line[:1] in "-*+" or (current == "members" and re.match(r"^\d+[.)]\s", line)):
            if len(cover.members) >= MAX_MEMBERS:
                raise ValueError(f"Bìa ghi tối đa {MAX_MEMBERS} thành viên.")
            cover.members.append(_member(line))
            continue
        key, separator, value = line.partition(":")
        name = _KEYS.get(_fold(key)) if separator else None
        if name is None:
            raise ValueError(f'Trang bìa không hiểu dòng "{line[:60]}". Mỗi dòng là "khóa: giá trị" với khóa: {ALLOWED}.')
        value = " ".join(value.split())[:MAX_VALUE]
        current = name
        if name == "members":
            for piece in (value.split(";") if value else []):
                if piece.strip():
                    cover.members.append(_member(piece))
            continue
        if name == "logo":
            match = IMAGE_REF.search(value)
            cover.logo = int(match.group(1)) if match else 0
            continue
        setattr(cover, name, value)
    rest = "\n".join(lines[end + 1:])
    return cover, rest

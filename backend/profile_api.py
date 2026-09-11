"""Hồ sơ người dùng tự điền trong Cài đặt: tên, cách Peto gọi, công việc và
hướng dẫn riêng.

Máy chủ ghép hồ sơ vào prompt ở MỖI lượt chat (xem ``main._build_system_prompt``),
nên sửa xong là tin nhắn kế tiếp đã theo — không có bộ nhớ đệm nào phải chờ.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import db
from auth import current_owner

router = APIRouter(tags=["profile"])

MAX_FULL_NAME = 80
MAX_NICKNAME = 40
MAX_INSTRUCTIONS = 1500

# Giá trị lưu trong DB là mã ổn định; nhãn tiếng Việt chỉ để hiển thị và ghép
# vào prompt, nên đổi chữ thoải mái mà không làm hỏng dữ liệu đã lưu.
OCCUPATIONS: tuple[tuple[str, str], ...] = (
    ("student", "Học sinh, sinh viên"),
    ("software", "Lập trình, kỹ thuật phần mềm"),
    ("data", "Dữ liệu, AI"),
    ("design", "Thiết kế"),
    ("writing", "Viết lách, sáng tạo nội dung"),
    ("marketing", "Marketing, truyền thông"),
    ("business", "Kinh doanh, bán hàng"),
    ("operations", "Vận hành, quản lý"),
    ("education", "Giáo dục"),
    ("research", "Nghiên cứu, khoa học"),
    ("health", "Y tế, sức khỏe"),
    ("finance", "Tài chính, kế toán"),
    ("legal", "Pháp lý"),
    ("other", "Khác"),
)
_LABELS = dict(OCCUPATIONS)

# Ký tự điều khiển (trừ xuống dòng và tab) không có chỗ trong tên hay lời dặn,
# và có thể làm rối khối prompt.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def occupation_label(value: str) -> str:
    return _LABELS.get(value, "")


def _one_line(value: str) -> str:
    return " ".join(_CONTROL.sub(" ", value.replace("\t", " ")).split())


def _multi_line(value: str) -> str:
    text = _CONTROL.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))
    # Gộp các chuỗi dòng trống dài: dán cả trang cũng không làm phình prompt.
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class ProfileIn(BaseModel):
    # Trần cứng chỉ để chặn thân yêu cầu khổng lồ. Giới hạn thật kiểm tra ở
    # dưới, để báo lỗi bằng tiếng Việt thay vì lỗi 422 tiếng Anh của Pydantic.
    full_name: str = Field(default="", max_length=4000)
    nickname: str = Field(default="", max_length=4000)
    occupation: str = Field(default="", max_length=100)
    instructions: str = Field(default="", max_length=20000)


def _public(profile: dict) -> dict:
    return {field: profile.get(field, "") for field in db.PROFILE_FIELDS}


@router.get("/api/profile")
async def read_profile(owner: str = Depends(current_owner)) -> dict:
    return {
        "profile": _public(await db.get_profile(owner)),
        "occupations": [{"value": value, "label": label} for value, label in OCCUPATIONS],
        "limits": {
            "full_name": MAX_FULL_NAME,
            "nickname": MAX_NICKNAME,
            "instructions": MAX_INSTRUCTIONS,
        },
    }


@router.put("/api/profile")
async def update_profile(body: ProfileIn, owner: str = Depends(current_owner)) -> dict:
    full_name = _one_line(body.full_name)
    nickname = _one_line(body.nickname)
    occupation = body.occupation.strip()
    instructions = _multi_line(body.instructions)

    if len(full_name) > MAX_FULL_NAME:
        raise HTTPException(400, f"Họ và tên dài quá, tối đa {MAX_FULL_NAME} ký tự nhé.")
    if len(nickname) > MAX_NICKNAME:
        raise HTTPException(400, f"Tên để Peto gọi dài quá, tối đa {MAX_NICKNAME} ký tự nhé.")
    if occupation and occupation not in _LABELS:
        raise HTTPException(400, "Công việc này không có trong danh sách. Bạn chọn lại nhé.")
    if len(instructions) > MAX_INSTRUCTIONS:
        raise HTTPException(
            400, f"Hướng dẫn cho Peto dài quá, tối đa {MAX_INSTRUCTIONS} ký tự nhé."
        )

    await db.save_profile(
        owner=owner,
        full_name=full_name,
        nickname=nickname,
        occupation=occupation,
        instructions=instructions,
    )
    return {"profile": _public(await db.get_profile(owner))}

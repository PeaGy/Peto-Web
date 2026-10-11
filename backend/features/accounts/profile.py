"""Hồ sơ người dùng tự điền trong Cài đặt: tên, cách Peto gọi, công việc và
hướng dẫn riêng.

Máy chủ ghép hồ sơ vào prompt ở MỖI lượt chat (xem ``features.chat.prompt_context._build_system_prompt``),
nên sửa xong là tin nhắn kế tiếp đã theo — không có bộ nhớ đệm nào phải chờ.
"""

from __future__ import annotations

import re
from io import BytesIO
import warnings
import anyio
from PIL import Image, ImageOps, UnidentifiedImageError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import storage as db
from storage import avatars
from features.accounts.auth import current_owner

router = APIRouter(tags=["profile"])

MAX_FULL_NAME = 80
MAX_NICKNAME = 40
MAX_INSTRUCTIONS = 1500
MAX_AVATAR_BYTES = 10 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000
AVATAR_TYPES = {'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/webp': 'WEBP'}

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
        "avatar": avatars.info(await db.get_user(owner) or {}),
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


def _prepare_avatar(data: bytes, mime: str) -> bytes:
    """Kiểm tra ảnh thật, bỏ metadata và thu về ảnh vuông 512px để tải nhanh."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format != AVATAR_TYPES[mime]:
                    raise HTTPException(400, 'Nội dung ảnh không đúng định dạng. Chọn PNG, JPEG hoặc WebP nhé.')
                if source.width * source.height > MAX_AVATAR_PIXELS:
                    raise HTTPException(400, 'Ảnh có độ phân giải quá lớn. Chọn ảnh dưới 16 triệu điểm ảnh nhé.')
                source.load()
                image = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGBA'), (512, 512), method=Image.Resampling.LANCZOS)
                image.info.clear()
                output = BytesIO()
                image.save(output, 'PNG')
                return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(400, 'Không đọc được ảnh. Chọn PNG, JPEG hoặc WebP hợp lệ nhé.') from None


@router.put('/api/profile/avatar')
async def upload_avatar(request: Request, owner: str = Depends(current_owner)) -> dict:
    mime = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if mime not in AVATAR_TYPES:
        raise HTTPException(400, 'Chọn ảnh PNG, JPEG hoặc WebP nhé.')
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_AVATAR_BYTES:
            raise HTTPException(413, 'Ảnh quá lớn. Chọn ảnh tối đa 10 MB nhé.')
        content.extend(chunk)
    prepared = await anyio.to_thread.run_sync(_prepare_avatar, bytes(content), mime)
    await avatars.save(owner, prepared)
    return avatars.info(await db.get_user(owner) or {})


@router.delete('/api/profile/avatar')
async def reset_avatar(owner: str = Depends(current_owner)) -> dict:
    await avatars.reset(owner)
    return avatars.info(await db.get_user(owner) or {})


@router.get('/api/profile/avatar')
async def read_avatar(owner: str = Depends(current_owner)) -> Response:
    data = await avatars.get(owner)
    if data is None:
        raise HTTPException(404, 'Chưa có ảnh đại diện riêng.')
    return Response(data, media_type='image/png', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post("/api/profile/roleplay-consent")
async def confirm_roleplay_age(owner: str = Depends(current_owner)) -> dict:
    """Người dùng tự xác nhận đủ 18 tuổi để bật chế độ nhập vai. Chỉ hỏi một lần cho mỗi tài khoản. Máy chủ còn kiểm lại lúc mở hội thoại nhập vai."""
    await db.add_roleplay_consent(owner)
    return {"roleplay_confirmed": True}

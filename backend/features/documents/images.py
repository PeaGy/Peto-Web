"""Ảnh người dùng đã gửi trong hội thoại, để chèn vào tài liệu Peto tạo (document_export).

Chỉ đọc ảnh của đúng tài khoản và hội thoại, lọc trong SQL, qua đường dẫn máy chủ đã lưu. Không bao giờ tải ảnh từ một địa
chỉ model hay người dùng viết. "Ảnh N" đánh số theo thứ tự gửi trong hội thoại, giống nhãn model thấy cạnh ảnh
(db._attach_files). Tin nhắn chỉ bị xóa cùng cả hội thoại, và phiên bản mới của hội thoại chép ảnh theo đúng thứ tự, nên số
của một ảnh không đổi.
"""
from io import BytesIO
from pathlib import Path

import anyio

import storage as db
from shared.attachments import sniff_image_mime
from core.config import UPLOAD_DIR
from features.documents.export import DocImage

# Cạnh dài tối đa khi nhúng: đủ nét cho khổ A4, tệp vẫn nhỏ (mỗi tài khoản có 32 MB tệp xuất).
MAX_SIDE = 1600
# Ảnh giải nén quá lớn (chẳng hạn một PNG nhỏ nhưng 20.000 × 20.000 điểm ảnh) làm tràn RAM của VPS.
MAX_PIXELS = 40_000_000
# PNG lớn hơn mức này sau khi thu nhỏ (thường là ảnh chụp) được đổi sang JPEG.
MAX_PNG_BYTES = 600_000


async def load(owner: str, conversation_id: str, numbers: set[int], *, strict: bool,
               tool: str = 'create_document') -> dict[int, bytes]:
    """Đọc các ảnh số ``numbers`` của hội thoại.

    ``strict`` dùng cho công cụ của model: số không có thì báo lỗi để model sửa rồi gọi lại. Bản người dùng tự sửa thì bỏ
    qua, và chỗ ảnh hiện thành chữ.
    """
    if not numbers:
        return {}
    rows = await db.conversation_images(owner, conversation_id)
    missing = sorted(number for number in numbers if not 1 <= number <= len(rows))
    if missing and strict:
        if not rows:
            raise ValueError('Hội thoại này chưa có ảnh nào người dùng gửi nên chưa chèn được ảnh. '
                             f'Bỏ {"phần ![…](anh-N)" if tool == "create_document" else "slide image_text"} '
                             f'rồi gọi lại {tool}, hoặc nhờ người dùng gửi ảnh trước.')
        have = ', '.join(f'Ảnh {number}' for number in range(1, len(rows) + 1))
        wanted = ', '.join(f'Ảnh {number}' for number in missing)
        raise ValueError(f'Hội thoại này không có {wanted}. Ảnh người dùng đã gửi: {have}. '
                         f'Sửa số ảnh rồi gọi lại {tool}.')
    root = UPLOAD_DIR.resolve()
    result: dict[int, bytes] = {}
    for number in sorted(set(numbers) - set(missing)):
        path = Path(rows[number - 1]['path']).resolve()
        try:
            if not path.is_relative_to(root):
                raise OSError('Ảnh nằm ngoài thư mục tải lên')
            result[number] = await anyio.to_thread.run_sync(path.read_bytes)
        except OSError as error:
            if strict:
                raise ValueError(f'Không đọc được Ảnh {number} trên máy chủ. Bỏ ảnh này khỏi content rồi gọi lại.') from error
    return result


def prepare(data: bytes) -> DocImage:
    """Thu nhỏ một ảnh để nhúng: xoay theo EXIF, cạnh dài tối đa MAX_SIDE, giữ nền trong suốt bằng PNG, còn lại JPEG."""
    from PIL import Image, ImageOps

    if not sniff_image_mime(data):
        raise ValueError('Không phải ảnh PNG, JPEG, GIF hay WebP.')
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > MAX_PIXELS:
            raise ValueError('Ảnh quá lớn.')
        source.draft('RGB', (MAX_SIDE, MAX_SIDE))  # JPEG giải nén thẳng ở cỡ nhỏ, đỡ tốn RAM
        lossless = source.format in ('PNG', 'GIF')  # ảnh chụp màn hình, sơ đồ: giữ nét chữ
        image = ImageOps.exif_transpose(source)
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        transparent = image.mode in ('RGBA', 'LA', 'PA') or (image.mode == 'P' and 'transparency' in image.info)
        output = BytesIO()
        if transparent:
            image.convert('RGBA').save(output, 'PNG', optimize=True)
        else:
            image = image.convert('RGB')
            if lossless:
                image.save(output, 'PNG', optimize=True)
            if not lossless or output.tell() > MAX_PNG_BYTES:
                output = BytesIO()
                image.save(output, 'JPEG', quality=85, optimize=True)
        return DocImage(output.getvalue(), image.width, image.height)


def prepare_all(raw: dict[int, bytes], *, strict: bool) -> dict[int, DocImage]:
    """Thu nhỏ mọi ảnh của một tài liệu; chạy trong luồng dựng tài liệu vì tốn CPU."""
    images: dict[int, DocImage] = {}
    for number, data in raw.items():
        try:
            images[number] = prepare(data)
        except Exception as error:
            if strict:
                raise ValueError(f'Không dùng được Ảnh {number} trong tài liệu (tệp hỏng hoặc quá lớn). '
                                 'Bỏ ảnh này khỏi content rồi gọi lại.') from error
    return images

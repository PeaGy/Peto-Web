"""Ảnh Word được tham chiếu trong phần thân, chuẩn hóa trong tiến trình đọc tài liệu.

Không đọc ảnh thừa trong gói, không tải URL hay giải nén ra ổ đĩa. Kết quả chỉ lưu nội bộ;
phần metadata gửi trình duyệt không chứa bitmap hoặc đường dẫn trong gói Word.
"""
from __future__ import annotations

import base64
import io
import math
import posixpath
import warnings
from urllib.parse import unquote

from PIL import Image, ImageOps

from features.documents.word_reader import parse

MAX_IMAGES = 8
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_PIXELS = 20_000_000
MAX_IMAGE_PIXELS = 4_000_000
MAX_EDGE = 2048
MAX_IMAGE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024
REL_NAMESPACE = 'http://schemas.openxmlformats.org/package/2006/relationships'


def _relationships(archive, max_xml_bytes: int) -> dict[str, str]:
    try:
        info = archive.getinfo('word/_rels/document.xml.rels')
    except KeyError:
        return {}
    if info.file_size > max_xml_bytes or info.flag_bits & 1:
        return {}
    root = parse(archive.read(info))
    if root.tag != f'{{{REL_NAMESPACE}}}Relationships':
        return {}
    result = {}
    for item in root:
        if (item.tag != f'{{{REL_NAMESPACE}}}Relationship' or item.get('TargetMode', 'Internal') != 'Internal'
                or not item.get('Type', '').endswith('/image')):
            continue
        target = unquote(item.get('Target', ''))
        if '\\' in target or ':' in target or '?' in target or '#' in target or '\x00' in target:
            continue
        path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('word', target))
        if path.startswith('word/media/'):
            identity = item.get('Id', '')
            if not identity or identity in result:
                return {}
            result[identity] = path
    return result


def _prepare(data: bytes, spec: dict) -> tuple[bytes, str, int, int]:
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {'PNG', 'JPEG', 'WEBP', 'GIF', 'BMP', 'TIFF'}:
                raise ValueError('Định dạng ảnh Word chưa được hỗ trợ')
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise ValueError('Ảnh Word gốc quá lớn')
            source.load()
            image = ImageOps.exif_transpose(source).convert('RGBA')
            crop = spec.get('crop') or {}
            if crop:
                width, height = image.size
                left, top, right, bottom = (int(crop.get(k, 0)) / 100000 for k in ('l', 't', 'r', 'b'))
                if not all(0 <= n < 1 for n in (left, top, right, bottom)) or left + right >= 1 or top + bottom >= 1:
                    raise ValueError('Vùng cắt ảnh Word không hợp lệ')
                box = (round(width * left), round(height * top), round(width * (1 - right)), round(height * (1 - bottom)))
                if box[0] >= box[2] or box[1] >= box[3]:
                    raise ValueError('Vùng cắt ảnh Word quá nhỏ')
                image = image.crop(box)
            scale = min(1, MAX_EDGE / max(image.size), math.sqrt(MAX_IMAGE_PIXELS / (image.width * image.height)))
            if scale < 1:
                image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
            if spec.get('flip_h'):
                image = ImageOps.mirror(image)
            if spec.get('flip_v'):
                image = ImageOps.flip(image)
            rotation = int(spec.get('rotation') or 0) / 60000
            if rotation % 360:
                image = image.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
                image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            image.info.clear()
            output = io.BytesIO()
            image.save(output, 'PNG')
            mime = 'image/png'
            if output.tell() > MAX_IMAGE_BYTES:
                # Ảnh chụp thường nặng hơn sơ đồ: JPEG giúp giữ độ phân giải mà chặn cỡ ngữ cảnh.
                canvas = Image.new('RGB', image.size, 'white')
                canvas.paste(image, mask=image.getchannel('A'))
                output = io.BytesIO()
                canvas.save(output, 'JPEG', quality=85)
                mime = 'image/jpeg'
            if output.tell() > MAX_IMAGE_BYTES:
                raise ValueError('Ảnh Word sau xử lý quá nặng')
            return output.getvalue(), mime, image.width, image.height


def extract(archive, specs: list[dict], max_xml_bytes: int) -> list[dict]:
    """Giữ số hình ở vị trí đọc, cả khi hình trước đó bị lỗi hoặc không được nhúng."""
    try:
        relationships = _relationships(archive, max_xml_bytes)
    except Exception:
        return []
    result = []
    total = attempts = 0
    for spec in specs:
        if attempts >= MAX_IMAGES:
            break
        attempts += 1
        try:
            path = relationships.get(spec.get('relationship', ''))
            if not path:
                continue
            info = archive.getinfo(path)
            if info.file_size > MAX_SOURCE_BYTES or info.flag_bits & 1:
                continue
            data, mime, width, height = _prepare(archive.read(info), spec)
            if total + len(data) > MAX_TOTAL_BYTES:
                continue
            total += len(data)
            result.append({'number': spec['number'], 'mime': mime, 'width': width, 'height': height,
                           'data_url': f'data:{mime};base64,{base64.b64encode(data).decode("ascii")}'})
        except Exception:
            # Hình hỏng không được làm mất phần chữ hoặc các hình hợp lệ khác của tài liệu.
            continue
    return result

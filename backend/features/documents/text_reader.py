"""Đọc văn bản nghiêm ngặt, biểu diễn ký tự điều khiển lẻ mà không đổi số dòng."""
from __future__ import annotations

import codecs
import re

# TAB/CR/LF là cấu trúc văn bản. Các C0/C1 còn lại phải hiện ra thành ký hiệu, không đi vào prompt như lệnh terminal.
CONTROLS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
MAX_CONTROL_CHARS = 4096
CONTROL_RATIO = 100  # Tối đa 1%; không coi một tệp có nhiều byte nhị phân là văn bản chỉ vì giải mã UTF-8 được.
TEXT_FORMAT = 1


def read_text(data: bytes) -> tuple[str, dict]:
    # UTF-32 LE cũng mở đầu bằng BOM của UTF-16 LE: kiểm UTF-32 trước.
    encoding = ('utf-32' if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)) else
                'utf-16' if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else 'utf-8-sig')
    text = data.decode(encoding)
    count = sum(1 for _ in CONTROLS.finditer(text))
    if count > MAX_CONTROL_CHARS or count * CONTROL_RATIO > len(text):
        raise ValueError('Tệp chứa quá nhiều dữ liệu nhị phân hoặc ký tự điều khiển.')
    if count:
        text = CONTROLS.sub(lambda match: f'[U+{ord(match[0]):04X}]', text)
    return text, {'text_format': TEXT_FORMAT, 'encoding': encoding, 'normalized_controls': count}


def decode_text(data: bytes) -> str:
    return read_text(data)[0]


def normalization_notice(details: dict) -> str:
    count = details.get('normalized_controls', 0)
    return (f' Đã biểu diễn {count} ký tự điều khiển bất thường dưới dạng [U+XXXX]; '
            'giữ nguyên dòng và tệp gốc.' if count else '')

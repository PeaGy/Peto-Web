"""Ba phong cách chủ web chọn từ trang mẫu ngày 2026-10-04 (frontend/prototypes/slides): Gọn sáng, Học thuật, Đậm nét.

Màu viết dạng hex không có dấu #. Mỗi phong cách có bảng màu biểu đồ riêng: một chuỗi số liệu thì dùng màu nhấn, nhiều chuỗi
thì các chuỗi trước dùng màu phụ và chuỗi cuối (thường là năm gần nhất) dùng màu nhấn.
"""
from dataclasses import dataclass

from features.documents.slides.fonts import SANS, SERIF


@dataclass(frozen=True)
class Theme:
    name: str
    label: str
    heading: str            # phông tiêu đề
    ink: str                # chữ chính
    muted: str              # chữ phụ, chú thích
    accent: str             # màu nhấn
    hair: str               # đường kẻ mảnh
    series: tuple[str, ...]  # màu các chuỗi đứng trước chuỗi cuối, theo thứ tự chuỗi
    pie: tuple[str, ...]
    grid: str = 'E3E7EB'
    body: str = SANS


THEMES = {
    'clean': Theme('clean', 'Gọn sáng', SANS, ink='1F2328', muted='5D6670', accent='0F766E', hair='D8DDE2',
                   series=('C9D3DA', '9CC9C2', '5FA8A0'), pie=('0F766E', '5FA8A0', '9CC9C2', '1F2328', '8A949E', 'C9D3DA')),
    'academic': Theme('academic', 'Học thuật', SERIF, ink='222831', muted='636B75', accent='1F3A5F', hair='CFD5DD',
                      series=('A97C37', 'D9C49E', '8A96A6'), pie=('1F3A5F', 'A97C37', '5C7699', 'D9C49E', '8A96A6', 'CFD5DD')),
    'bold': Theme('bold', 'Đậm nét', SANS, ink='172033', muted='5E6675', accent='F0643C', hair='DDE1E7',
                  series=('C3C9D3', '6B7385', '172033'), pie=('F0643C', '172033', 'FFB59F', '6B7385', 'C3C9D3', 'FFD8CC')),
}

# Màu riêng từng phong cách, dùng trong layout.py.
GOLD, GOLD_LIGHT, ZEBRA = 'A97C37', 'D9C49E', 'F3F5F8'
CORAL_LIGHT, MIST, BOLD_META, RING = 'FFB59F', 'F2F4F7', 'B9C0CC', '2C3446'


def series_colors(theme: Theme, count: int) -> list[str]:
    if count <= 1:
        return [theme.accent]
    before = list(theme.series[:count - 1])
    while len(before) < count - 1:
        before.append(theme.series[-1])
    return [*before, theme.accent]

"""Kiểu trình bày tài liệu Peto tạo (create_document).

Chủ dự án chọn cả ba kiểu từ mẫu ngày 6/10/2026 (https://claude.ai/artifact/R79UV3ASRLWUd49j79ZvzR): Khung đôi cho đồ án
tốt nghiệp, khóa luận; Dải màu cho báo cáo môn học, đồ án nhóm; Tối giản cho tiểu luận, lời giải, tài liệu đơn giản.
Kiểu nào cũng theo cách trình bày quen dùng ở các trường Việt Nam: A4, Times New Roman 13, giãn dòng 1,5, căn đều, thụt
đầu dòng 1 cm, lề trên 2 · dưới 2 · trái 3 · phải 2 cm. Bản Word dùng Times New Roman; bản PDF dùng Tinos, cùng bề rộng
chữ với Times New Roman, nên ngắt dòng và số trang gần như trùng với Word.
"""
from __future__ import annotations

from dataclasses import dataclass

NAVY = "1F3A5F"


@dataclass(frozen=True)
class Theme:
    name: str
    # Đề mục cấp 1–4: cỡ chữ, in hoa, nghiêng; màu chung của đề mục.
    heading_sizes: tuple = (14, 13, 13, 13)
    heading_caps: tuple = (True, False, False, False)
    heading_italic: tuple = (False, False, True, True)
    heading_color: str = "000000"
    # Kẻ một đường dưới đề mục cấp 1 (Dải màu).
    heading_rule: bool = False
    # Phần tên tài liệu khi không có bìa: "center" (in đậm giữa trang), "band" (chữ màu, gạch dưới), "rule" (chữ thường,
    # kẻ mảnh), "essay" (lớn, giữa trang).
    title: str = "center"
    # Bảng: "grid" (kẻ ô đầy đủ), "band" (hàng đầu nền màu, sọc nhạt), "booktabs" (ba đường kẻ).
    table: str = "grid"
    # Khung mã: "box" (nền xám, viền), "bar" (vạch màu bên trái), "rules" (kẻ trên dưới).
    code: str = "box"
    caption_align: str = "center"
    caption_separator: str = "."
    caption_small_caps: bool = False
    caption_color: str = "000000"
    # Đầu trang: None (không có), "split" (trái: môn/loại bài, phải: tên tài liệu), "title" (tên tài liệu bên phải).
    header: str | None = None
    header_small_caps: bool = False
    # Chân trang: "number" (số trang giữa), "trang" ("Trang N" giữa), "trang-right" ("Trang N" bên phải).
    footer: str = "number"
    # Bìa: "frame" (khung đôi, căn giữa), "band" (dải màu bên trái, căn trái), "rules" (kẻ mảnh, căn giữa).
    cover: str = "frame"
    accent: str = "000000"
    toc_title: str = "MỤC LỤC"
    code_font: str = "Courier New"


THEMES = {
    "classic": Theme("classic"),
    "band": Theme("band", heading_sizes=(15.5, 13.5, 13, 13), heading_caps=(False,) * 4, heading_color=NAVY,
                  heading_rule=True, title="band", table="band", code="bar", caption_align="left",
                  caption_separator=":", caption_color=NAVY, header="split", footer="trang-right", cover="band",
                  accent=NAVY, toc_title="Mục lục", code_font="Consolas"),
    "minimal": Theme("minimal", heading_sizes=(15, 13, 13, 13), heading_caps=(False,) * 4, title="rule",
                     table="booktabs", code="rules", caption_small_caps=True, header="split", header_small_caps=True,
                     cover="rules", toc_title="Mục lục"),
    # Bài nghị luận: không bìa, tên bài lớn giữa trang, đầu trang ghi tên bài.
    "essay": Theme("essay", heading_sizes=(16, 14, 13, 13), heading_caps=(False,) * 4, title="essay", header="title",
                   footer="trang", toc_title="Mục lục"),
}
# Tài liệu tạo trước 6/10/2026 lưu kiểu "report" (giấy Letter, Arial): sửa lại thì dựng theo Khung đôi.
ALIASES = {"report": "classic"}
STYLES = ("classic", "band", "minimal", "essay")


def theme_for(style: str) -> Theme:
    return THEMES.get(ALIASES.get(style, style), THEMES["classic"])

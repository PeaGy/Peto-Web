"""Các hình đã dàn trang của một slide, tọa độ tính bằng point từ góc trên trái (slide 16:9 rộng 960, cao 540).

pptx_out.py và pdf_out.py chỉ vẽ lại các hình này, không tự tính vị trí, nên hai bản luôn cùng bố cục.
"""
from __future__ import annotations

from dataclasses import dataclass, field

W, H = 960.0, 540.0


@dataclass
class Shape:
    kind: str                    # rect, round, ellipse
    x: float
    y: float
    w: float
    h: float
    fill: str | None = None
    line: str | None = None
    line_width: float = 0.0
    radius: float = 0.0


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    color: str
    width: float = 0.75
    dash: bool = False


@dataclass
class Bullet:
    char: str
    color: str
    scale: float                 # cỡ dấu so với cỡ chữ
    indent: float                # khoảng từ mép trái tới chữ


@dataclass
class Para:
    text: str
    family: str
    size: float
    color: str
    bold: bool = False
    italic: bool = False
    align: str = 'left'          # left, right, center
    spacing: float = 0.0         # giãn chữ, point
    line: float = 0.0            # chiều cao mỗi dòng, point (cố định để hai bản giống nhau)
    after: float = 0.0           # khoảng sau đoạn
    bullet: Bullet | None = None
    lines: list[str] = field(default_factory=list)   # các dòng đã ngắt, cho bản PDF

    @property
    def height(self) -> float:
        return len(self.lines) * self.line


@dataclass
class TextBox:
    x: float
    y: float
    w: float
    h: float
    paras: list[Para]
    anchor: str = 'top'          # top, middle, bottom
    title: bool = False          # thành ô tiêu đề thật của slide trong PPTX (outline, trình đọc màn hình)
    slide_number: bool = False   # ô số trang: PPTX ghi trường số slide, tự đổi khi sắp xếp lại

    @property
    def content_height(self) -> float:
        return sum(para.height + para.after for para in self.paras) - (self.paras[-1].after if self.paras else 0)


@dataclass
class Picture:
    x: float
    y: float
    w: float
    h: float
    data: bytes
    border: str | None = None


@dataclass
class Cell:
    para: Para
    fill: str | None = None


@dataclass
class Table:
    x: float
    y: float
    widths: list[float]
    heights: list[float]
    cells: list[list[Cell]]
    pad_x: float
    pad_y: float
    header_rule: tuple[str, float] | None = None   # đường dưới hàng tiêu đề: màu, độ dày
    row_rule: tuple[str, float] | None = None      # đường dưới mỗi hàng


@dataclass
class Chart:
    x: float
    y: float
    w: float
    h: float
    kind: str                    # column, bar, line, pie
    categories: list[str]
    series: list[tuple[str, list[float]]]
    colors: list[str]
    family: str
    text: str                    # màu chữ trục, nhãn
    grid: str
    minimum: float = 0.0         # trục giá trị cố định, để PowerPoint và bản xem trước cùng thang chia
    maximum: float = 0.0
    step: float = 0.0
    labels: bool = False         # nhãn số trên từng cột (một chuỗi số liệu)


@dataclass
class Scene:
    background: str
    items: list = field(default_factory=list)
    notes: str = ''

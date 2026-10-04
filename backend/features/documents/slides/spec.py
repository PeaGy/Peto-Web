"""Đầu vào của công cụ create_presentation: lược đồ cho model và bước kiểm tra trước khi dàn trang.

Lược đồ để phẳng: mọi trường của mọi khuôn đều có mặt (strict), trường khuôn không dùng thì null. Bảng và biểu đồ là các
trường table_* và chart_* thay vì đối tượng lồng có thể null, vì không phải dịch vụ AI nào cũng nhận anyOf trong strict.
Bài thuyết trình lưu lại dạng JSON gọn (bỏ trường null) để Peto đọc lại khi được nhờ sửa ở lượt sau.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from features.documents.export import clean_text

LAYOUTS = ('cover', 'agenda', 'bullets', 'two_columns', 'image_text', 'table', 'chart')
THEMES = ('clean', 'academic', 'bold')
CHARTS = ('column', 'bar', 'line', 'pie')
MAX_SLIDES = 25
MAX_IMAGES = 8
MAX_NOTES = 1500
ITEM = 110          # ký tự tối đa mỗi ý
CELL = 60

_STRING = {'type': 'string'}
_NULL_STRING = {'type': ['string', 'null']}
_NULL_LIST = {'type': ['array', 'null'], 'items': _STRING}

SLIDE_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'layout': {'type': 'string', 'enum': list(LAYOUTS), 'description': (
            'cover: bìa (title, subtitle là dòng nhỏ phía trên tên như môn học/sự kiện, meta là người trình bày · ngày, '
            'tối đa 2 dòng). agenda: mục lục, bullets là 2–6 mục. bullets: 1–6 ý ngắn. two_columns: left_title/right_title '
            'và left_bullets/right_bullets, mỗi cột 1–5 ý (so sánh, trước/sau, ưu/nhược). image_text: image là số N của '
            '[Ảnh N] người dùng đã gửi, bullets 1–5 ý, caption chú thích ảnh. table: table_columns 2–5 cột, table_rows 1–7 '
            'hàng. chart: chart_type, chart_categories, chart_series, chart_unit.')},
        'title': {'type': 'string', 'description': 'Tiêu đề slide, ngắn (tối đa khoảng 60 ký tự).'},
        'subtitle': _NULL_STRING,
        'meta': _NULL_STRING,
        'section': {'type': ['string', 'null'], 'description': 'Tên phần ngắn, ví dụ "2 · Phân tích yêu cầu"; phong cách academic hiện nó phía trên tiêu đề. Có thể null.'},
        'bullets': {'type': ['array', 'null'], 'items': _STRING, 'description': 'Mỗi ý một câu ngắn, không có dấu đầu dòng hay Markdown.'},
        'left_title': _NULL_STRING, 'left_bullets': _NULL_LIST,
        'right_title': _NULL_STRING, 'right_bullets': _NULL_LIST,
        'image': {'type': ['integer', 'null'], 'description': 'Số N trong nhãn [Ảnh N: …] của ảnh người dùng đã gửi. Không dùng ảnh từ web.'},
        'caption': {'type': ['string', 'null'], 'description': 'Chú thích hoặc nguồn số liệu cho ảnh, bảng, biểu đồ.'},
        'table_columns': _NULL_LIST,
        'table_rows': {'type': ['array', 'null'], 'items': {'type': 'array', 'items': _STRING}},
        'chart_type': {'type': ['string', 'null'], 'enum': [*CHARTS, None]},
        'chart_categories': _NULL_LIST,
        'chart_series': {'type': ['array', 'null'], 'items': {
            'type': 'object', 'additionalProperties': False,
            'properties': {'name': _STRING, 'values': {'type': 'array', 'items': {'type': 'number'}}},
            'required': ['name', 'values']}},
        'chart_unit': _NULL_STRING,
        'notes': {'type': 'string', 'description': 'Ghi chú cho người thuyết trình: điều cần nói ở slide này, 1–3 câu.'},
    },
}
SLIDE_SCHEMA['required'] = list(SLIDE_SCHEMA['properties'])

SCHEMA = {
    'type': 'function', 'name': 'create_presentation', 'strict': True,
    'description': (
        'Tạo tệp PowerPoint PPTX thật (kèm bản PDF), lưu theo tài khoản và hiện thẻ xem trước/tải ngay trong chat. Gọi khi '
        'người dùng nhờ làm slide, bài thuyết trình, PowerPoint. Slide 16:9, mỗi slide có ghi chú cho người thuyết trình. '
        'theme: clean (Gọn sáng, mặc định), academic (Học thuật: đồ án, luận văn, báo cáo khoa học), bold (Đậm nét: hội '
        'trường, cuộc thi, giới thiệu sản phẩm); người dùng chọn phong cách thì theo người dùng. Thường 6–12 slide, mở đầu '
        'bằng cover, slide thứ hai có thể là agenda. Ý ngắn gọn, không đoạn văn dài. Bảng và biểu đồ chỉ dùng số liệu có '
        'thật từ người dùng, tệp hoặc nguồn đã dẫn; không bịa số liệu. Tiếng Việt phải có đầy đủ dấu.'),
    'parameters': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'title': {'type': 'string', 'description': 'Tên bài thuyết trình, cũng là tên tệp.'},
            'theme': {'type': 'string', 'enum': list(THEMES)},
            'slides': {'type': 'array', 'items': SLIDE_SCHEMA},
        },
        'required': ['title', 'theme', 'slides'],
    },
}


class SeriesInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(max_length=60)
    values: list[float] = Field(max_length=20)


class SlideInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    layout: Literal['cover', 'agenda', 'bullets', 'two_columns', 'image_text', 'table', 'chart']
    title: str = Field(max_length=200)
    subtitle: str | None = Field(None, max_length=300)
    meta: str | None = Field(None, max_length=300)
    section: str | None = Field(None, max_length=120)
    bullets: list[str] | None = Field(None, max_length=12)
    left_title: str | None = Field(None, max_length=120)
    left_bullets: list[str] | None = Field(None, max_length=12)
    right_title: str | None = Field(None, max_length=120)
    right_bullets: list[str] | None = Field(None, max_length=12)
    image: int | None = None
    caption: str | None = Field(None, max_length=300)
    table_columns: list[str] | None = Field(None, max_length=12)
    table_rows: list[list[str]] | None = Field(None, max_length=20)
    chart_type: Literal['column', 'bar', 'line', 'pie'] | None = None
    chart_categories: list[str] | None = Field(None, max_length=20)
    chart_series: list[SeriesInput] | None = Field(None, max_length=8)
    chart_unit: str | None = Field(None, max_length=40)
    notes: str = Field('', max_length=4000)


class DeckInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    theme: Literal['clean', 'academic', 'bold']
    slides: list[SlideInput] = Field(min_length=1, max_length=40)


@dataclass
class Series:
    name: str
    values: list[float]


@dataclass
class Slide:
    layout: str
    title: str
    notes: str = ''
    subtitle: str = ''
    meta: str = ''
    section: str = ''
    bullets: list[str] = field(default_factory=list)
    left_title: str = ''
    left_bullets: list[str] = field(default_factory=list)
    right_title: str = ''
    right_bullets: list[str] = field(default_factory=list)
    image: int = 0
    caption: str = ''
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    chart_type: str = ''
    categories: list[str] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    unit: str = ''


@dataclass
class Deck:
    title: str
    theme: str
    slides: list[Slide]

    def to_json(self) -> str:
        """JSON gọn để lưu và để Peto đọc lại: bỏ trường rỗng của khuôn không dùng."""
        def compact(value):
            if isinstance(value, dict):
                return {key: compact(item) for key, item in value.items() if item not in ('', 0, [], None)}
            if isinstance(value, list):
                return [compact(item) for item in value]
            return value
        return json.dumps(compact(asdict(self)), ensure_ascii=False)


def _line(value: str | None) -> str:
    text = clean_text(value or '')
    text = re.sub(r'\*\*|__|`', '', text)
    return ' '.join(text.split())


def _item(value: str) -> str:
    return re.sub(r'^(?:[-*•–·]|\d+[.)])\s+', '', _line(value))


def _items(values: list[str] | None) -> list[str]:
    return [item for item in (_item(value) for value in values or []) if item]


def _number(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError('số không hợp lệ')
    return float(value)


def _check_length(where: str, text: str, limit: int, what: str):
    if len(text) > limit:
        raise ValueError(f'{where}: {what} dài quá {limit} ký tự. Rút gọn hoặc tách thành hai slide.')


def normalize(spec: DeckInput) -> Deck:
    """Làm sạch chữ và kiểm tra từng khuôn. Lỗi nói rõ slide nào, sai gì, để model sửa rồi gọi lại."""
    if len(spec.slides) > MAX_SLIDES:
        raise ValueError(f'Bài thuyết trình tối đa {MAX_SLIDES} slide. Gộp hoặc bỏ bớt slide rồi gọi lại.')
    slides: list[Slide] = []
    images = 0
    for index, raw in enumerate(spec.slides, start=1):
        where = f'Slide {index} ({raw.layout})'
        slide = Slide(layout=raw.layout, title=_line(raw.title), notes=clean_text(raw.notes or ''),
                      section=_line(raw.section), caption=_line(raw.caption))
        if not slide.title:
            raise ValueError(f'{where}: thiếu tiêu đề.')
        _check_length(where, slide.title, 100, 'tiêu đề')
        _check_length(where, slide.section, 60, 'tên phần')
        _check_length(where, slide.caption, 160, 'chú thích')
        if len(slide.notes) > MAX_NOTES:
            raise ValueError(f'{where}: ghi chú thuyết trình dài quá {MAX_NOTES} ký tự.')
        bullets = _items(raw.bullets)
        for item in bullets:
            _check_length(where, item, ITEM, 'một ý')
        if raw.layout == 'cover':
            slide.subtitle = _line(raw.subtitle)
            slide.meta = '\n'.join(_line(part) for part in clean_text(raw.meta or '').split('\n') if _line(part))
            _check_length(where, slide.subtitle, 100, 'dòng phụ')
            _check_length(where, slide.meta, 140, 'dòng thông tin')
            if slide.meta.count('\n') > 1:
                raise ValueError(f'{where}: meta tối đa 2 dòng.')
        elif raw.layout in ('agenda', 'bullets', 'image_text'):
            low, high = {'agenda': (2, 6), 'bullets': (1, 6), 'image_text': (1, 5)}[raw.layout]
            if not low <= len(bullets) <= high:
                raise ValueError(f'{where}: bullets cần {low}–{high} ý, đang có {len(bullets)}.')
            slide.bullets = bullets
            if raw.layout == 'image_text':
                if not raw.image or raw.image < 1:
                    raise ValueError(f'{where}: image phải là số N của [Ảnh N] người dùng đã gửi. Không có ảnh thì dùng khuôn bullets.')
                slide.image = raw.image
                images += 1
        elif raw.layout == 'two_columns':
            slide.left_title, slide.right_title = _line(raw.left_title), _line(raw.right_title)
            slide.left_bullets, slide.right_bullets = _items(raw.left_bullets), _items(raw.right_bullets)
            for side, items in (('trái', slide.left_bullets), ('phải', slide.right_bullets)):
                if not 1 <= len(items) <= 5:
                    raise ValueError(f'{where}: cột {side} cần 1–5 ý.')
                for item in items:
                    _check_length(where, item, 90, 'một ý trong cột')
            if not slide.left_title or not slide.right_title:
                raise ValueError(f'{where}: cần left_title và right_title.')
            _check_length(where, slide.left_title, 40, 'tên cột')
            _check_length(where, slide.right_title, 40, 'tên cột')
        elif raw.layout == 'table':
            columns = [_line(value) for value in raw.table_columns or []]
            rows = [[_line(value) for value in row] for row in raw.table_rows or []]
            if not 2 <= len(columns) <= 5 or not all(columns):
                raise ValueError(f'{where}: table_columns cần 2–5 tên cột.')
            if not 1 <= len(rows) <= 7:
                raise ValueError(f'{where}: table_rows cần 1–7 hàng. Bảng dài thì chia sang slide khác.')
            for row in rows:
                if len(row) != len(columns):
                    raise ValueError(f'{where}: mỗi hàng phải có đúng {len(columns)} ô như số cột.')
                for cell in row:
                    _check_length(where, cell, CELL, 'một ô')
            for column in columns:
                _check_length(where, column, 40, 'tên cột')
            slide.columns, slide.rows = columns, rows
        elif raw.layout == 'chart':
            categories = [_line(value) for value in raw.chart_categories or []]
            series = [Series(_line(item.name), [_number(value) for value in item.values]) for item in raw.chart_series or []]
            if not raw.chart_type:
                raise ValueError(f'{where}: thiếu chart_type (column, bar, line, pie).')
            if not 2 <= len(categories) <= 12 or not all(categories):
                raise ValueError(f'{where}: chart_categories cần 2–12 nhãn.')
            if not 1 <= len(series) <= 4:
                raise ValueError(f'{where}: chart_series cần 1–4 chuỗi số liệu.')
            for item in series:
                if not item.name:
                    raise ValueError(f'{where}: mỗi chuỗi số liệu cần tên.')
                if len(item.values) != len(categories):
                    raise ValueError(f'{where}: chuỗi "{item.name}" phải có đúng {len(categories)} số, mỗi nhãn một số.')
            if raw.chart_type == 'pie':
                if len(series) != 1:
                    raise ValueError(f'{where}: biểu đồ tròn chỉ có một chuỗi số liệu.')
                if any(value < 0 for value in series[0].values) or sum(series[0].values) <= 0:
                    raise ValueError(f'{where}: biểu đồ tròn cần các số không âm, tổng lớn hơn 0.')
                if len(categories) > 6:
                    raise ValueError(f'{where}: biểu đồ tròn tối đa 6 phần; nhiều hơn thì dùng biểu đồ cột.')
            if raw.chart_type in ('column', 'bar') and any(value < 0 for item in series for value in item.values):
                raise ValueError(f'{where}: biểu đồ cột chưa hỗ trợ số âm; dùng bảng.')
            for label in categories:
                _check_length(where, label, 30, 'nhãn')
            slide.chart_type, slide.categories, slide.series = raw.chart_type, categories, series
            slide.unit = _line(raw.chart_unit)[:20]
        slides.append(slide)
    if images > MAX_IMAGES:
        raise ValueError(f'Tối đa {MAX_IMAGES} slide có ảnh mỗi bài thuyết trình.')
    title = _line(spec.title)
    if not title:
        raise ValueError('Tên bài thuyết trình trống.')
    return Deck(title=title[:120], theme=spec.theme, slides=slides)


def load(content: str) -> Deck:
    """Đọc lại JSON đã lưu (Deck.to_json)."""
    data = json.loads(content)
    slides = []
    for item in data.get('slides', []):
        item = dict(item)
        item['series'] = [Series(**series) for series in item.get('series', [])]
        slides.append(Slide(**item))
    return Deck(title=data['title'], theme=data['theme'], slides=slides)


def image_numbers(deck: Deck) -> set[int]:
    return {slide.image for slide in deck.slides if slide.layout == 'image_text' and slide.image}


def plain_text(deck: Deck) -> str:
    """Toàn bộ chữ của bài, để kiểm tra tiếng Việt bị gửi không dấu."""
    parts = [deck.title]
    for slide in deck.slides:
        parts += [slide.title, slide.subtitle, slide.meta, slide.section, slide.left_title, slide.right_title, slide.caption,
                  *slide.bullets, *slide.left_bullets, *slide.right_bullets, *slide.columns,
                  *(cell for row in slide.rows for cell in row), *slide.categories, slide.notes]
    return '\n'.join(part for part in parts if part)

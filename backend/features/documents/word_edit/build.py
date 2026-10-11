"""Dựng phần Peto chèn vào tệp Word (đoạn, công thức Word thật, bảng) dưới dạng Theo dõi thay đổi của Word: mỗi phần
mang dấu w:ins tác giả "Peto", người dùng xem rồi Accept hay Reject trong Word (chủ web chọn ngày 12/10/2026).

Nội dung đến dưới dạng Markdown như create_document, cùng bộ phân tích (export.parse_blocks) và cùng bộ viết công thức
(math/omml_out), nên công thức chèn vào sửa được trong Word. Danh sách được viết số và dấu đầu dòng bằng chữ, không thêm
định nghĩa đánh số vào numbering.xml: tệp chỉ đổi đúng phần nội dung.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from lxml import etree

from features.documents.export import Block, Run, column_widths
from features.documents.math import latex as math_latex, omml_out
from features.documents.word_reader import format_number

from .package import W_NS

M_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
AUTHOR = 'Peto'
_NAMESPACES = f'xmlns:w="{W_NS}" xmlns:m="{M_NS}"'
# Các thuộc tính chữ lấy theo đoạn bên cạnh, để phần chèn cùng phông và cỡ chữ với bài. Không lấy đậm, nghiêng, màu.
_INHERITED = ('rFonts', 'sz', 'szCs', 'lang')
# Thứ tự con của w:rPr theo lược đồ OOXML; Word coi thứ tự sai là tệp hỏng.
_RPR_ORDER = ('rStyle', 'rFonts', 'b', 'bCs', 'i', 'iCs', 'strike', 'color', 'sz', 'szCs', 'lang')
CODE_FONT = 'Courier New'
DEFAULT_TEXT_WIDTH = 9026  # A4 trừ lề 2,54 cm, đơn vị twip


def w(name: str) -> str:
    return f'{{{W_NS}}}{name}'


class Revisions:
    """Mã (w:id) và dấu thời gian cho các dấu sửa của một lần chạy; mã nối tiếp mã lớn nhất đã có trong tệp."""

    def __init__(self, root, date: str):
        largest = 0
        for element in root.iter():
            value = element.get(w('id')) if isinstance(element.tag, str) else None
            if value and value.lstrip('-').isdigit():
                largest = max(largest, int(value))
        self.next = largest + 1
        self.date = date

    def attrs(self) -> str:
        number, self.next = self.next, self.next + 1
        return f'w:id="{number}" w:author="{AUTHOR}" w:date="{self.date}"'

    def mark(self, name: str):
        """Phần tử w:ins hay w:del rỗng (dấu cho dấu xuống đoạn, hàng bảng) hoặc để bọc các run."""
        return fragment(f'<w:{name} {self.attrs()}/>')[0]


def fragment(xml: str) -> list:
    """Chuỗi XML có tiền tố w:, m: → các phần tử lxml để gắn vào tài liệu."""
    root = etree.fromstring(f'<root {_NAMESPACES}>{xml}</root>')
    return list(root)


def base_properties(paragraph) -> list:
    """Phông, cỡ chữ, ngôn ngữ của chữ đầu tiên trong đoạn, để phần chèn trông như bài. Đoạn không ghi gì riêng (theo
    kiểu mặc định) thì lấy của các đoạn ngay trước, rồi ngay sau nó."""
    if paragraph is None:
        return []
    nearby = [paragraph]
    for step in ('getprevious', 'getnext'):
        node = getattr(paragraph, step)()
        while node is not None and len(nearby) < 12:
            if etree.QName(node).localname == 'p':
                nearby.append(node)
            node = getattr(node, step)()
    for candidate in nearby:
        found = _own_properties(candidate)
        if found:
            return found
    return []


def _own_properties(paragraph) -> list:
    for run in paragraph.iter(w('r')):
        if run.find(w('t')) is not None and (run.findtext(w('t')) or '').strip():
            properties = run.find(w('rPr'))
            if properties is not None:
                return [child for child in properties if etree.QName(child).localname in _INHERITED]
            return []
    mark = paragraph.find(f"{w('pPr')}/{w('rPr')}")
    return [] if mark is None else [child for child in mark if etree.QName(child).localname in _INHERITED]


def text_font(base: list) -> str:
    for child in base:
        if etree.QName(child).localname == 'rFonts':
            return child.get(w('ascii')) or child.get(w('hAnsi')) or 'Times New Roman'
    return 'Times New Roman'


def text_width(root) -> int:
    """Bề rộng vùng chữ (twip) theo khổ giấy và lề của phần cuối tài liệu."""
    section = root.find(f"{w('body')}/{w('sectPr')}")
    try:
        size, margins = section.find(w('pgSz')), section.find(w('pgMar'))
        width = int(size.get(w('w'))) - int(margins.get(w('left'))) - int(margins.get(w('right')))
        return width if 2000 <= width <= 30000 else DEFAULT_TEXT_WIDTH
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_TEXT_WIDTH


class Writer:
    """Viết các khối Markdown thành XML Word, mỗi phần mang dấu chèn của Peto."""

    def __init__(self, revisions: Revisions, base: list, width: int):
        self.revisions = revisions
        self.base = ''.join(etree.tostring(child, encoding='unicode') for child in base)
        self.font = text_font(base)
        self.width = width

    def _rpr(self, run: Run, extra: str = '') -> str:
        parts = {etree.QName(child).localname: etree.tostring(child, encoding='unicode')
                 for child in fragment(self.base)} if self.base else {}
        if run.code:
            parts['rFonts'] = f'<w:rFonts w:ascii="{CODE_FONT}" w:hAnsi="{CODE_FONT}" w:cs="{CODE_FONT}"/>'
        if run.bold:
            parts['b'], parts['bCs'] = '<w:b/>', '<w:bCs/>'
        if run.italic:
            parts['i'], parts['iCs'] = '<w:i/>', '<w:iCs/>'
        if run.strike:
            parts['strike'] = '<w:strike/>'
        for piece in fragment(extra) if extra else []:
            parts[etree.QName(piece).localname] = etree.tostring(piece, encoding='unicode')
        body = ''.join(parts[name] for name in _RPR_ORDER if name in parts)
        return f'<w:rPr>{body}</w:rPr>' if body else ''

    def _clean(self, xml: str) -> str:
        # etree.tostring lặp lại khai báo không gian tên trên từng phần tử con; bỏ đi để chuỗi gọn khi ghép.
        return xml.replace(f' xmlns:w="{W_NS}"', '').replace(f' xmlns:m="{M_NS}"', '')

    def runs(self, runs: list[Run], extra: str = '') -> str:
        """Các run trong một w:ins; công thức trong dòng thành m:oMath."""
        out = []
        for run in runs:
            if run.math:
                formula = math_latex.parse(run.text, False)
                out.append(omml_out.to_omml(formula, self.font))
                continue
            props = self._clean(self._rpr(run, extra))
            pieces = run.text.replace('\r', '').split('\n')
            for index, piece in enumerate(pieces):
                if index:
                    out.append(f'<w:r>{props}<w:br/></w:r>')
                for part_index, part in enumerate(piece.split('\t')):
                    if part_index:
                        out.append(f'<w:r>{props}<w:tab/></w:r>')
                    if part:
                        out.append(f'<w:r>{props}<w:t xml:space="preserve">{escape(part)}</w:t></w:r>')
        return ''.join(out)

    def paragraph(self, inner: str, properties: str = '') -> str:
        """Một đoạn chèn: dấu xuống đoạn mang w:ins, nội dung bọc trong w:ins."""
        mark = f'<w:rPr><w:ins {self.revisions.attrs()}/></w:rPr>'
        content = f'<w:ins {self.revisions.attrs()}>{inner}</w:ins>' if inner else ''
        return f'<w:p><w:pPr>{properties}{mark}</w:pPr>{content}</w:p>'

    def block(self, block: Block) -> list[str]:
        if block.kind == 'paragraph':
            label, indent = '', ''
            if block.list_info is not None:
                depth = block.list_info.depth
                left = 360 * (depth + 1)
                indent = f'<w:ind w:left="{left}" w:hanging="360"/>'
                if block.number is not None:
                    label = (f'{format_number(block.number, block.list_info.style)}. ' if block.list_info.ordered
                             else f'{block.list_info.marker} ')
                else:
                    # Đoạn sau của cùng một mục: thẳng hàng với chữ của mục, không có số.
                    indent = f'<w:ind w:left="{left}"/>'
            runs = ([Run(label)] if label else []) + block.runs
            return [self.paragraph(self.runs(runs), indent)]
        if block.kind == 'heading':
            return [self.paragraph(self.runs([Run(run.text, True, run.italic, run.strike, run.code, run.math)
                                              for run in block.runs]), '<w:keepNext/>')]
        if block.kind == 'quote':
            return [self.paragraph(self.runs([Run(run.text, run.bold, True, run.strike, run.code, run.math)
                                              for run in block.runs]), '<w:ind w:left="567"/>')]
        if block.kind == 'math':
            formula = math_latex.parse(block.math, True)
            return [self.paragraph(omml_out.to_omml(formula, self.font))]
        if block.kind == 'code':
            return [self.paragraph(self.runs(block.runs), '<w:spacing w:before="0" w:after="0"/>')]
        if block.kind == 'rule':
            return []
        if block.kind == 'table':
            return [self.table(block.rows)]
        raise ValueError('Phần chèn vào tệp Word chưa nhận ảnh, khung ảnh hay mục lục; chỉ chữ, công thức, danh sách và bảng.')

    def table(self, rows: list[list[list[Run]]]) -> str:
        columns = max(len(row) for row in rows)
        rows = [row + [[] for _ in range(columns - len(row))] for row in rows]
        widths = [max(int(points * 20), 400) for points in column_widths(rows, self.width / 20)]
        border = ''.join(f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
                         for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
        grid = ''.join(f'<w:gridCol w:w="{width}"/>' for width in widths)
        out = [f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:jc w:val="center"/><w:tblBorders>{border}'
               f'</w:tblBorders><w:tblLayout w:type="autofit"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
        for index, row in enumerate(rows):
            header = '<w:tblHeader/>' if index == 0 and len(rows) > 1 else ''
            out.append(f'<w:tr><w:trPr>{header}<w:ins {self.revisions.attrs()}/></w:trPr>')
            for column, cell in enumerate(row):
                runs = [Run(run.text, run.bold or index == 0, run.italic, run.strike, run.code, run.math) for run in cell]
                short = sum(len(run.text) for run in cell) <= 12
                align = '<w:jc w:val="center"/>' if short else ''
                spacing = '<w:spacing w:before="0" w:after="0"/>'
                out.append(f'<w:tc><w:tcPr><w:tcW w:w="{widths[column]}" w:type="dxa"/></w:tcPr>'
                           f'{self.paragraph(self.runs(runs), spacing + align)}</w:tc>')
            out.append('</w:tr>')
        out.append('</w:tbl>')
        return ''.join(out)

    def empty_paragraph(self) -> str:
        return self.paragraph('')

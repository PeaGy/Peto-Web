"""Dữ liệu xem trước tệp Word đã sửa cho trang: từng đoạn và bảng theo thứ tự, mỗi phần chữ ghi là chèn, xóa hay giữ
nguyên, công thức ở dạng LaTeX (trang vẽ bằng KaTeX như trong chat). Không phải bản dàn trang của Word: máy chủ không có
Word, nên trang chỉ cho thấy nội dung và chỗ sửa, còn bố cục thật xem bằng Word sau khi tải.
"""
from __future__ import annotations

from lxml import etree

from features.documents import word_reader
from features.documents.math import omml_in

from .build import AUTHOR

MAX_BLOCKS = 2000
MAX_CHARS = 300_000
_HEADING = ('heading', 'title', 'tieude', 'tiêuđề', 'subtitle')


def _name(element) -> tuple[str, str]:
    return omml_in.local(element)


W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _w(name: str) -> str:
    return f'{{{W}}}{name}'


def _flag(properties, name: str) -> bool:
    """w:b, w:i… bật khi không có w:val hoặc w:val khác false/0/off."""
    element = None if properties is None else properties.find(_w(name))
    return element is not None and element.get(_w('val'), 'true') not in {'false', '0', 'off'}


class Walker:
    def __init__(self, numbering_root, styles_root):
        numbering = word_reader.Numbering(numbering_root, styles_root) if numbering_root is not None else None
        self.numbering = numbering
        self.chars = 0
        self.counts = {'ins': 0, 'del': 0}

    def _state(self, element, state: str | None) -> str | None:
        name = _name(element)
        if name[0] in word_reader.WORD_NAMESPACES and name[1] in {'ins', 'moveTo'}:
            return 'ins'
        if name[0] in word_reader.WORD_NAMESPACES and name[1] in {'del', 'moveFrom'}:
            return 'del'
        return state

    def _push(self, parts: list, part: dict) -> None:
        text = part.get('text')
        if text is not None:
            self.chars += len(text)
            last = parts[-1] if parts else None
            if (last and 'text' in last and last.get('state') == part.get('state') and last.get('b') == part.get('b')
                    and last.get('i') == part.get('i')):
                last['text'] += text
                return
        if part.get('state'):
            self.counts[part['state']] += 1
        parts.append(part)

    def parts(self, node, state: str | None = None, out: list | None = None) -> list:
        out = [] if out is None else out
        for child in node:
            namespace, name = _name(child)
            if namespace in omml_in.MATH_NAMESPACES:
                if name == 'oMathPara':
                    for formula in omml_in.math_paragraph(child):
                        self._push(out, {'math': formula, 'display': True, 'state': state})
                elif name == 'oMath':
                    formula = omml_in.omml_to_latex(child)
                    if formula:
                        self._push(out, {'math': formula, 'display': False, 'state': state})
                continue
            if namespace not in word_reader.WORD_NAMESPACES:
                if name in {'drawing', 'pict'} or (namespace and name == 'pic'):
                    self._push(out, {'image': True, 'state': state})
                    continue
                self.parts(child, state, out)
                continue
            if name in {'pPr', 'rPr', 'instrText', 'delInstrText', 'fldChar', 'commentReference'}:
                continue
            if name == 'r':
                properties = child.find(_w('rPr'))
                bold, italic = _flag(properties, 'b'), _flag(properties, 'i')
                for piece in child:
                    piece_name = _name(piece)[1]
                    text = None
                    if piece_name in {'t', 'delText'}:
                        text = piece.text or ''
                    elif piece_name == 'tab':
                        text = '\t'
                    elif piece_name in {'br', 'cr'}:
                        text = '\n'
                    elif piece_name in {'drawing', 'pict', 'object'}:
                        self._push(out, {'image': True, 'state': state})
                    if text:
                        part = {'text': text, 'state': state}
                        if bold:
                            part['b'] = True
                        if italic:
                            part['i'] = True
                        self._push(out, part)
                continue
            if name in {'drawing', 'pict', 'object'}:
                self._push(out, {'image': True, 'state': state})
                continue
            self.parts(child, self._state(child, state), out)
        return out

    def paragraph(self, element) -> dict:
        label = self.numbering.label(element) if self.numbering else ''
        properties = element.find(_w('pPr'))
        mark = None if properties is None else properties.find(_w('rPr'))
        state = None
        if mark is not None:
            if mark.find(_w('ins')) is not None:
                state = 'ins'
            elif mark.find(_w('del')) is not None:
                state = 'del'
        style = (properties.find(_w('pStyle')).get(_w('val'), '') if properties is not None
                 and properties.find(_w('pStyle')) is not None else '').casefold()
        align = properties.find(_w('jc')).get(_w('val'), '') if properties is not None and properties.find(_w('jc')) is not None else ''
        block: dict = {'type': 'p', 'parts': self.parts(element)}
        if label:
            block['label'] = label
        if state:
            block['state'] = state
        if any(word in style for word in _HEADING):
            block['heading'] = True
        if align in {'center', 'right'}:
            block['align'] = align
        return block

    def table(self, element) -> dict:
        rows = []
        for row in word_reader._rows(element):
            mark = row.find(f"{_w('trPr')}/{_w('ins')}")
            gone = row.find(f"{_w('trPr')}/{_w('del')}")
            cells = []
            for cell in row:
                if _name(cell)[1] != 'tc':
                    continue
                span = cell.find(f"{_w('tcPr')}/{_w('gridSpan')}")
                parts: list = []
                for block in word_reader._blocks(cell):
                    if _name(block)[1] == 'p':
                        paragraph = self.paragraph(block)
                        if parts and paragraph['parts']:
                            self._push(parts, {'text': '\n', 'state': None})
                        for part in paragraph['parts']:
                            self._push(parts, part)
                    else:
                        self._push(parts, {'text': '[bảng lồng]', 'state': None})
                item: dict = {'parts': parts}
                if span is not None and (span.get(_w('val')) or '').isdigit() and int(span.get(_w('val'))) > 1:
                    item['span'] = int(span.get(_w('val')))
                cells.append(item)
            entry: dict = {'cells': cells}
            if mark is not None:
                entry['state'] = 'ins'
            elif gone is not None:
                entry['state'] = 'del'
            rows.append(entry)
        return {'type': 'table', 'rows': rows}


def build(root, numbering_root, styles_root) -> dict:
    """{'blocks': [...], 'counts': {'ins', 'del'}, 'truncated'}; số Đoạn/Bảng khớp bản Peto đọc."""
    body = word_reader.body_of(root)
    # Khóa là chính phần tử (giữ nó sống), không phải id(): lxml tạo lại đối tượng Python và id có thể trùng.
    numbers = {element: (kind, number) for kind, number, element, _ in
               word_reader.numbered_blocks(body, word_reader.Body(
                   word_reader.Numbering(numbering_root, styles_root) if numbering_root is not None else None))}
    walker = Walker(numbering_root, styles_root)
    blocks, truncated = [], False
    for element in word_reader._blocks(body):
        if len(blocks) >= MAX_BLOCKS or walker.chars > MAX_CHARS:
            truncated = True
            break
        kind = _name(element)[1]
        block = walker.paragraph(element) if kind == 'p' else walker.table(element)
        if kind == 'p' and not block['parts'] and not block.get('state'):
            continue
        number = numbers.get(element)
        if number:
            block['number'] = number[1]
        revisions = sorted({int(mark.get(_w('id'))) for mark in element.iter(_w('ins'), _w('del'))
                            if (mark.get(_w('id')) or '').isdigit()})
        if revisions:
            block['revs'] = revisions
        blocks.append(block)
    return {'blocks': blocks, 'counts': walker.counts, 'truncated': truncated, 'author': AUTHOR}

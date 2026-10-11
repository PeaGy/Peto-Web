"""Công cụ edit_document: sửa thẳng tệp Word người dùng gửi, ghi mọi thay đổi bằng Theo dõi thay đổi của Word.

Chỗ sửa gọi theo đúng số Peto đã đọc (``[Đoạn N]``, ``[Bảng N]`` của word_reader). Mọi chỗ trong một lần gọi tính theo
số của tệp trước lần gọi đó, nên Peto chèn lời giải dưới nhiều câu một lượt mà không phải tự cộng số. Cả lần gọi là một
khối: có lỗi thì không ghi gì, và mọi lỗi được báo cùng lúc (như edit_spreadsheet) để Peto sửa hết trong một lần.

Phần Peto từng chèn (dấu chèn tác giả "Peto") mà bị thay hay xóa thì được bỏ hẳn thay vì đánh dấu xóa, như Word làm khi
người viết xóa chính phần mình vừa chèn: sửa lại lời giải của Peto không để lại hai lớp dấu.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from lxml import etree
from pydantic import BaseModel, ConfigDict, Field

from features.documents.export import parse_blocks
from features.documents.math.omml_in import MATH_NAMESPACES
from features.documents import word_reader

from .build import AUTHOR, Revisions, Writer, base_properties, fragment, text_width, w
from .package import EditError, Package
from . import preview as word_preview

MAX_CHANGES = 30
MAX_PROBLEMS = 8
MAX_CONTENT = 20_000
MAX_TOTAL = 80_000

SCHEMA = {
    'type': 'function', 'name': 'edit_document', 'strict': True,
    'description': (
        'Sửa thẳng tệp Word (.docx) người dùng gửi trong hội thoại (hoặc bản Peto đã sửa): chèn lời giải dưới từng câu, '
        'điền bảng, thay hay xóa một đoạn. Mọi thay đổi ghi bằng Theo dõi thay đổi của Word, tác giả Peto: người dùng '
        'xem rồi Accept hay Reject trong Word. Định dạng, hình, đầu trang và phần không sửa giữ nguyên. Chỉ chỗ sửa bằng số '
        'đã đọc: "Đoạn N" hoặc "Bảng N"; mọi số trong một lần gọi tính theo tệp trước lần gọi đó. Cả lần gọi là một khối: '
        'có lỗi thì không ghi gì.'),
    'parameters': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'file': {'type': 'string', 'description': 'Tên tệp Word đúng như trong hội thoại.'},
            'changes': {
                'type': 'array', 'minItems': 1, 'maxItems': MAX_CHANGES,
                'items': {
                    'type': 'object', 'additionalProperties': False,
                    'properties': {
                        'action': {'type': 'string', 'enum': ['insert_after', 'replace', 'delete', 'fill_cell'],
                                   'description': (
                                       'insert_after: chèn content (Markdown) ngay sau đoạn hay bảng target, ví dụ lời '
                                       'giải dưới câu hỏi; nhiều lần chèn sau cùng một chỗ giữ đúng thứ tự gửi. replace: '
                                       'thay chữ của một đoạn bằng content (một đoạn). delete: xóa một đoạn hay bảng. '
                                       'fill_cell: điền content (một dòng chữ, có thể có công thức) vào ô row, column của '
                                       'bảng target, thay chữ đang có trong ô.')},
                        'target': {'type': 'string', 'description': '"Đoạn N" hoặc "Bảng N", đúng số đã đọc.'},
                        'content': {'type': ['string', 'null'], 'description': (
                            'Markdown như create_document: đoạn văn, **đậm**, *nghiêng*, danh sách, bảng Markdown (hàng '
                            'đầu là tiêu đề), công thức $...$ trong dòng và $$...$$ dòng riêng (thành công thức Word thật, '
                            'sửa được). Không có ảnh hay mục lục. Tiếng Việt đầy đủ dấu. null khi delete.')},
                        'row': {'type': ['integer', 'null'], 'description': 'fill_cell: hàng, đếm từ 1 kể cả hàng tiêu đề.'},
                        'column': {'type': ['integer', 'null'], 'description': 'fill_cell: cột, đếm từ 1.'},
                    },
                    'required': ['action', 'target', 'content', 'row', 'column'],
                },
            },
        },
        'required': ['file', 'changes'],
    },
}


class Change(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['insert_after', 'replace', 'delete', 'fill_cell']
    target: str = Field(max_length=40)
    content: str | None = Field(default=None, max_length=MAX_CONTENT)
    row: int | None = None
    column: int | None = None


class EditInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file: str = Field(min_length=1, max_length=255)
    changes: list[Change] = Field(min_length=1, max_length=MAX_CHANGES)


_TARGET = re.compile(r'^\[?\s*(doan|bang)\s*(\d{1,5})\s*\]?$')
_VERBS = {'insert_after': 'Chèn sau', 'replace': 'Thay', 'delete': 'Xóa', 'fill_cell': 'Điền'}


def _fold(text: str) -> str:
    text = unicodedata.normalize('NFD', text).replace('đ', 'd').replace('Đ', 'D')
    return ''.join(char for char in text if not unicodedata.combining(char)).casefold().strip()


def parse_target(target: str) -> tuple[str, int] | None:
    match = _TARGET.match(_fold(target))
    if not match:
        return None
    return ('p' if match.group(1) == 'doan' else 'tbl'), int(match.group(2))


def _label(kind: str, number: int) -> str:
    return f'Đoạn {number}' if kind == 'p' else f'Bảng {number}'


def _peto(element) -> bool:
    return element.get(w('author')) == AUTHOR


def _mark_holder(element) -> bool:
    """w:ins / w:del đánh dấu dấu xuống đoạn (trong w:rPr) hay hàng bảng (trong w:trPr), không bọc nội dung."""
    parent = element.getparent()
    return parent is not None and etree.QName(parent).localname in {'rPr', 'trPr'}


def _inside(element, container, names: set[str]) -> bool:
    node = element.getparent()
    while node is not None and node is not container:
        if etree.QName(node).localname in names:
            return True
        node = node.getparent()
    return False


def locked(container) -> str:
    """Phần trong đoạn/bảng mà Peto không xóa hay thay được bằng dấu sửa an toàn; rỗng nếu không có. Phần Peto tự chèn
    trước đó thì không tính: nó được bỏ hẳn."""
    for element in container.iter():
        if not isinstance(element.tag, str):
            continue
        if _peto_ancestor(element, container):
            continue
        name = etree.QName(element)
        if name.namespace in MATH_NAMESPACES and name.localname in {'oMath', 'oMathPara'}:
            return 'công thức Word'
        if name.localname in {'drawing', 'pict', 'object'}:
            return 'hình hoặc đối tượng nhúng'
        if name.localname in {'fldChar', 'fldSimple', 'instrText'}:
            return 'trường tự động (mục lục, số trang, liên kết chéo…)'
        if name.localname in {'footnoteReference', 'endnoteReference'}:
            return 'chú thích cuối trang'
        if name.localname == 'txbxContent':
            return 'hộp văn bản'
        if name.localname == 'sectPr':
            return 'dấu ngắt phần (section break)'
    return ''


def _peto_ancestor(element, container) -> bool:
    node = element.getparent()
    while node is not None and node is not container:
        if etree.QName(node).localname == 'ins' and _peto(node) and not _mark_holder(node):
            return True
        node = node.getparent()
    return False


class Editor:
    def __init__(self, root, date: str):
        self.root = root
        self.revisions = Revisions(root, date)
        self.width = text_width(root)

    def writer(self, near) -> Writer:
        return Writer(self.revisions, base_properties(near), self.width)

    # --- rút lại nội dung có sẵn
    def retract(self, container) -> None:
        """Đánh dấu xóa mọi chữ trong ``container``; phần Peto đã chèn thì bỏ hẳn."""
        for ins in [item for item in container.iter(w('ins')) if _peto(item) and not _mark_holder(item)]:
            if ins.getparent() is not None:
                ins.getparent().remove(ins)
        for run in list(container.iter(w('r'))):
            if run.getparent() is None or _inside(run, container, {'del'}):
                continue
            if not any(etree.QName(child).localname in {'t', 'tab', 'br', 'cr', 'sym', 'noBreakHyphen'} for child in run):
                continue
            parent = run.getparent()
            wrapper = self.revisions.mark('del')
            parent.insert(parent.index(run), wrapper)
            wrapper.append(run)
            for text in run.iter(w('t')):
                text.tag = w('delText')

    @staticmethod
    def _paragraph_mark(paragraph):
        properties = paragraph.find(w('pPr'))
        if properties is None:
            properties = etree.Element(w('pPr'))
            paragraph.insert(0, properties)
        mark = properties.find(w('rPr'))
        if mark is None:
            mark = etree.Element(w('rPr'))
            # w:rPr đứng sau mọi thuộc tính đoạn khác, chỉ trước w:sectPr và w:pPrChange.
            tail = next((child for child in properties if etree.QName(child).localname in {'sectPr', 'pPrChange'}), None)
            if tail is None:
                properties.append(mark)
            else:
                tail.addprevious(mark)
        return mark

    @staticmethod
    def own_paragraph(paragraph) -> bool:
        """Cả đoạn do Peto chèn (dấu xuống đoạn và mọi nội dung): xóa thì bỏ hẳn."""
        mark = paragraph.find(f"{w('pPr')}/{w('rPr')}/{w('ins')}")
        if mark is None or not _peto(mark):
            return False
        return all(etree.QName(child).localname in {'pPr', 'bookmarkStart', 'bookmarkEnd', 'proofErr'}
                   or (etree.QName(child).localname == 'ins' and _peto(child)) for child in paragraph)

    def delete_paragraph(self, paragraph) -> None:
        if self.own_paragraph(paragraph):
            paragraph.getparent().remove(paragraph)
            return
        self.retract(paragraph)
        mark = self._paragraph_mark(paragraph)
        if mark.find(w('del')) is None:
            mark.insert(0, self.revisions.mark('del'))

    def delete_table(self, table) -> None:
        rows = list(word_reader._rows(table))
        if rows and all((row.find(f"{w('trPr')}/{w('ins')}") is not None and _peto(row.find(f"{w('trPr')}/{w('ins')}")))
                        for row in rows):
            table.getparent().remove(table)
            return
        for row in rows:
            self.retract(row)
            properties = row.find(w('trPr'))
            if properties is None:
                properties = etree.Element(w('trPr'))
                index = 1 if len(row) and etree.QName(row[0]).localname == 'tblPrEx' else 0
                row.insert(index, properties)
            if properties.find(w('del')) is None:
                change = properties.find(w('trPrChange'))
                if change is None:
                    properties.append(self.revisions.mark('del'))
                else:
                    change.addprevious(self.revisions.mark('del'))

    # --- thêm nội dung mới
    def insert_after(self, anchor, blocks) -> object:
        """Chèn các khối sau ``anchor``; trả về phần tử cuối cùng đã chèn (chỗ để lần chèn sau nối tiếp)."""
        writer = self.writer(anchor if etree.QName(anchor).localname == 'p' else _previous_paragraph(anchor))
        pieces: list[str] = []
        previous_table = etree.QName(anchor).localname == 'tbl'
        for block in blocks:
            for xml in writer.block(block):
                table = xml.startswith('<w:tbl>')
                if table and previous_table:
                    # Hai bảng liền nhau thì Word gộp làm một: chen một đoạn trống (cũng là phần Peto chèn).
                    pieces.append(writer.empty_paragraph())
                pieces.append(xml)
                previous_table = table
        if not pieces:
            return anchor
        following = anchor.getnext()
        if previous_table and (following is None or etree.QName(following).localname in {'tbl', 'sectPr'}):
            pieces.append(writer.empty_paragraph())
        last = anchor
        for element in fragment(''.join(pieces)):
            last.addnext(element)
            last = element
        return last

    def replace_paragraph(self, paragraph, blocks) -> None:
        writer = self.writer(paragraph)
        runs = _single_paragraph(blocks)
        self.retract(paragraph)
        paragraph.append(fragment(f'<w:ins {self.revisions.attrs()}>{writer.runs(runs)}</w:ins>')[0])

    def fill_cell(self, cell, blocks) -> None:
        paragraphs = [item for item in cell if etree.QName(item).localname == 'p']
        near = next((item for item in paragraphs if ''.join(item.itertext()).strip()), paragraphs[0] if paragraphs else None)
        writer = self.writer(near)
        runs = _single_paragraph(blocks, joined=True)
        for paragraph in paragraphs:
            self.retract(paragraph)
        if not paragraphs:
            cell.append(fragment(writer.paragraph(writer.runs(runs)))[0])
            return
        paragraphs[0].append(fragment(f'<w:ins {self.revisions.attrs()}>{writer.runs(runs)}</w:ins>')[0])


def _previous_paragraph(element):
    node = element.getprevious()
    while node is not None and etree.QName(node).localname != 'p':
        node = node.getprevious()
    return node


def _single_paragraph(blocks, joined: bool = False) -> list:
    """Chữ của content dạng một đoạn (thay đoạn, điền ô). Ô bảng nhận nhiều dòng, nối bằng xuống dòng."""
    from features.documents.export import Run
    usable = [block for block in blocks if block.kind in {'paragraph', 'heading', 'quote', 'math', 'code'}]
    if len(usable) != len(blocks) or not usable:
        raise ValueError('content ở đây chỉ được là chữ (có thể có công thức), không có bảng, ảnh hay danh sách lồng.')
    if len(usable) > 1 and not joined:
        raise ValueError('replace chỉ thay bằng một đoạn. Muốn thêm đoạn mới thì dùng insert_after.')
    runs: list = []
    for index, block in enumerate(usable):
        if index:
            runs.append(Run('\n'))
        runs.extend([Run(block.math, math=True)] if block.kind == 'math' else block.runs)
    return runs


def _cell(table, row: int, column: int):
    rows = list(word_reader._rows(table))
    if not 1 <= row <= len(rows):
        raise ValueError(f'bảng có {len(rows)} hàng, không có hàng {row}.')
    position = 0
    cells = [item for item in rows[row - 1] if etree.QName(item).localname == 'tc']
    widest = 0
    for cell in cells:
        span = cell.find(f"{w('tcPr')}/{w('gridSpan')}")
        width = int(span.get(w('val'), '1')) if span is not None and span.get(w('val'), '1').isdigit() else 1
        if position < column <= position + width:
            merge = cell.find(f"{w('tcPr')}/{w('vMerge')}")
            if merge is not None and merge.get(w('val')) != 'restart':
                raise ValueError(f'ô hàng {row}, cột {column} nằm trong vùng gộp với ô phía trên; điền vào ô đầu của vùng gộp.')
            return cell
        position += width
        widest = position
    raise ValueError(f'hàng {row} của bảng có {widest} cột, không có cột {column}.')


def describe(change: Change, kind: str, number: int, blocks) -> str:
    where = _label(kind, number)
    if change.action == 'delete':
        return f'Xóa {where}'
    if change.action == 'fill_cell':
        return f'Điền {where}, ô hàng {change.row} cột {change.column}: {_short(change.content or "")}'
    if change.action == 'replace':
        return f'Thay chữ {where}: {_short(change.content or "")}'
    counts = {'table': 0, 'math': 0, 'text': 0}
    for block in blocks:
        if block.kind == 'table':
            counts['table'] += 1
        elif block.kind == 'math':
            counts['math'] += 1
        elif block.kind != 'rule':
            counts['text'] += 1
    parts = [f'{counts["text"]} đoạn' if counts['text'] else '', f'{counts["math"]} công thức' if counts['math'] else '',
             f'{counts["table"]} bảng' if counts['table'] else '']
    return f'Chèn sau {where}: ' + ', '.join(part for part in parts if part)


def _short(text: str, limit: int = 60) -> str:
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _readers(package: Package):
    return package.optional('word/numbering.xml'), package.optional('word/styles.xml')


def _body(numbering_root, styles_root) -> word_reader.Body:
    numbering = word_reader.Numbering(numbering_root, styles_root) if numbering_root is not None else None
    return word_reader.Body(numbering)


def run(data: bytes, changes: list[dict], date: str, excerpt_chars: int) -> dict:
    """Chạy trong tiến trình riêng (tools.DocumentSession.revise). Trả về tệp mới, các dòng thay đổi, chữ đọc lại của tệp
    mới (để Peto đọc ở lượt sau) và dữ liệu xem trước; hoặc ``error`` liệt kê mọi lỗi."""
    try:
        package = Package(data)
        root = package.document()
        numbering_root, styles_root = _readers(package)
        found = {(kind, number): element
                 for kind, number, element, _ in word_reader.numbered_blocks(word_reader.body_of(root),
                                                                              _body(numbering_root, styles_root))}
        paragraphs = sum(kind == 'p' for kind, _ in found)
        tables = len(found) - paragraphs
        if sum(len(item.get('content') or '') for item in changes) > MAX_TOTAL:
            raise EditError('Nội dung chèn trong một lần quá dài. Chia thành vài lần gọi edit_document.')
        plan, problems = [], []
        for index, raw in enumerate(changes, 1):
            change = Change.model_validate(raw)
            head = f'Thay đổi {index} ({_VERBS[change.action]} {change.target})'
            try:
                target = parse_target(change.target)
                if target is None:
                    raise ValueError('target phải là "Đoạn N" hoặc "Bảng N".')
                kind, number = target
                element = found.get(target)
                if element is None:
                    raise ValueError(f'tệp không có {_label(kind, number)} (có {paragraphs} đoạn, {tables} bảng có thể sửa).')
                blocks = []
                if change.action != 'delete':
                    if not (change.content or '').strip():
                        raise ValueError('cần content.')
                    blocks = parse_blocks(change.content)
                    if any(block.kind in {'image', 'slot', 'toc', 'logo'} for block in blocks):
                        raise ValueError('content chưa nhận ảnh, khung ảnh hay mục lục.')
                cell = None
                if change.action == 'replace':
                    if kind != 'p':
                        raise ValueError('replace chỉ dùng cho đoạn; điền bảng thì dùng fill_cell.')
                    _single_paragraph(blocks)
                elif change.action == 'fill_cell':
                    if kind != 'tbl':
                        raise ValueError('fill_cell cần target là một bảng.')
                    if not change.row or not change.column:
                        raise ValueError('fill_cell cần row và column (đếm từ 1).')
                    cell = _cell(element, change.row, change.column)
                    if cell.find(f'.//{w("tbl")}') is not None:
                        raise ValueError('ô này có bảng lồng bên trong, Peto chưa điền được.')
                    _single_paragraph(blocks, joined=True)
                if change.action in {'replace', 'delete', 'fill_cell'}:
                    reason = locked(cell if cell is not None else element)
                    if reason:
                        raise ValueError(f'chỗ này có {reason} nên Peto không thay hay xóa được an toàn. '
                                         'Chèn đoạn mới bằng insert_after, để người dùng tự xóa phần cũ trong Word.')
                plan.append((change, kind, number, element, cell, blocks))
            except ValueError as error:
                problems.append(f'{head}: {error}')
        if problems:
            more = len(problems) - MAX_PROBLEMS
            text = '\n'.join(problems[:MAX_PROBLEMS]) + (f'\n(và {more} lỗi khác cùng loại)' if more > 0 else '')
            return {'error': text}
        editor = Editor(root, date)
        lines: list[str] = []
        # Mã dấu sửa (w:id) mỗi thay đổi đã dùng, [đầu, cuối]: bản xem dựa vào đó để bấm một dòng thay đổi là tới đúng
        # chỗ, kể cả khi tệp còn dấu của những lần sửa trước. Thay đổi chỉ bỏ phần Peto tự chèn thì không có dấu nào.
        ranges: list[list[int]] = []
        anchors: dict = {}
        deletions = []
        for change, kind, number, element, cell, blocks in plan:
            lines.append(describe(change, kind, number, blocks))
            start = editor.revisions.next
            if change.action == 'insert_after':
                anchors[element] = editor.insert_after(anchors.get(element, element), blocks)
            elif change.action == 'replace':
                editor.replace_paragraph(element, blocks)
            elif change.action == 'fill_cell':
                editor.fill_cell(cell, blocks)
            else:
                deletions.append((len(ranges), kind, element))
            ranges.append([start, editor.revisions.next - 1])
        # Xóa sau cùng: một đoạn Peto chèn trước đó bị bỏ hẳn, và các phần chèn sau nó vẫn đúng chỗ.
        for index, kind, element in deletions:
            start = editor.revisions.next
            if element.getparent() is not None:
                (editor.delete_paragraph if kind == 'p' else editor.delete_table)(element)
            ranges[index] = [start, editor.revisions.next - 1]
        output = package.save(root)
        reread = word_reader.read_body(Package(output).document(), numbering_root, styles_root, excerpt_chars)
        return {'data': output, 'lines': lines, 'ranges': [item if item[1] >= item[0] else [] for item in ranges],
                'readout': reread['text'], 'shortened': reread['shortened'],
                'preview': word_preview.build(Package(output).document(), numbering_root, styles_root)}
    except EditError as error:
        return {'error': str(error)}
    except Exception as error:  # noqa: BLE001 - lỗi lạ của bộ sửa không được làm hỏng lượt chat
        return {'error': 'Bộ sửa Word gặp lỗi với tệp này. Không nói đã sửa xong; báo người dùng thử lại hoặc gửi bản '
                         'lưu lại bằng Word.', 'internal': f'{type(error).__name__}: {error}'}

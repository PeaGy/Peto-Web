"""Phần của tệp Excel nằm ngoài ô dữ liệu: biểu đồ, hình và hộp chữ, ghi chú trong ô, Bảng (Table) và bảng tổng hợp
(pivot). Dùng cho bộ đọc (chữ đưa Peto) và lưới xem tệp Peto đã sửa.

Chỉ đọc XML qua đối tượng gói của bộ đọc (workbook_reader._Package: .names, .xml(tên), .relationships(phần)), nên vẫn
cấm DTD và giới hạn cỡ từng phần. Tên thẻ so theo tên cục bộ, để tệp lưu kiểu Strict OOXML (không gian tên khác) cũng
đọc được. Một phần lỗi thì bỏ qua phần đó, không làm hỏng cả lượt đọc.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from features.documents.workbook_reader import (_local, _number, _relationship_id, column_letter, format_kind, general,
                                                show_number)

MAX_POINTS_SHOWN = 20       # số điểm mỗi chuỗi số liệu hiện trong chữ đưa Peto
MAX_SERIES_SHOWN = 8
MAX_COMMENT_CHARS = 300
MAX_TEXT_CHARS = 500        # chữ trong một hộp chữ
MAX_POINTS = 1000           # số điểm đọc mỗi chuỗi (lưới xem cần đủ điểm để vẽ)

# Loại biểu đồ: tên thẻ trong plotArea → tên tiếng Việt. Biểu đồ cột/thanh xét thêm barDir.
_KINDS = {
    'lineChart': 'đường', 'line3DChart': 'đường 3D', 'pieChart': 'tròn', 'pie3DChart': 'tròn 3D',
    'doughnutChart': 'vành khuyên', 'ofPieChart': 'tròn tách', 'areaChart': 'vùng', 'area3DChart': 'vùng 3D',
    'scatterChart': 'phân tán XY', 'bubbleChart': 'bong bóng', 'radarChart': 'radar', 'stockChart': 'chứng khoán',
    'surfaceChart': 'bề mặt', 'surface3DChart': 'bề mặt 3D',
}
# Biểu đồ đời mới (chartEx, Excel 2016): layoutId của chuỗi → tên.
_EX_KINDS = {
    'boxWhisker': 'hộp và râu', 'clusteredColumn': 'tần suất (histogram)', 'funnel': 'phễu', 'paretoLine': 'Pareto',
    'regionMap': 'bản đồ', 'sunburst': 'sunburst', 'treemap': 'treemap', 'waterfall': 'thác nước',
}
_SUBTOTALS = {
    'sum': 'tổng', 'count': 'đếm', 'average': 'trung bình', 'max': 'lớn nhất', 'min': 'nhỏ nhất', 'product': 'tích',
    'countNums': 'đếm số', 'stdDev': 'độ lệch chuẩn', 'stdDevp': 'độ lệch chuẩn tổng thể', 'var': 'phương sai',
    'varp': 'phương sai tổng thể',
}


def _children(element, name: str):
    return [child for child in element if _local(child.tag) == name] if element is not None else []


def _child(element, *names: str):
    """Con đầu tiên có một trong các tên cục bộ ``names``. Không dùng ``a or b`` với phần tử XML: phần tử không có con
    bị coi là sai."""
    if element is None:
        return None
    return next((child for child in element if _local(child.tag) in names), None)


def _find(element, *path: str):
    """Đi xuống theo tên cục bộ; thiếu một bậc thì None."""
    for name in path:
        if element is None:
            return None
        element = _child(element, name)
    return element


def _val(element, default: str = '') -> str:
    return element.get('val', default) if element is not None else default


def _text(element, name: str = 't') -> str:
    """Nối mọi chữ trong các thẻ ``name`` con cháu (chữ của DrawingML hay rich text của ô)."""
    if element is None:
        return ''
    return ''.join(node.text or '' for node in element.iter() if _local(node.tag) == name)


def _paragraphs(element) -> str:
    """Chữ của khối có đoạn (a:p): các đoạn ngăn bằng dấu cách."""
    if element is None:
        return ''
    paragraphs = [_text(node) for node in element.iter() if _local(node.tag) == 'p']
    return ' '.join(part.strip() for part in paragraphs if part.strip()) or _text(element).strip()


def _clip(text: str, limit: int) -> str:
    text = ' '.join(text.replace('\r', '\n').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def area(r1: int, c1: int, r2: int, c2: int) -> str:
    """Vùng ô từ chỉ số tính từ 0, như E2:L16."""
    first, last = f'{column_letter(c1)}{r1 + 1}', f'{column_letter(c2)}{r2 + 1}'
    return first if first == last else f'{first}:{last}'


# ---------- biểu đồ ----------

@dataclass
class Series:
    name: str = ''
    name_ref: str = ''
    categories_ref: str = ''
    values_ref: str = ''
    categories: list[str] = field(default_factory=list)
    values: list[float | None] = field(default_factory=list)
    kind: str = ''              # loại riêng của chuỗi (biểu đồ kết hợp)
    simple: str | None = None   # column, bar, line, pie: loại lưới xem vẽ được


@dataclass
class Chart:
    kind: str
    title: str
    series: list[Series]
    anchor: tuple[int, int, int, int] | None = None
    stacked: bool = False

    @property
    def simple(self) -> str | None:
        """Loại lưới xem vẽ lại được (cột, thanh, đường, tròn); biểu đồ kết hợp hay loại khác thì None."""
        kinds = {series.simple for series in self.series}
        return kinds.pop() if len(kinds) == 1 and not self.stacked else None


def _cache_points(cache, date1904: bool) -> list:
    """Điểm số liệu đã lưu (numCache, strCache, numLit, strLit), theo idx."""
    if cache is None:
        return []
    count = min(int(_val(_child(cache, 'ptCount'), '0') or 0), MAX_POINTS)
    code = _child(cache, 'formatCode')
    kind = format_kind(code.text or '') if code is not None else 'number'
    points: list = [None] * count
    for point in _children(cache, 'pt'):
        try:
            index = int(point.get('idx', '-1'))
        except ValueError:
            continue
        value = _child(point, 'v')
        if not 0 <= index < count or value is None or value.text is None:
            continue
        if _local(cache.tag) in ('numCache', 'numLit'):
            try:
                number = float(value.text)
            except ValueError:
                continue
            points[index] = number if kind not in ('date', 'datetime', 'time') else show_number(number, kind, date1904)
        else:
            points[index] = value.text
    return points


def _data(element, date1904: bool) -> tuple[str, list]:
    """(Tham chiếu, các điểm đã lưu) của c:cat, c:val, c:xVal, c:yVal, c:tx."""
    if element is None:
        return '', []
    for source in element:
        name = _local(source.tag)
        if name in ('numRef', 'strRef', 'multiLvlStrRef'):
            formula = _child(source, 'f')
            reference = (formula.text or '') if formula is not None else ''
            cache = _child(source, 'numCache', 'strCache')
            if name == 'multiLvlStrRef':
                cache = _child(source, 'multiLvlStrCache')
                level = _children(cache, 'lvl') if cache is not None else []
                # Nhãn nhiều tầng: lấy tầng trong cùng (tầng đầu trong tệp).
                cache = level[0] if level else None
                if cache is not None and _child(cache, 'ptCount') is None:
                    parent = _child(source, 'multiLvlStrCache')
                    count = _val(_child(parent, 'ptCount'), '0')
                    return reference, _level_points(cache, count)
            return reference, _cache_points(cache, date1904)
        if name in ('numLit', 'strLit'):
            return '', _cache_points(source, date1904)
        if name == 'v':
            return '', [source.text or '']
    return '', []


def _level_points(level, count: str) -> list:
    try:
        size = min(int(count), MAX_POINTS)
    except ValueError:
        size = 0
    points: list = [None] * size
    for point in _children(level, 'pt'):
        try:
            index = int(point.get('idx', '-1'))
        except ValueError:
            continue
        value = _child(point, 'v')
        if 0 <= index < size and value is not None:
            points[index] = value.text or ''
    return points


def _label(value) -> str:
    if value is None:
        return ''
    return general(value) if isinstance(value, float) else str(value)


def _chart_title(chart) -> str:
    title = _child(chart, 'title')
    if title is None:
        return ''
    text = _child(title, 'tx')
    if text is None:
        return ''
    rich = _child(text, 'rich')
    if rich is not None:
        return _paragraphs(rich)
    _, points = _data(text, False)
    return ' '.join(_label(point) for point in points if point is not None)


def read_chart(package, path: str, date1904: bool = False) -> Chart | None:
    """Biểu đồ thường (c:chartSpace) hoặc đời mới (cx:chartSpace)."""
    root = package.xml(path)
    if _local(root.tag) != 'chartSpace':
        return None
    chart = _child(root, 'chart')
    if chart is None:
        return None
    if _find(chart, 'plotArea') is None and _find(root, 'chartData') is not None:
        return _read_chart_ex(root, chart)
    plot = _child(chart, 'plotArea')
    series: list[Series] = []
    kinds: list[str] = []
    stacked = False
    for group in plot if plot is not None else ():
        name = _local(group.tag)
        if not name.endswith('Chart'):
            continue
        grouping = _val(_child(group, 'grouping'))
        if name in ('barChart', 'bar3DChart'):
            horizontal = _val(_child(group, 'barDir'), 'col') == 'bar'
            kind = 'thanh ngang' if horizontal else 'cột'
            simple = 'bar' if horizontal else 'column'
        else:
            kind = _KINDS.get(name, name.removesuffix('Chart'))
            simple = {'lineChart': 'line', 'pieChart': 'pie'}.get(name)
        if grouping in ('stacked', 'percentStacked'):
            stacked = True
            kind += ' chồng' + (' 100%' if grouping == 'percentStacked' else '')
        if kind not in kinds:
            kinds.append(kind)
        for ser in _children(group, 'ser'):
            item = Series(kind=kind, simple=simple)
            item.name_ref, names = _data(_child(ser, 'tx'), date1904)
            item.name = ' '.join(_label(point) for point in names if point is not None)
            categories = _child(ser, 'cat', 'xVal')
            item.categories_ref, labels = _data(categories, date1904)
            item.categories = [_label(point) for point in labels]
            values = _child(ser, 'val', 'yVal')
            item.values_ref, points = _data(values, date1904)
            item.values = [point if isinstance(point, float) else None for point in points]
            series.append(item)
    title = _chart_title(chart)
    if not title and _val(_child(chart, 'autoTitleDeleted'), '0') not in ('1', 'true') and len(series) == 1:
        title = series[0].name      # Excel lấy tên chuỗi duy nhất làm tiêu đề
    return Chart(' + '.join(kinds) or 'không rõ loại', title, series, stacked=stacked)


def _read_chart_ex(root, chart) -> Chart:
    data: dict[str, dict[str, tuple[str, list]]] = {}
    for item in _children(_child(root, 'chartData'), 'data'):
        dims: dict[str, tuple[str, list]] = {}
        for dim in item:
            if _local(dim.tag) not in ('strDim', 'numDim'):
                continue
            formula = _child(dim, 'f')
            level = _child(dim, 'lvl')
            points: list = []
            if level is not None:
                points = _level_points(level, level.get('ptCount', '0'))
                if _local(dim.tag) == 'numDim':
                    points = [_float(point) for point in points]
            dims[dim.get('type', '')] = ((formula.text or '') if formula is not None else '', points)
        data[item.get('id', '')] = dims
    series: list[Series] = []
    kinds: list[str] = []
    region = _find(chart, 'plotArea', 'plotAreaRegion')
    for ser in _children(region, 'series') if region is not None else ():
        kind = _EX_KINDS.get(ser.get('layoutId', ''), ser.get('layoutId', 'không rõ loại'))
        if kind not in kinds:
            kinds.append(kind)
        dims = data.get(_val(_child(ser, 'dataId')), {})
        name_data = _find(ser, 'tx', 'txData')
        item = Series(kind=kind)
        if name_data is not None:
            formula, value = _child(name_data, 'f'), _child(name_data, 'v')
            item.name_ref = (formula.text or '') if formula is not None else ''
            item.name = (value.text or '') if value is not None else ''
        item.categories_ref, labels = dims.get('cat', ('', []))
        item.categories = [_label(point) for point in labels]
        item.values_ref, points = dims.get('val', dims.get('size', ('', [])))
        item.values = [point if isinstance(point, float) else None for point in points]
        series.append(item)
    title = _find(chart, 'title', 'tx')
    text = ''
    if title is not None:
        value = _find(title, 'txData', 'v')
        text = (value.text or '') if value is not None else _paragraphs(_child(title, 'rich'))
    return Chart(' + '.join(kinds) or 'không rõ loại', text.strip(), series)


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def describe_chart(chart: Chart, where: str = '') -> list[str]:
    """Các dòng chữ đưa Peto: loại, tiêu đề, chỗ đặt, rồi mỗi chuỗi số liệu với tham chiếu và vài điểm đã lưu."""
    title = f' "{_clip(chart.title, 120)}"' if chart.title else ' (không có tiêu đề)'
    lines = [f'Biểu đồ {chart.kind}{title}{where}:']
    for series in chart.series[:MAX_SERIES_SHOWN]:
        name = f'"{_clip(series.name, 60)}"' if series.name else 'không tên'
        refs = [part for part in (f'số liệu {series.values_ref}' if series.values_ref else '',
                                  f'nhãn {series.categories_ref}' if series.categories_ref else '') if part]
        head = f'  chuỗi {name}' + (f' ({", ".join(refs)})' if refs else '')
        points = [(series.categories[index] if index < len(series.categories) else '', value)
                  for index, value in enumerate(series.values)]
        if not points:
            lines.append(head + ': chưa có số liệu lưu sẵn')
            continue
        shown = '; '.join(f'{_clip(label, 30)} {_label(value) if value is not None else "(trống)"}'.strip()
                          for label, value in points[:MAX_POINTS_SHOWN])
        more = f' … ({_number(len(points))} điểm)' if len(points) > MAX_POINTS_SHOWN else ''
        lines.append(f'{head}: {shown}{more}')
    if len(chart.series) > MAX_SERIES_SHOWN:
        lines.append(f'  … và {len(chart.series) - MAX_SERIES_SHOWN} chuỗi khác')
    return lines


# ---------- hình vẽ trên trang tính ----------

@dataclass
class Drawing:
    charts: list[Chart] = field(default_factory=list)
    texts: list[tuple[str, str]] = field(default_factory=list)      # (chỗ đặt, chữ trong hộp chữ/hình)
    images: list[tuple[str, str]] = field(default_factory=list)     # (chỗ đặt, mô tả thay thế)


def _anchor(anchor) -> tuple[int, int, int, int] | None:
    def cell(element):
        if element is None:
            return None
        try:
            return int(_child(element, 'row').text), int(_child(element, 'col').text)
        except (AttributeError, TypeError, ValueError):
            return None
    start = cell(_child(anchor, 'from'))
    if start is None:
        return None
    end = cell(_child(anchor, 'to')) or start
    return start[0], start[1], max(start[0], end[0]), max(start[1], end[1])


def _visible(element):
    """Con cháu của một neo, bỏ nhánh mc:Fallback (hình thay thế cho Excel cũ, như "biểu đồ này không có trong bản Excel
    của bạn")."""
    stack = [element]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed([child for child in node if _local(child.tag) != 'Fallback']))


def _anchors(root):
    """Các neo hình của bản vẽ. Biểu đồ đời mới nằm trong mc:AlternateContent: lấy neo trong mc:Choice, bỏ mc:Fallback."""
    for node in root:
        name = _local(node.tag)
        if name in ('twoCellAnchor', 'oneCellAnchor', 'absoluteAnchor'):
            yield node
        elif name == 'AlternateContent':
            choice = _child(node, 'Choice')
            if choice is not None:
                yield from _anchors(choice)


def read_drawing(package, path: str, date1904: bool = False) -> Drawing:
    drawing = Drawing()
    relations = package.relationships(path)
    root = package.xml(path)
    for anchor in _anchors(root):
        place = _anchor(anchor)
        where = f' ở {area(*place)}' if place else ''
        for node in _visible(anchor):
            name = _local(node.tag)
            if name == 'chart':
                target = relations.get(_relationship_id(node), ('', ''))[0]
                if target in package.names:
                    try:
                        chart = read_chart(package, target, date1904)
                    except Exception:
                        chart = None
                    if chart is not None:
                        chart.anchor = place
                        drawing.charts.append(chart)
            elif name == 'sp':
                body = _child(node, 'txBody')
                text = _paragraphs(body) if body is not None else ''
                if text.strip():
                    drawing.texts.append((where, _clip(text, MAX_TEXT_CHARS)))
            elif name == 'pic':
                properties = _find(node, 'nvPicPr', 'cNvPr')
                description = (properties.get('descr') or '') if properties is not None else ''
                drawing.images.append((where, _clip(description, 150)))
    return drawing


# ---------- ghi chú trong ô ----------

@dataclass
class Note:
    ref: str
    author: str
    text: str
    replies: list[tuple[str, str]] = field(default_factory=list)   # (người trả lời, chữ)
    when: str = ''
    threaded: bool = False
    done: bool = False


def read_people(package, workbook_part: str) -> dict[str, str]:
    """Id → tên hiển thị của người viết bình luận dạng hội thoại (xl/persons/person.xml)."""
    people: dict[str, str] = {}
    for target, kind in package.relationships(workbook_part).values():
        if kind.endswith('/person') and target in package.names:
            for person in package.xml(target):
                if _local(person.tag) == 'person':
                    people[person.get('id', '')] = person.get('displayName', '')
    return people


def read_notes(package, sheet_part: str, people: dict[str, str]) -> list[Note]:
    """Ghi chú cũ (comments) và bình luận dạng hội thoại (threadedComments) của một trang tính, theo thứ tự ô."""
    notes: dict[str, Note] = {}
    threaded: dict[str, Note] = {}
    relations = package.relationships(sheet_part)
    for target, kind in relations.values():
        if target not in package.names:
            continue
        if kind.endswith('/threadedComment'):
            by_id: dict[str, Note] = {}
            for item in package.xml(target):
                if _local(item.tag) != 'threadedComment':
                    continue
                author = people.get(item.get('personId', ''), '')
                body = _child(item, 'text')
                text = (body.text or '') if body is not None else ''
                parent = by_id.get(item.get('parentId', ''))
                if parent is not None:
                    parent.replies.append((author, text))
                    continue
                note = Note(item.get('ref', ''), author, text, when=(item.get('dT') or '')[:10], threaded=True,
                            done=item.get('done') in ('1', 'true'))
                by_id[item.get('id', '')] = note
                threaded.setdefault(note.ref, note)
    for target, kind in relations.values():
        if not kind.endswith('/comments') or target not in package.names:
            continue
        root = package.xml(target)
        authors = [author.text or '' for author in _children(_child(root, 'authors'), 'author')]
        for comment in _children(_child(root, 'commentList'), 'comment'):
            ref = comment.get('ref', '')
            if ref in threaded:
                continue        # bản ghi chú cũ của bình luận hội thoại chỉ là chữ thay thế cho Excel cũ
            try:
                author = authors[int(comment.get('authorId', '0'))]
            except (ValueError, IndexError):
                author = ''
            text = _text(_child(comment, 'text')).strip()
            # Ghi chú Excel thường mở đầu bằng tên người viết và dấu hai chấm.
            if author and text.startswith(author + ':'):
                text = text[len(author) + 1:].strip()
            notes[ref] = Note(ref, author, text)
    notes.update(threaded)
    return sorted(notes.values(), key=lambda note: _cell_order(note.ref))


def _cell_order(ref: str) -> tuple[int, int]:
    letters = ''.join(char for char in ref if char.isalpha())
    digits = ''.join(char for char in ref if char.isdigit())
    column = 0
    for char in letters.upper():
        column = column * 26 + ord(char) - 64
    return (int(digits) if digits else 0, column)


def describe_note(note: Note) -> str:
    who = f' · {note.author}' if note.author else ''
    label = 'Bình luận' if note.threaded else 'Ghi chú'
    when = f', {note.when}' if note.when else ''
    state = ', đã giải quyết' if note.done else ''
    line = f'{label} {note.ref}{who}{when}{state}: {_clip(note.text, MAX_COMMENT_CHARS)}'
    for author, text in note.replies[:5]:
        line += f' ↳ {author or "trả lời"}: {_clip(text, 160)}'
    if len(note.replies) > 5:
        line += f' ↳ … và {len(note.replies) - 5} trả lời khác'
    return line


# ---------- Bảng (Table) ----------

@dataclass
class Table:
    name: str
    ref: str
    columns: list[tuple[str, str]]       # (tên cột, công thức cột tính)
    totals: bool = False
    header: bool = True


def read_table(package, path: str) -> Table | None:
    root = package.xml(path)
    if _local(root.tag) != 'table':
        return None
    columns = []
    for column in _children(_child(root, 'tableColumns'), 'tableColumn'):
        formula = _child(column, 'calculatedColumnFormula')
        columns.append((column.get('name', ''), (formula.text or '').strip() if formula is not None else ''))
    # totalsRowShown chỉ nói hàng tổng từng được bật; totalsRowCount mới là hàng tổng đang có.
    totals = (root.get('totalsRowCount') or '0') not in ('0', '')
    return Table(root.get('displayName') or root.get('name', ''), root.get('ref', ''), columns, totals,
                 (root.get('headerRowCount') or '1') != '0')


def describe_table(table: Table) -> str:
    parts = []
    for name, formula in table.columns[:30]:
        parts.append(f'{name} = {formula}' if formula else name)
    more = f' … và {len(table.columns) - 30} cột khác' if len(table.columns) > 30 else ''
    totals = ', có hàng tổng' if table.totals else ''
    return f'Bảng Excel "{table.name}" ở {table.ref}{totals}: cột {", ".join(parts)}{more}'


# ---------- bảng tổng hợp ----------

@dataclass
class Pivot:
    name: str
    location: str
    source: str
    rows: list[str]
    columns: list[str]
    values: list[str]
    filters: list[str]


def _shared_items(field_element) -> list[str]:
    items = _child(field_element, 'sharedItems')
    out = []
    for item in items if items is not None else ():
        name = _local(item.tag)
        if name == 'm':
            out.append('(trống)')
        elif name == 'b':
            out.append('TRUE' if item.get('v') in ('1', 'true') else 'FALSE')
        elif name == 'n':
            number = _float(item.get('v'))
            out.append(general(number) if number is not None else item.get('v', ''))
        else:
            out.append(item.get('v', ''))
    return out


def read_pivot(package, path: str) -> Pivot | None:
    root = package.xml(path)
    if _local(root.tag) != 'pivotTableDefinition':
        return None
    cache_path = next((target for target, kind in package.relationships(path).values()
                       if kind.endswith('/pivotCacheDefinition')), None)
    fields: list[str] = []
    shared: list[list[str]] = []
    source = 'nguồn không rõ'
    if cache_path and cache_path in package.names:
        cache = package.xml(cache_path)
        origin = _child(cache, 'cacheSource')
        if origin is not None:
            kind = origin.get('type', 'worksheet')
            sheet = _child(origin, 'worksheetSource')
            if kind == 'worksheet' and sheet is not None:
                if sheet.get('name'):
                    source = f'nguồn {sheet.get("name")}'
                elif sheet.get('sheet'):
                    from features.documents.sheets.formula import quote_sheet
                    source = f'nguồn {quote_sheet(sheet.get("sheet"))}!{sheet.get("ref", "")}'
                if _relationship_id(sheet):
                    source += ' (tệp khác)'
            elif kind == 'external':
                source = 'nguồn ngoài tệp (kết nối dữ liệu)'
            elif kind == 'consolidation':
                source = 'nguồn hợp nhất nhiều vùng'
        for cache_field in _children(_child(cache, 'cacheFields'), 'cacheField'):
            fields.append(cache_field.get('name', ''))
            shared.append(_shared_items(cache_field))
    pivot_fields = _children(_child(root, 'pivotFields'), 'pivotField')

    def field_name(index: str) -> str:
        try:
            number = int(index)
        except ValueError:
            return '?'
        if number == -2:
            return 'Giá trị'
        return fields[number] if 0 <= number < len(fields) else f'trường {number + 1}'

    def axis(name: str) -> list[str]:
        return [field_name(item.get('x', '')) for item in _children(_child(root, name), 'field')]

    values = []
    for data_field in _children(_child(root, 'dataFields'), 'dataField'):
        how = _SUBTOTALS.get(data_field.get('subtotal', 'sum'), data_field.get('subtotal', 'sum'))
        label = data_field.get('name') or f'{how} của {field_name(data_field.get("fld", ""))}'
        values.append(f'{label} ({how} của {field_name(data_field.get("fld", ""))})')
    filters = []
    for page in _children(_child(root, 'pageFields'), 'pageField'):
        name = field_name(page.get('fld', ''))
        chosen = 'tất cả'
        try:
            number = int(page.get('fld', ''))
            if page.get('item') is not None:
                items = _children(_child(pivot_fields[number], 'items'), 'item')
                position = int(items[int(page.get('item'))].get('x', '-1'))
                chosen = shared[number][position]
        except (ValueError, IndexError, TypeError):
            pass
        filters.append(f'{name} = {chosen}')
    location = _child(root, 'location')
    return Pivot(root.get('name', ''), location.get('ref', '') if location is not None else '', source,
                 axis('rowFields'), axis('colFields'), values, filters)


def describe_pivot(pivot: Pivot) -> str:
    parts = []
    if pivot.rows:
        parts.append('hàng: ' + ', '.join(pivot.rows))
    if pivot.columns:
        parts.append('cột: ' + ', '.join(pivot.columns))
    if pivot.values:
        parts.append('giá trị: ' + ', '.join(pivot.values))
    if pivot.filters:
        parts.append('lọc: ' + ', '.join(pivot.filters))
    return f'Bảng tổng hợp "{pivot.name}" ở {pivot.location} ({pivot.source}): ' + '; '.join(parts) + \
        '. Số trong vùng này là kết quả Excel lưu lần làm mới gần nhất.'

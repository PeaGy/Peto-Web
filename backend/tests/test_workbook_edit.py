"""Sửa thẳng tệp Excel người dùng gửi (workbook_edit): ghi ô, điền công thức, định dạng, chèn/xóa hàng cột, thêm và đổi
tên trang, Bảng (Table), tính lại công thức phụ thuộc, và giữ nguyên mọi phần khác của tệp."""
import io
import json
from urllib.parse import quote
import re
import zipfile
from datetime import date, datetime

import pytest
from lxml import etree

from features.documents import reader, workbook_reader
from features.documents.workbook_edit import book as book_module, ops, refs
from features.documents.workbook_edit.ops import ChangeInput, apply
from features.documents.workbook_edit.package import EditError
from test_workbook_reader import workbook

TODAY = date(2026, 10, 5)
MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def change(action='set', sheet='Lương', **fields):
    values = dict(action=action, sheet=sheet, range=None, values=None, value=None, format_from=None, bold=None,
                  italic=None, font_color=None, fill_color=None, number_format=None, decimals=None, align=None,
                  new_name=None)
    values.update(fields)
    return ChangeInput(**values)


def edit(data, *changes):
    return apply(data, list(changes), TODAY)


def parts(data) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def xml(data, name) -> str:
    return parts(data)[name].decode('utf-8')


def read(data, chars=80_000) -> str:
    return reader.extract_document(data, workbook_reader.XLSX_MIME, chars, 100)['text']


def salary(book):
    sheet = book.add_worksheet('Lương')
    head = book.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1})
    money = book.add_format({'num_format': '#,##0 "₫"', 'border': 1})
    sheet.write_row(0, 0, ['Họ tên', 'Lương', 'Phụ cấp', 'Tổng'], head)
    people = [('An', 10_000_000, 500_000), ('Bình', 12_000_000, 0), ('Chi', 9_000_000, 700_000)]
    for row, (name, base, extra) in enumerate(people, start=1):
        sheet.write_string(row, 0, name)
        sheet.write_number(row, 1, base, money)
        sheet.write_number(row, 2, extra, money)
        sheet.write_formula(row, 3, f'=B{row + 1}+C{row + 1}', money, base + extra)
    sheet.write_string(4, 0, 'Cộng', head)
    for col in (1, 2, 3):
        letter = 'BCD'[col - 1]
        sheet.write_formula(4, col, f'=SUM({letter}2:{letter}4)', money, sum(p[col] if col < 3 else p[1] + p[2] for p in people))
    other = book.add_worksheet('Ghi chú')
    other.write('A1', 'Không đụng tới')
    other.write_formula('B1', "='Lương'!D5", None, 32_200_000)


# ---------- ghi ô, điền công thức, giữ nguyên phần khác ----------

def test_set_and_fill_keep_formats_recalculate_and_leave_other_parts_untouched():
    original = workbook(salary)
    result = edit(original,
                  change(range='E1', values=[['Thưởng']], format_from='D1'),
                  change('fill', range='E2:E4', value='=B2*10%', format_from='D2'),
                  change(range='B3', values=[['13000000']]))
    text = read(result.data)
    assert 'Hàng 1 | A: Họ tên | B: Lương | C: Phụ cấp | D: Tổng | E: Thưởng' in text
    assert 'Công thức E2:E4 (chép xuống, 3 ô): =B2*10%' in text
    assert 'Hàng 3 | A: Bình | B: 13000000 | C: 0 | D: 13000000 | E: 1300000' in text
    # Tổng và ô trang khác trỏ tới tổng được tính lại; kết quả lưu trong tệp, không phải 0.
    assert 'Hàng 5 | A: Cộng | B: 32000000 | C: 1200000 | D: 33200000' in text
    assert 'Hàng 1 | A: Không đụng tới | B: 33200000' in text
    assert result.lines[0] == "'Lương'!E1: (trống) → \"Thưởng\""
    assert result.lines[2] == "'Lương'!B3: 12000000 → 13000000"
    assert any('E2 = 1000000' in line and 'E4 = 900000' in line for line in result.results)
    assert result.changed['Lương'] == [(0, 4, 3, 4), (2, 1, 2, 1)]
    before, after = parts(original), parts(result.data)
    assert list(before) == list(after)
    changed = {name for name in after if after[name] != before[name]}
    assert changed == {'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml', 'xl/workbook.xml', 'xl/sharedStrings.xml'}
    sheet = xml(result.data, 'xl/worksheets/sheet1.xml')
    # E1 mang kiểu ô tiêu đề như D1, cột E mang định dạng tiền như cột D.
    styles = dict(re.findall(r'<c r="([A-Z]+\d+)" s="(\d+)"', sheet))
    assert styles['E1'] == styles['D1'] and styles['E2'] == styles['D2'] == styles['E4']
    assert 'fullCalcOnLoad="1"' in xml(result.data, 'xl/workbook.xml')
    for name, data in after.items():
        if name.endswith(('.xml', '.rels')):
            etree.fromstring(data)


def test_value_syntax_formats_and_refusals():
    def build(book):
        sheet = book.add_worksheet('Lương')
        sheet.write_string('A1', 'mã', book.add_format({'num_format': '@'}))
        sheet.write_string('A2', 'cũ')
    data = workbook(build)
    result = edit(data, change(range='A1', values=[['0123', "'=không phải công thức", '8.5%', '2026-10-05', 'TRUE', '']]),
                  change(range='A2', values=[['']]))
    text = read(result.data)
    assert "Hàng 1 | A: 0123 | B: =không phải công thức | C: 8.5% | D: 2026-10-05 | E: TRUE" in text
    assert 'Hàng 2' not in text
    styles = xml(result.data, 'xl/styles.xml')
    assert 'formatCode="0.0%"' in styles and 'numFmtId="14"' in styles
    for raw, message in (('1.500.000', 'số dạng máy'), ('7,5', 'số dạng máy'), ('2026-02-30', 'không có thật'),
                         ('1899-05-01', 'trước 01/03/1900'), ('=SUM(A1:A2', 'thiếu dấu')):
        with pytest.raises(EditError, match=message):
            edit(data, change(range='B5', values=[[raw]]))


@pytest.mark.parametrize('values, message', [
    ('=B2/0', '#DIV/0!'),
    ('=XLOOKUP(A2,A:A,B:B)', 'chưa được hỗ trợ'),
    ("='Không có'!A1", 'Không có trang tính'),
])
def test_new_formula_errors_are_refused_with_the_cell(values, message):
    with pytest.raises(EditError, match=re.escape(message)):
        edit(workbook(salary), change(range='E2', values=[[values]]))


def test_cycles_and_merged_cells_are_refused():
    def build(book):
        sheet = book.add_worksheet('Lương')
        sheet.merge_range('A1:C1', 'Tiêu đề')
    data = workbook(build)
    with pytest.raises(EditError, match='vòng tham chiếu'):
        edit(data, change(range='D2', values=[['=D3'], ['=D2']]))
    with pytest.raises(EditError, match='ô B1 nằm trong vùng gộp A1:C1; ghi vào ô đầu A1'):
        edit(data, change(range='B1', values=[['x']]))
    assert 'Mới' in read(edit(data, change(range='A1', values=[['Mới']])).data)


def test_dependents_follow_chains_whole_columns_and_other_sheets():
    def build(book):
        sheet = book.add_worksheet('Lương')
        for row in range(200):
            sheet.write_number(row, 0, 1)
            sheet.write_formula(row, 1, f'=A{row + 1}' if row == 0 else f'=B{row}+A{row + 1}', None, row + 1)
        sheet.write_formula('C1', '=SUM(B:B)', None, sum(range(1, 201)))
        other = book.add_worksheet('Báo cáo')
        other.write_formula('A1', "=Lương!B200*2", None, 400)
        other.write_formula('A2', '=A1+1', None, 401)
    result = edit(workbook(build), change(range='A1', values=[['11']]))
    text = read(result.data)
    assert 'Hàng 200 | A: 1 | B: 210' in text
    assert f'Hàng 1 | A: 11 | B: 11 | C: {sum(range(1, 201)) + 2000}' in text
    assert 'Hàng 1 | A: 420' in text and 'Hàng 2 | A: 421' in text
    assert any('Đã tính lại 203 công thức' in note for note in result.notes)


def test_unknown_functions_lose_stale_results_and_others_keep_theirs():
    def build(book):
        sheet = book.add_worksheet('Lương')
        sheet.write_number('A1', 2)
        sheet.write_formula('B1', '=_xlfn.TEXTJOIN(",",TRUE,A1:A2)', None, '2')
        sheet.write_formula('C1', '=_xlfn.TEXTJOIN(",",TRUE,D1)', None, 'giữ')
        sheet.write_formula('E1', '=B1&"!"', None, '2!')
    result = edit(workbook(build), change(range='A2', values=[['3']]))
    sheet = xml(result.data, 'xl/worksheets/sheet1.xml')
    assert re.search(r'<c r="B1"[^>]*><f>[^<]+</f></c>', sheet)
    assert re.search(r'<c r="C1"[^>]*t="str"><f>[^<]+</f><v>giữ</v></c>', sheet)
    assert re.search(r'<c r="E1"[^>]*><f>[^<]+</f></c>', sheet), 'phụ thuộc công thức chưa tính được thì cũng bỏ kết quả'
    note = next(note for note in result.notes if 'Excel sẽ tự tính' in note)
    assert '2 công thức' in note and 'TEXTJOIN' in note


def build_package(parts_map: dict[str, str | bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts_map.items():
            archive.writestr(name, content)
    return output.getvalue()


def minimal(sheet_rows: str, *, sheet_extra: str = '', extra: dict | None = None, workbook_extra: str = '',
            workbook_rels: str = '', sheet_rels: str = '', content: str = '', sheets: str = '') -> bytes:
    return build_package({
        '[Content_Types].xml': ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                                '<Default Extension="xml" ContentType="application/xml"/>'
                                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
                                f'officedocument.spreadsheetml.sheet.main+xml"/>{content}</Types>'),
        '_rels/.rels': (f'<Relationships xmlns="{PKG}"><Relationship Id="r1" Type="{REL}/officeDocument" '
                        'Target="xl/workbook.xml"/></Relationships>'),
        'xl/workbook.xml': (f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets><sheet name="Dữ liệu" sheetId="1" '
                            f'r:id="rId1"/>{sheets}</sheets>{workbook_extra}</workbook>'),
        'xl/_rels/workbook.xml.rels': (f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{REL}/worksheet" '
                                       f'Target="worksheets/sheet1.xml"/>{workbook_rels}</Relationships>'),
        'xl/worksheets/sheet1.xml': f'<worksheet xmlns="{MAIN}" xmlns:r="{REL}"><sheetData>{sheet_rows}</sheetData>{sheet_extra}</worksheet>',
        **({'xl/worksheets/_rels/sheet1.xml.rels': f'<Relationships xmlns="{PKG}">{sheet_rels}</Relationships>'}
           if sheet_rels else {}),
        **(extra or {}),
    })


def test_shared_formulas_are_opened_before_overwriting_one_cell():
    rows = ''.join(f'<row r="{r}"><c r="A{r}"><v>{r}</v></c><c r="B{r}">'
                   + ('<f t="shared" ref="B1:B4" si="0">A1*2</f>' if r == 1 else '<f t="shared" si="0"/>')
                   + f'<v>{r * 2}</v></c></row>' for r in range(1, 5))
    result = edit(minimal(rows), change(sheet='Dữ liệu', range='B1', values=[['=A1*3']]))
    sheet = xml(result.data, 'xl/worksheets/sheet1.xml')
    assert 'si=' not in sheet
    assert '<f>A1*3</f><v>3</v>' in sheet and '<f>A2*2</f><v>4</v>' in sheet and '<f>A4*2</f><v>8</v>' in sheet


def test_array_formulas_pivots_totals_and_protection_are_guarded():
    rows = ('<row r="1"><c r="A1"><f t="array" ref="A1:A3">ROW(B1:B3)</f><v>1</v></c></row>'
            '<row r="2"><c r="A2"><v>2</v></c></row><row r="3"><c r="A3"><v>3</v></c></row>')
    data = minimal(rows)
    with pytest.raises(EditError, match='công thức mảng A1:A3'):
        edit(data, change(sheet='Dữ liệu', range='A2', values=[['5']]))
    whole = edit(data, change(sheet='Dữ liệu', range='A1', values=[['7'], ['8'], ['9']]))
    assert 't="array"' not in xml(whole.data, 'xl/worksheets/sheet1.xml')
    protected = minimal('<row r="1"><c r="A1"><v>1</v></c></row>', sheet_extra='<sheetProtection sheet="1" objects="1"/>')
    with pytest.raises(EditError, match='đang được bảo vệ'):
        edit(protected, change(sheet='Dữ liệu', range='A2', values=[['5']]))
    locked = minimal('<row r="1"><c r="A1"><v>1</v></c></row>', workbook_extra='<workbookProtection lockStructure="1"/>')
    with pytest.raises(EditError, match='Protect Workbook'):
        edit(locked, change('add_sheet', sheet='Mới'))

    def totals(book):
        sheet = book.add_worksheet('Lương')
        sheet.add_table('A1:B4', {'name': 'Bang', 'total_row': True,
                                  'columns': [{'header': 'Tên', 'total_string': 'Cộng'}, {'header': 'Số', 'total_function': 'sum'}],
                                  'data': [['a', 1], ['b', 2]]})
    with pytest.raises(EditError, match='hàng tổng của Bảng "Bang"'):
        edit(workbook(totals), change(range='B4', values=[['9']]))


# ---------- Bảng (Table) ----------

def staff(book):
    sheet = book.add_worksheet('Lương')
    sheet.add_table('A1:C4', {'name': 'NhanVien', 'columns': [
        {'header': 'Tên'}, {'header': 'Lương'}, {'header': 'Thưởng', 'formula': '=[@Lương]*10%'}],
        'data': [['An', 1000], ['Bình', 1200], ['Chi', 900]]})
    sheet.write_formula('E1', '=SUM(NhanVien[Lương])', None, 3100)


def test_tables_grow_fill_calculated_columns_and_rename_columns_everywhere():
    data = workbook(staff)
    grown = edit(data, change(range='A5', values=[['Dũng', '1100']]), change(range='D1', values=[['Ghi chú'], ['ok']]))
    table = xml(grown.data, 'xl/tables/table1.xml')
    assert 'ref="A1:D5"' in table and '<autoFilter ref="A1:D5"/>' in table and 'name="Ghi chú"' in table
    assert re.search(r'<c r="C5"[^>]*><f>\[\[#This Row\],Lương\]\*10%</f></c>', xml(grown.data, 'xl/worksheets/sheet1.xml'))
    assert '\'Lương\'!A1:D5: Bảng "NhanVien" nới ra để gồm ô vừa ghi' in grown.lines
    renamed = edit(data, change(range='B1', values=[['Lương CB']]))
    sheet = xml(renamed.data, 'xl/worksheets/sheet1.xml')
    assert 'SUM(NhanVien[Lương CB])' in sheet and '[[#This Row],[Lương CB]]*10%' in sheet
    assert 'name="Lương CB"' in xml(renamed.data, 'xl/tables/table1.xml')
    for raw, message in (('Tên', 'trùng tên cột'), ('=1+1', 'cần là chữ')):
        with pytest.raises(EditError, match=message):
            edit(data, change(range='B1', values=[[raw]]))
    with pytest.raises(EditError, match='Peto chưa chèn/xóa cột giữa một Bảng'):
        edit(data, change('insert_columns', range='B'))
    with pytest.raises(EditError, match='hàng tiêu đề của Bảng'):
        edit(data, change('delete_rows', range='1'))


# ---------- định dạng ----------

def test_formats_create_new_styles_and_reuse_identical_ones():
    data = workbook(salary)
    result = edit(data, change('format', range='A1:D1', bold=True, fill_color='#FFF2CC', align='center'),
                  change('format', range='B2:B4', number_format='percent', decimals=1, font_color='#C00000', italic=True),
                  change('format', range='F7', fill_color='#FFF2CC', bold=True))
    styles = xml(result.data, 'xl/styles.xml')
    assert styles.count('rgb="FFFFF2CC"') == 1 and 'formatCode="0.0%"' in styles and 'horizontal="center"' in styles
    sheet = xml(result.data, 'xl/worksheets/sheet1.xml')
    cells = dict(re.findall(r'<c r="([A-Z]+\d+)" s="(\d+)"', sheet))
    assert cells['A1'] == cells['B1'] == cells['D1'] and 'F7' in cells
    assert 'Hàng 2 | A: An | B: 1000000000%' in read(result.data)
    assert result.lines[0] == "'Lương'!A1:D1: in đậm, nền #FFF2CC, căn giữa"
    with pytest.raises(EditError, match='#RRGGBB'):
        edit(data, change('format', range='A1', fill_color='vàng'))
    with pytest.raises(EditError, match='decimals cần đi cùng number_format'):
        edit(data, change('format', range='A1', decimals=2))


# ---------- chèn, xóa hàng cột ----------

def layout(book):
    sheet = book.add_worksheet('Lương')
    head = book.add_format({'bold': True})
    sheet.write_row(0, 0, ['Tháng', 'Bắc', 'Nam'], head)
    for row, (month, north, south) in enumerate([('T1', 120, 90), ('T2', 135, 95), ('T3', 150, 110)], start=1):
        sheet.write_row(row, 0, [month, north, south])
    sheet.write_formula('B5', '=SUM(B2:B4)', head, 405)
    sheet.write_formula('C5', '=SUM(C2:C4)', head, 295)
    sheet.set_row(2, 30)
    sheet.set_column('B:B', 18)
    sheet.write_comment('B3', 'Kiểm tra số tháng 2', {'author': 'An'})
    sheet.merge_range('A7:C7', 'Ghi chú cuối bảng')
    sheet.conditional_format('B2:C4', {'type': 'cell', 'criteria': '>', 'value': 130, 'format': book.add_format({'bold': True})})
    sheet.conditional_format('B2:B4', {'type': 'data_bar', 'bar_solid': True})
    sheet.data_validation('A2:A4', {'validate': 'list', 'source': ['T1', 'T2', 'T3']})
    sheet.write_url('A8', "internal:'Lương'!B4", string='Tới T3')
    sheet.add_sparkline('D2', {'range': "'Lương'!B2:C2"})
    sheet.autofilter('A1:C4')
    chart = book.add_chart({'type': 'column'})
    chart.add_series({'name': "='Lương'!$B$1", 'categories': "='Lương'!$A$2:$A$4", 'values': "='Lương'!$B$2:$B$4"})
    sheet.insert_chart('E2', chart)
    sheet.print_area('A1:C8')
    book.define_name('Bac', "='Lương'!$B$2:$B$4")
    other = book.add_worksheet('Tổng')
    other.write_formula('A1', "='Lương'!B5+'Lương'!B3", None, 540)


def test_insert_rows_moves_cells_and_everything_that_points_at_them():
    result = edit(workbook(layout), change('insert_rows', range='3:4'))
    sheet = xml(result.data, 'xl/worksheets/sheet1.xml')
    for expected in ('<f>SUM(B2:B6)</f>', 'ref="A9:C9"', 'sqref="B2:C6"', 'sqref="B2:B6"', 'sqref="A2:A6"',
                     '<hyperlink ref="A10" location="\'Lương\'!B6"', '<xm:sqref>B2:B6</xm:sqref>', '<autoFilter ref="A1:C6"/>',
                     '<xm:f>\'Lương\'!B2:C2</xm:f>'):
        assert expected in sheet, expected
    # Hàng mới theo định dạng hàng ngay trên (hàng 2), hàng cao 30 (hàng 3 cũ) dời xuống hàng 5.
    assert re.search(r'<row r="5"[^>]*ht="30"', sheet)
    workbook_xml = xml(result.data, 'xl/workbook.xml')
    assert "Lương'!$B$2:$B$6" in workbook_xml and "Lương!$A$1:$C$10" in workbook_xml
    assert "'Lương'!B7+'Lương'!B5" in xml(result.data, 'xl/worksheets/sheet2.xml')
    chart = xml(result.data, 'xl/charts/chart1.xml')
    assert "'Lương'!$B$2:$B$6" in chart and "'Lương'!$A$2:$A$6" in chart
    assert 'ref="B5"' in xml(result.data, 'xl/comments1.xml')
    vml = xml(result.data, 'xl/drawings/vmlDrawing1.vml')
    assert '<x:Row>4</x:Row>' in vml
    drawing = xml(result.data, 'xl/drawings/drawing1.xml')
    assert '<xdr:row>1</xdr:row>' in drawing and '<xdr:row>16</xdr:row>' in drawing, 'biểu đồ giãn theo hai hàng chèn'
    text = read(result.data)
    assert 'Hàng 7 | B: 405 | C: 295' in text and 'Ghi chú B5 · An: Kiểm tra số tháng 2' in text
    assert result.lines == ["'Lương'!3:4: chèn 2 hàng trống (theo định dạng hàng 2)"]


def test_delete_rows_turns_dead_references_into_ref_errors_and_drops_dead_parts():
    result = edit(workbook(layout), change('delete_rows', range='2:4'))
    sheet = xml(result.data, 'xl/worksheets/sheet1.xml')
    assert '<f>SUM(#REF!)</f>' in sheet and 'sqref="B2:C4"' not in sheet and '<dataValidation ' not in sheet
    assert 'mergeCell ref="A4:C4"' in sheet and '<x14:sparkline>' not in sheet
    assert "'Lương'!#REF!" in xml(result.data, 'xl/charts/chart1.xml')
    assert '<comment ' not in xml(result.data, 'xl/comments1.xml')
    assert 'ObjectType="Note"' not in xml(result.data, 'xl/drawings/vmlDrawing1.vml')
    assert any('thành #REF!' in note for note in result.notes)
    for name, data in parts(result.data).items():
        if name.endswith(('.xml', '.rels', '.vml')):
            etree.fromstring(data)


def test_insert_and_delete_columns_shift_columns_widths_and_formats():
    inserted = edit(workbook(layout), change('insert_columns', range='C'))
    sheet = xml(inserted.data, 'xl/worksheets/sheet1.xml')
    assert '<f>SUM(D2:D4)</f>' in sheet and 'ref="A7:D7"' in sheet and 'sqref="B2:D4"' in sheet
    assert re.search(r'<col min="2" max="2" width="18[^"]*"[^>]*/><col min="3" max="3" width="18', sheet)
    assert re.search(r'<c r="C1" s="1"/>', sheet), 'cột mới theo định dạng cột bên trái'
    removed = edit(workbook(layout), change('delete_columns', range='B'))
    sheet = xml(removed.data, 'xl/worksheets/sheet1.xml')
    assert '<f>SUM(B2:B4)</f>' in sheet and '<c r="C5"' not in sheet and 'ref="A7:B7"' in sheet
    assert "'Lương'!#REF!" in xml(removed.data, 'xl/charts/chart1.xml')


def test_threaded_comments_pivot_tables_and_their_sources_follow_shifts():
    data = pivot_book()
    text = read(data)
    assert 'Bình luận B2 · Nguyễn An, 2026-09-30: Số này đúng chưa? ↳ Trần Bình: Đúng rồi.' in text
    assert '[Threaded comment]' not in text
    assert ('Bảng tổng hợp "DoanhThu" ở A3:B6 (nguồn \'Dữ liệu\'!A1:C5): hàng: Miền; giá trị: Tổng Doanh thu '
            '(tổng của Doanh thu); lọc: Năm = 2026') in text
    result = edit(data, change('insert_rows', sheet='Dữ liệu', range='2'))
    assert 'ref="B3"' in xml(result.data, 'xl/threadedComments/threadedComment1.xml')
    assert 'ref="A1:C6"' in xml(result.data, 'xl/pivotCache/pivotCacheDefinition1.xml')
    with pytest.raises(EditError, match='bảng tổng hợp "DoanhThu"'):
        edit(data, change('insert_rows', sheet='Tổng hợp', range='4'))
    with pytest.raises(EditError, match='bảng tổng hợp "DoanhThu"'):
        edit(data, change(sheet='Tổng hợp', range='B4', values=[['1']]))
    moved = edit(data, change('insert_rows', sheet='Tổng hợp', range='1'))
    assert 'ref="A4:B7"' in xml(moved.data, 'xl/pivotTables/pivotTable1.xml')
    renamed = edit(data, change('rename_sheet', sheet='Dữ liệu', new_name='Số liệu'))
    assert 'sheet="Số liệu"' in xml(renamed.data, 'xl/pivotCache/pivotCacheDefinition1.xml')


def pivot_book() -> bytes:
    threaded = 'http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments'
    rows = ('<row r="1"><c r="A1" t="inlineStr"><is><t>Miền</t></is></c><c r="B1" t="inlineStr"><is><t>Doanh thu</t></is>'
            '</c><c r="C1" t="inlineStr"><is><t>Năm</t></is></c></row>'
            + ''.join(f'<row r="{r}"><c r="A{r}" t="inlineStr"><is><t>{"Bắc" if r % 2 else "Nam"}</t></is></c>'
                      f'<c r="B{r}"><v>{r * 10}</v></c><c r="C{r}"><v>2026</v></c></row>' for r in range(2, 6)))
    pivot_rows = ('<row r="3"><c r="A3" t="inlineStr"><is><t>Miền</t></is></c><c r="B3" t="inlineStr"><is><t>Tổng Doanh '
                  'thu</t></is></c></row><row r="4"><c r="A4" t="inlineStr"><is><t>Bắc</t></is></c><c r="B4"><v>80</v>'
                  '</c></row>')
    return minimal(rows, sheets='<sheet name="Tổng hợp" sheetId="2" r:id="rId2"/>',
                   workbook_extra='<pivotCaches><pivotCache cacheId="1" r:id="rId3"/></pivotCaches>',
                   workbook_rels=(f'<Relationship Id="rId2" Type="{REL}/worksheet" Target="worksheets/sheet2.xml"/>'
                                  f'<Relationship Id="rId3" Type="{REL}/pivotCacheDefinition" '
                                  'Target="pivotCache/pivotCacheDefinition1.xml"/>'
                                  '<Relationship Id="rId4" Type="http://schemas.microsoft.com/office/2017/10/'
                                  'relationships/person" Target="persons/person.xml"/>'),
                   sheet_rels=('<Relationship Id="t1" Type="http://schemas.microsoft.com/office/2017/10/relationships/'
                               'threadedComment" Target="../threadedComments/threadedComment1.xml"/>'
                               f'<Relationship Id="c1" Type="{REL}/comments" Target="../comments1.xml"/>'),
                   extra={
                       'xl/worksheets/sheet2.xml': f'<worksheet xmlns="{MAIN}"><sheetData>{pivot_rows}</sheetData></worksheet>',
                       'xl/worksheets/_rels/sheet2.xml.rels': (f'<Relationships xmlns="{PKG}"><Relationship Id="p1" '
                                                               f'Type="{REL}/pivotTable" Target="../pivotTables/pivotTable1.xml"/>'
                                                               '</Relationships>'),
                       'xl/pivotTables/pivotTable1.xml': (
                           f'<pivotTableDefinition xmlns="{MAIN}" name="DoanhThu" cacheId="1"><location ref="A3:B6" '
                           'firstHeaderRow="1" firstDataRow="1" firstDataCol="1"/><pivotFields count="3"><pivotField '
                           'axis="axisRow"><items count="3"><item x="0"/><item x="1"/><item t="default"/></items>'
                           '</pivotField><pivotField dataField="1"/><pivotField axis="axisPage"><items count="2">'
                           '<item x="0"/><item x="1"/></items></pivotField></pivotFields><rowFields count="1"><field x="0"/>'
                           '</rowFields><pageFields count="1"><pageField fld="2" item="1"/></pageFields><dataFields '
                           'count="1"><dataField name="Tổng Doanh thu" fld="1"/></dataFields></pivotTableDefinition>'),
                       'xl/pivotTables/_rels/pivotTable1.xml.rels': (
                           f'<Relationships xmlns="{PKG}"><Relationship Id="r1" Type="{REL}/pivotCacheDefinition" '
                           'Target="../pivotCache/pivotCacheDefinition1.xml"/></Relationships>'),
                       'xl/pivotCache/pivotCacheDefinition1.xml': (
                           f'<pivotCacheDefinition xmlns="{MAIN}" recordCount="4"><cacheSource type="worksheet">'
                           '<worksheetSource ref="A1:C5" sheet="Dữ liệu"/></cacheSource><cacheFields count="3"><cacheField '
                           'name="Miền"><sharedItems count="2"><s v="Bắc"/><s v="Nam"/></sharedItems></cacheField>'
                           '<cacheField name="Doanh thu"><sharedItems containsNumber="1"/></cacheField><cacheField '
                           'name="Năm"><sharedItems count="2"><n v="2025"/><n v="2026"/></sharedItems></cacheField>'
                           '</cacheFields></pivotCacheDefinition>'),
                       'xl/threadedComments/threadedComment1.xml': (
                           f'<ThreadedComments xmlns="{threaded}"><threadedComment ref="B2" dT="2026-09-30T10:00:00.00" '
                           'personId="{P1}" id="{T1}"><text>Số này đúng chưa?</text></threadedComment><threadedComment '
                           'ref="B2" dT="2026-09-30T11:00:00.00" personId="{P2}" id="{T2}" parentId="{T1}"><text>Đúng '
                           'rồi.</text></threadedComment></ThreadedComments>'),
                       'xl/persons/person.xml': (f'<personList xmlns="{threaded}"><person displayName="Nguyễn An" '
                                                 'id="{P1}"/><person displayName="Trần Bình" id="{P2}"/></personList>'),
                       'xl/comments1.xml': (f'<comments xmlns="{MAIN}"><authors><author>tc={{T1}}</author></authors>'
                                            '<commentList><comment ref="B2" authorId="0"><text><t>[Threaded comment] Bản '
                                            'Excel của bạn…</t></text></comment></commentList></comments>'),
                   })


# ---------- trang tính ----------

def test_add_and_rename_sheets_update_every_reference():
    result = edit(workbook(layout), change('add_sheet', sheet='Tổng hợp'),
                  change(sheet='Tổng hợp', range='A1', values=[['Bắc', "='Lương'!B5*2"]]))
    text = read(result.data)
    assert '[Trang tính 3/3 "Tổng hợp"' in text and 'Hàng 1 | A: Bắc | B: 810' in text
    content_types = xml(result.data, '[Content_Types].xml')
    assert '/xl/worksheets/sheet3.xml' in content_types
    renamed = edit(workbook(layout), change('rename_sheet', sheet='Lương', new_name='Thu nhập 2026'))
    assert "'Thu nhập 2026'!B5+'Thu nhập 2026'!B3" in xml(renamed.data, 'xl/worksheets/sheet2.xml')
    assert "'Thu nhập 2026'!$B$2:$B$4" in xml(renamed.data, 'xl/workbook.xml')
    assert "'Thu nhập 2026'!$B$2:$B$4" in xml(renamed.data, 'xl/charts/chart1.xml')
    assert "location=\"'Thu nhập 2026'!B4\"" in xml(renamed.data, 'xl/worksheets/sheet1.xml')
    assert '<vt:lpstr>Thu nhập 2026</vt:lpstr>' in xml(renamed.data, 'docProps/app.xml')
    for name, message in (('Tổng', 'đã có trang'), ('a/b', 'không hợp lệ'), ('x' * 32, 'không hợp lệ'),
                          ('History', 'History')):
        with pytest.raises(EditError, match=message):
            edit(workbook(layout), change('rename_sheet', new_name=name))


# ---------- tệp macro, tệp hỏng, giới hạn ----------

def test_macro_workbooks_keep_their_vba_project_byte_for_byte():
    vba = bytes(range(256)) * 40
    data = minimal('<row r="1"><c r="A1"><v>1</v></c></row>',
                   content='<Override PartName="/xl/workbook.xml" ContentType="application/vnd.ms-excel.sheet.'
                           'macroEnabled.main+xml"/><Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/>',
                   workbook_rels=('<Relationship Id="rIdV" Type="http://schemas.microsoft.com/office/2006/relationships/'
                                  'vbaProject" Target="vbaProject.bin"/>'),
                   extra={'xl/vbaProject.bin': vba})
    result = edit(data, change(sheet='Dữ liệu', range='A2', values=[['2']]))
    assert parts(result.data)['xl/vbaProject.bin'] == vba


def test_broken_locked_and_oversized_files_are_refused(monkeypatch):
    with pytest.raises(EditError, match='mật khẩu'):
        edit(workbook_reader.CFB_MAGIC + b'\0' * 600, change(range='A1', values=[['1']]))
    with pytest.raises(EditError, match='không phải Excel'):
        edit(b'not a zip', change(range='A1', values=[['1']]))
    dtd = minimal('<row r="1"><c r="A1"><v>1</v></c></row>')
    with pytest.raises(EditError, match='DTD'):
        edit(build_package({**parts(dtd), 'xl/workbook.xml': b'<!DOCTYPE x [<!ENTITY a "b">]>' + parts(dtd)['xl/workbook.xml']}),
             change(sheet='Dữ liệu', range='A1', values=[['1']]))
    monkeypatch.setattr(book_module, 'MAX_EDIT_CELLS', 5)
    with pytest.raises(EditError, match='lớn quá'):
        edit(workbook(salary), change(range='A1', values=[['x']]))
    monkeypatch.setattr(ops, 'MAX_CELLS', 3)
    monkeypatch.setattr(book_module, 'MAX_EDIT_CELLS', 250_000)
    with pytest.raises(EditError, match='tối đa 3 ô'):
        edit(workbook(salary), change('fill', range='F1:F4', value='1'))


def test_change_errors_name_the_change_and_write_nothing():
    data = workbook(salary)
    with pytest.raises(EditError, match=r'^Thay đổi 2 \(set \'Lương\' Z9\): ô Z9: "1,5"'):
        edit(data, change(range='E1', values=[['ok']]), change(range='Z9', values=[['1,5']]))
    with pytest.raises(EditError, match='Không có trang tính "Không có"'):
        edit(data, change(sheet='Không có', range='A1', values=[['1']]))
    with pytest.raises(EditError, match='set dùng values'):
        edit(data, change(range='A1', values=[['1']], value='2'))
    with pytest.raises(EditError, match='insert_rows không dùng values'):
        edit(data, change('insert_rows', range='2', values=[['1']]))


def test_every_refused_change_is_listed_at_once():
    """Trước đây mỗi lần gọi chỉ biết lỗi đầu tiên: bảng nhiều lỗi tốn một vòng cho mỗi lỗi rồi hết giờ."""
    def build(book):
        sheet = book.add_worksheet('Lương')
        sheet.merge_range('A1:C1', 'Tiêu đề')
    data = workbook(build)
    with pytest.raises(EditError) as refused:
        edit(data, change(range='B1', values=[['x']]), change(range='D2', values=[['5']]),
             change(range='E2', values=[['2.000.000']]), change('unmerge', range='Z1'))
    lines = str(refused.value).splitlines()
    assert lines[0].startswith("Thay đổi 1 (set 'Lương' B1): ô B1 nằm trong vùng gộp A1:C1")
    assert 'bỏ gộp (unmerge)' in lines[0]
    assert lines[1].startswith("Thay đổi 3 (set 'Lương' E2)") and len(lines) == 2
    with pytest.raises(EditError) as broken:
        edit(workbook(salary), change('fill', range='E2:E3', value='=B2/0'), change(range='F2', values=[['=1/0']]))
    text = str(broken.value)
    assert "'Lương'!E2 (=B2/0) ra #DIV/0!" in text and "'Lương'!E3 (=B3/0)" in text and "'Lương'!F2 (=1/0)" in text


def test_merge_and_unmerge_cells():
    def build(book):
        sheet = book.add_worksheet('Lương')
        sheet.merge_range('A1:C1', 'Tiêu đề')
        sheet.merge_range('E1:F1', 'Gộp nhầm')
        sheet.write('A3', 'Tên')
        sheet.write('B3', 'Ghi chú')
    data = workbook(build)
    result = edit(data, change('unmerge', range='E1:F1'), change(range='F1', values=[['6']]),
                  change('merge', range='A5:D5'), change('merge', range='A1:D1'))
    sheet = xml(result.data, 'xl/worksheets/sheet1.xml')
    merges = re.findall(r'<mergeCell ref="([^"]+)"/>', sheet)
    assert merges == ['A5:D5', 'A1:D1'] and '<mergeCells count="2">' in sheet
    assert result.lines[0] == "'Lương'!E1:F1: bỏ gộp ô, các ô tách riêng (giá trị ở E1)"
    assert "'Lương'!A1:D1: gộp thành một ô (thay cho vùng gộp A1:C1)" in result.lines
    assert [0, 0, 0, 5] == list(result.changed['Lương'][0])
    assert 'F: 6' in read(result.data)
    # Excel chỉ giữ ô đầu khi gộp: không lặng lẽ xóa chữ của người dùng; chạm một phần vùng gộp thì phải bỏ gộp trước.
    with pytest.raises(EditError, match='B3 đang có dữ liệu'):
        edit(data, change('merge', range='A3:B3'))
    with pytest.raises(EditError, match='chạm một phần vùng gộp A1:C1'):
        edit(data, change('merge', range='B1:D1'))
    with pytest.raises(EditError, match='từ hai ô trở lên'):
        edit(data, change('merge', range='A7'))
    with pytest.raises(EditError, match='merge không dùng values'):
        edit(data, change('merge', range='A7:B7', values=[['x']]))
    # Bỏ hết vùng gộp thì bỏ luôn thẻ mergeCells (rỗng là sai lược đồ, Excel báo hỏng tệp).
    plain = edit(data, change('unmerge', range='A1:F1'))
    assert '<mergeCells' not in xml(plain.data, 'xl/worksheets/sheet1.xml') and len(plain.lines) == 2
    assert edit(data, change('unmerge', range='A9')).notes == ["'Lương'!A9 không có ô gộp nào nên unmerge không đổi gì."]


def test_first_merge_goes_where_the_schema_wants_it():
    data = minimal('<row r="1"><c r="A1"><v>1</v></c></row>',
                   sheet_extra='<autoFilter ref="A1:B1"/><pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" '
                               'header="0.3" footer="0.3"/>')
    sheet = xml(edit(data, change('merge', sheet='Dữ liệu', range='A3:B3')).data, 'xl/worksheets/sheet1.xml')
    assert '<autoFilter ref="A1:B1"/><mergeCells count="1"><mergeCell ref="A3:B3"/></mergeCells><pageMargins' in sheet
    assert 'ns0' not in sheet
    etree.fromstring(sheet.encode())


def test_reference_scanner_handles_quoted_sheets_structured_names_and_strings():
    found = refs.scan("SUM('Bảng 1'!$B$2:B9)+Bang1[[#This Row],[Q1]]+\"C3\"+[1]Ngoài!A1+Tên_vùng+LOG10(A1)")
    texts = [(ref.sheet, ref.kind, ref.external) for ref in found.refs]
    assert texts == [('Bảng 1', 'area', False), ('Ngoài', 'cell', True), (None, 'cell', False)]
    assert [name.name for name in found.names] == ['Tên_vùng'] and found.structured and 'LOG10' in found.functions
    shifted = refs.rewrite('SUM(B2:B10)+B12+B3', refs.shifter('S', 'S', 'row', 4, 2, False))
    assert shifted == 'SUM(B2:B12)+B14+B3'
    assert refs.rewrite('B5+SUM(B4:B6)', refs.shifter('S', 'S', 'row', 3, 3, True)) == '#REF!+SUM(#REF!)'
    with pytest.raises(refs.Unsupported):
        refs.rewrite('SUM(A:B!C1)+SUM(S1:S3!A1)', refs.shifter('S2', 'S2', 'row', 0, 1, False, ['S1', 'S2', 'S3']))


# ---------- trong chat ----------

def upload(name: str, data: bytes, mime: str = workbook_reader.XLSX_MIME) -> dict:
    import base64
    return {'name': name, 'mime': mime, 'data': base64.b64encode(data).decode()}


async def test_chat_edits_an_upload_and_then_its_latest_version(client, monkeypatch):
    from conftest import TEST_OWNER, read_events
    import storage as db
    from features.chat import service as chat_service
    from shared.attachment_tools import AttachmentFiles

    events = await read_events(await client.post('/api/chat', json={
        'message': 'Đây là bảng lương', 'attachments': [upload('Bảng lương.xlsx', workbook(salary))]}))
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    events = await read_events(await client.post('/api/chat', json={'message': '__suaexcel__', 'conversation_id': conversation}))
    assert events[-1]['type'] == 'done', events
    first = next(event['artifact'] for event in events if event['type'] == 'artifact')
    assert first['style'] == 'workbook' and first['filename'] == 'Bảng lương.xlsx' and first['version'] == 1
    base = f"/api/documents/{first['id']}"
    grid = (await client.get(base + '/sheet?version=1')).json()
    sheet = grid['sheets'][0]
    assert grid['kind'] == 'workbook' and sheet['name'] == 'Lương' and [0, 4, 4, 4] in sheet['changed']
    cells = {(row, col): item for row, col, item in sheet['cells']}
    assert cells[(0, 4)]['d'] == 'Ghi chú Peto' and cells[(1, 1)]['d'] == '10.000.000 ₫'
    assert grid['styles'][cells[(0, 4)]['s']]['f'] == '#FFF2CC' and cells[(1, 3)]['f'] == '=B2+C2'
    download = await client.get(base + '/export/xlsx?version=1')
    assert download.headers['content-type'] == workbook_reader.XLSX_MIME
    assert quote('Bảng lương') + '-v1.xlsx' in download.headers['content-disposition']
    assert 'E: Ghi chú Peto' in read(download.content)
    events = await read_events(await client.post('/api/chat', json={'message': '__suaexcel__', 'conversation_id': conversation}))
    second = next(event['artifact'] for event in events if event['type'] == 'artifact')
    assert second['id'] == first['id'] and second['version'] == 2
    latest = await client.get(base + '/export/xlsx?version=2')
    assert 'E: Ghi chú Peto | F: Ghi chú Peto' in read(latest.content), 'lần sửa sau dựa trên bản mới nhất'
    rows = await db.get_messages(TEST_OWNER, conversation)
    found = await AttachmentFiles(rows, TEST_OWNER).run('search_attachment', json.dumps(
        {'file': 'Bảng lương.xlsx', 'query': 'ghi chu peto', 'context_lines': 0}))
    assert found['matches'] == 1 and 'F: Ghi chú Peto' in found['text']
    seen = []

    class FollowUp:
        async def stream(self, **kwargs):
            seen.extend(kwargs['messages'])
            yield 'Đã xem bản sửa.'
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': FollowUp())
    await read_events(await client.post('/api/chat', json={'message': 'Bản mới có gì?', 'conversation_id': conversation}))
    excerpts = [item.text_excerpt for message in seen for item in message.attachments if item.name == 'Bảng lương.xlsx']
    assert any('Bản Peto đã sửa của tệp "Bảng lương.xlsx"' in text and "Ô đã sửa: 'Lương'!F1:F5" in text for text in excerpts)


async def test_macro_workbooks_download_as_xlsm(client):
    from conftest import read_events
    data = minimal('<row r="1"><c r="A1" t="inlineStr"><is><t>Tên</t></is></c></row><row r="2"><c r="A2"><v>1</v></c></row>',
                   content='<Override PartName="/xl/workbook.xml" ContentType="application/vnd.ms-excel.sheet.'
                           'macroEnabled.main+xml"/>',
                   workbook_rels=('<Relationship Id="rIdV" Type="http://schemas.microsoft.com/office/2006/relationships/'
                                  'vbaProject" Target="vbaProject.bin"/>'),
                   extra={'xl/vbaProject.bin': b'\xd0\xcfmacro'})
    events = await read_events(await client.post('/api/chat', json={
        'message': 'Tệp có macro', 'attachments': [upload('Có macro.xlsm', data, workbook_reader.XLSM_MIME)]}))
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    events = await read_events(await client.post('/api/chat', json={'message': '__suaexcel__', 'conversation_id': conversation}))
    artifact = next((event['artifact'] for event in events if event['type'] == 'artifact'), None)
    assert artifact, events
    assert artifact['filename'] == 'Có macro.xlsm'
    download = await client.get(f"/api/documents/{artifact['id']}/export/xlsx?version=1")
    assert download.headers['content-type'] == 'application/vnd.ms-excel.sheet.macroEnabled.12'
    assert download.headers['content-disposition'].endswith('-v1.xlsm')
    assert parts(download.content)['xl/vbaProject.bin'] == b'\xd0\xcfmacro'


async def test_provider_offers_the_edit_tool_only_with_a_workbook(client, monkeypatch):
    from types import SimpleNamespace
    import storage as db
    from ai.base import ChatMessage
    from conftest import TEST_OWNER
    from features.documents.tools import DocumentSession, current_session
    from test_clock_tools import FakeStream, done, fake_provider

    provider, requests = fake_provider(monkeypatch, [
        FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Ừ.'), done()]),
        FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Ừ.'), done()])])
    conversation = await db.create_conversation(TEST_OWNER, 'Không có tệp')
    for rows, expected in (([], False), ([{'attachments': [{'kind': 'file', 'mime': workbook_reader.XLSX_MIME,
                                                             'path': 'x.xlsx', 'filename': 'x.xlsx'}]}], True)):
        token = current_session.set(DocumentSession(TEST_OWNER, conversation, rows))
        try:
            [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Sửa giúp')])]
        finally:
            current_session.reset(token)
        assert any(tool.get('name') == 'edit_spreadsheet' for tool in requests[-1]['tools']) is expected

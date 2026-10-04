"""Bảng tính Excel (create_spreadsheet): đọc công thức, tính như Excel, kiểm tra đầu vào, tệp XLSX và lưới xem trong chat."""
import json
import re
import zipfile
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest

import storage as db
from ai.base import ChatMessage, StreamChunk
from ai.mock import sheet_sample
from features.chat import conversations as conversation_actions
from features.chat import service as chat_service
from features.documents.sheets import engine, spec, view, xlsx_out
from features.documents.sheets.formula import FUNCTIONS, FormulaError, parse
from features.documents.tools import DocumentSession, current_session
from conftest import TEST_OWNER, read_events

TODAY = date(2026, 10, 4)


def column(header, format='text', decimals=None):
    return {'header': header, 'format': format, 'decimals': decimals}


def sheet(name, columns, rows, total=None, charts=None, title=None):
    return {'name': name, 'title': title, 'columns': columns, 'rows': rows, 'total_row': total, 'charts': charts or []}


def build(*sheets, title='Bảng thử'):
    book = spec.normalize(spec.WorkbookInput.model_validate({'title': title, 'sheets': list(sheets)}))
    return spec.prepare(book, TODAY)


DATA = sheet('Dữ liệu', [column('Tên'), column('Điểm', 'number'), column('Lớp'), column('Ngày', 'date')], [
    ['An', '8', '10A', '2026-09-05'], ['Bình', '6.5', '10B', '2026-09-12'], ['Chi', '9', '10A', '2026-10-01'],
    ['Dũng', '', '10B', ''], ['Em', 'Vắng', '10A', '']])
LEVELS = sheet('Ngưỡng', [column('Từ điểm', 'number'), column('Xếp loại')],
               [['0', 'Yếu'], ['5', 'Trung bình'], ['6.5', 'Khá'], ['8', 'Giỏi']])


def calc(formula):
    """Kết quả của một công thức đặt ở ô A2 trang Tính, cạnh hai trang dữ liệu mẫu."""
    prepared = build(DATA, LEVELS, sheet('Tính', [column('Kết quả')], [[formula]]))
    return prepared.value(2, 1, 0)


def fails(formula) -> str:
    with pytest.raises(ValueError) as caught:
        calc(formula)
    return str(caught.value)


# ---------- đọc công thức ----------
def test_formulas_are_normalized_to_what_excel_reads():
    assert parse('=round((c2+d2*2+e2*3)/6, 1)').text == '=ROUND((C2+D2*2+E2*3)/6,1)'
    assert parse('=IF(A1>=5;"Đạt";"Trượt")').text == '=IF(A1>=5,"Đạt","Trượt")'
    assert parse("=SUM('Bảng điểm'!$G$2:G11)").text == "=SUM('Bảng điểm'!$G$2:G11)"
    assert parse('=COUNTIF(B2:B9, “Đạt”)').text == '=COUNTIF(B2:B9,"Đạt")'
    assert parse('=SUM(Sheet1!A:A)').refs[0].r1 is None


@pytest.mark.parametrize('source, message', [
    ('=SUM(A1;A2,A3)', 'không trộn dấu chấm phẩy'),
    ('=XLOOKUP(A1,B:B,C:C)', 'hàm XLOOKUP chưa được hỗ trợ'),
    ('=ROUND(A1)', 'ROUND cần 2 tham số'),
    ('=SUMIFS(A1:A5,B1:B5,">1",C1:C5)', 'cặp'),
    ("=Bảng điểm!A1", 'nháy đơn'),
    ('=SUM(A1', 'thiếu'),
    ('=A1 B1', 'thừa'),
    ('=tong', 'tên vùng'),
])
def test_bad_formulas_explain_what_to_fix(source, message):
    with pytest.raises(FormulaError, match=re.escape(message)):
        parse(source)


def test_every_function_has_an_implementation():
    special = {'IF', 'IFERROR', 'ISERROR', 'CHOOSE'}
    assert all(name in special or hasattr(engine.Evaluator, 'f_' + name) for name in FUNCTIONS)


# ---------- tính như Excel ----------
@pytest.mark.parametrize('formula, expected', [
    ("=SUM('Dữ liệu'!B2:B6)", 23.5),
    ("=AVERAGE('Dữ liệu'!B:B)", 23.5 / 3),
    ("=COUNT('Dữ liệu'!B2:B6)", 3),
    ("=COUNTA('Dữ liệu'!B2:B6)", 4),
    ("=COUNTBLANK('Dữ liệu'!B2:B6)", 1),
    ("=COUNTIF('Dữ liệu'!C2:C6,\"10a\")", 3),
    ("=COUNTIF('Dữ liệu'!B2:B6,\">=8\")", 2),
    ("=COUNTIF('Dữ liệu'!A2:A6,\"B*\")", 1),
    ("=SUMIF('Dữ liệu'!C2:C6,\"10A\",'Dữ liệu'!B2:B6)", 17),
    ("=SUMIFS('Dữ liệu'!B2:B6,'Dữ liệu'!C2:C6,\"10A\",'Dữ liệu'!B2:B6,\">8\")", 9),
    ("=AVERAGEIF('Dữ liệu'!C2:C6,\"10B\",'Dữ liệu'!B2:B6)", 6.5),
    ("=COUNTIFS('Dữ liệu'!C2:C6,\"10A\",'Dữ liệu'!B2:B6,\"<>\")", 3),
    ("=VLOOKUP(\"chi\",'Dữ liệu'!A2:C6,2,FALSE)", 9),
    ("=IFERROR(VLOOKUP(\"Zed\",'Dữ liệu'!A2:C6,2,FALSE),\"Không có\")", 'Không có'),
    ("=INDEX('Dữ liệu'!A2:A6,MATCH(9,'Dữ liệu'!B2:B6,0))", 'Chi'),
    ("=VLOOKUP(7.2,'Ngưỡng'!A2:B5,2)", 'Khá'),
    ("=VLOOKUP(8,'Ngưỡng'!A2:B5,2,TRUE)", 'Giỏi'),
    ("=MATCH(6,'Ngưỡng'!A2:A5)", 2),
    ('=ROUND(2.675,2)', 2.68), ('=ROUND(-2.5,0)', -3), ('=ROUNDUP(3.21,1)', 3.3), ('=ROUNDDOWN(-3.29,1)', -3.2),
    ('=ROUND(1234.5,-2)', 1200), ('=INT(-2.5)', -3), ('=MOD(-1,3)', 2), ('=TRUNC(-2.7)', -2),
    ('=0.1+0.2=0.3', True), ('=-2^2', 4), ('=2^3^2', 64), ('=10%*50', 5), ('=10-2-3', 5),
    ("=\"Lớp \"&'Dữ liệu'!C2&\": \"&'Dữ liệu'!B2", 'Lớp 10A: 8'),
    ('=1/3&""', '0.333333333333333'),
    ("=IF('Dữ liệu'!B6>=5,\"Đạt\",\"Trượt\")", 'Đạt'),
    ("='Dữ liệu'!B5+1", 1),
    ("=AND('Dữ liệu'!B2>5,'Dữ liệu'!B3>5)", True), ('=OR(FALSE,0)', False), ('=NOT(0)', True),
    ('=LEFT("Nguyễn Văn A",6)', 'Nguyễn'), ('=UPPER("đạt")', 'ĐẠT'), ('=PROPER("nguyễn văn an")', 'Nguyễn Văn An'),
    ('=LEN("Giỏi")', 4), ('=TRIM("  a   b ")', 'a b'), ('=MID("Peto Web",6,3)', 'Web'), ('=RIGHT("10A1",2)', 'A1'),
    ('=SUBSTITUTE("a-b-c","-","+",2)', 'a-b+c'), ('=VALUE("12.5")', 12.5), ('=CONCATENATE("A",1,TRUE)', 'A1TRUE'),
    ('=DATE(2026,10,4)', 46299), ("=YEAR('Dữ liệu'!D2)", 2026), ("=MONTH('Dữ liệu'!D2)", 9), ("=DAY('Dữ liệu'!D2)", 5),
    ('=DATE(2026,13,1)', 46388), ('=DATEDIF(DATE(2008,5,20),DATE(2026,10,4),"Y")', 18), ('=TODAY()', 46299),
    ('=MEDIAN(1,3,2,4)', 2.5), ("=LARGE('Dữ liệu'!B2:B6,1)", 9), ("=SMALL('Dữ liệu'!B2:B6,1)", 6.5),
    ("=RANK(8,'Dữ liệu'!B2:B6)", 2), ("=RANK(8,'Dữ liệu'!B2:B6,1)", 2),
    ("=SUMPRODUCT('Dữ liệu'!B2:B4,'Dữ liệu'!B2:B4)", 187.25), ('=PRODUCT(2,3,4)', 24), ("=MAX('Dữ liệu'!B2:B6)", 9),
    ('=CHOOSE(2,"a","b","c")', 'b'), ("=ISBLANK('Dữ liệu'!B5)", True), ("=ISTEXT('Dữ liệu'!B6)", True),
    ("=ISNUMBER('Dữ liệu'!B6)", False), ('=ISERROR(1/0)', True),
])
def test_results_match_excel(formula, expected):
    value = calc(formula)
    if isinstance(expected, bool):
        assert value is expected
    elif isinstance(expected, str):
        assert value == expected
    else:
        assert value == pytest.approx(expected, rel=1e-12)


def test_money_functions():
    assert calc('=PMT(0.1/12,12,-10000000)') == pytest.approx(879158.8723, rel=1e-8)
    assert calc('=FV(0.05,10,0,-1000)') == pytest.approx(1628.894627, rel=1e-8)
    assert calc('=PV(0.05,10,0,1628.894627)') == pytest.approx(-1000, rel=1e-8)
    assert calc('=STDEV(2,4,4,4,5,5,7,9)') == pytest.approx(2.13808993, rel=1e-8)


@pytest.mark.parametrize('formula, message', [
    ('=1/0', '#DIV/0!'),
    ("=VLOOKUP(\"Zed\",'Dữ liệu'!A2:C6,2,FALSE)", 'không tìm thấy'),
    ("='Dữ liệu'!B6+1", '#VALUE!'),
    ("='Dữ liệu'!B2:B4*2", 'SUMPRODUCT'),
    ("=VLOOKUP(7,'Dữ liệu'!B2:C6,2)", 'thêm FALSE'),
    ('=A2+1', 'vòng tham chiếu'),
    ("='Dữ liệu'!B20", 'nằm ngoài bảng'),
    ("='Không có'!A1", "các trang: 'Dữ liệu', 'Ngưỡng', 'Tính'"),
])
def test_errors_name_the_cell_and_the_fix(formula, message):
    text = fails(formula)
    assert message in text and ('Tính!A2' in text or 'vòng' in text)


def test_long_chains_do_not_recurse():
    rows = [[str(row - 1), f'=B{row - 1}+A{row}' if row > 2 else '=A2'] for row in range(2, 302)]
    prepared = build(sheet('Cộng dồn', [column('Số', 'number'), column('Lũy kế', 'number')], rows))
    assert prepared.value(0, 300, 1) == sum(range(1, 301))


def test_whole_column_blank_counts_match_excel():
    prepared = build(DATA, sheet('Tính', [column('Kết quả', 'number')], [["=COUNTBLANK('Dữ liệu'!B:B)"],
                                                                           ["=COUNTIF('Dữ liệu'!B:B,\"\")"]]))
    assert prepared.value(1, 1, 0) == 1_048_576 - 5 == prepared.value(1, 2, 0)


# ---------- kiểm tra đầu vào ----------
@pytest.mark.parametrize('change, message', [
    (lambda data: data['sheets'][0]['rows'][1].pop(), 'hàng 3 (rows[1]) có 6 ô'),
    (lambda data: data['sheets'][0]['rows'][0].__setitem__(2, '7,5'), 'số dạng máy'),
    (lambda data: data['sheets'][1]['rows'][0].__setitem__(2, '0.3'), 'cột phần trăm viết dạng 8%'),
    (lambda data: data['sheets'][0].update(name='Bảng/điểm'), 'không được chứa'),
    (lambda data: data['sheets'][1].update(name='bảng điểm'), 'bị trùng'),
    (lambda data: data['sheets'][0].update(name='Một tên trang tính dài hơn ba mươi mốt ký tự'), '31 ký tự'),
    (lambda data: data['sheets'][1]['charts'][0].update(value_columns=['A']), 'không được trùng'),
    (lambda data: data['sheets'][1]['charts'][0].update(category_column='Z'), 'bảng có cột A–C'),
    (lambda data: data['sheets'][0]['rows'][0].__setitem__(5, '=ROUND(C2+D2,1'), 'công thức "=ROUND(C2+D2,1" sai'),
])
def test_input_errors_point_at_the_cell(change, message):
    data = sheet_sample('diem')
    change(data)
    with pytest.raises(ValueError, match=re.escape(message)):
        spec.prepare(spec.normalize(spec.WorkbookInput.model_validate(data)), TODAY)


def test_text_in_number_columns_stays_text_but_dates_must_be_iso():
    prepared = build(sheet('Điểm', [column('Tên'), column('Điểm', 'number')], [['An', 'Vắng'], ['Bình', '7']],
                           total=['Trung bình', '=AVERAGE(B2:B3)']))
    assert prepared.value(0, 1, 1) == 'Vắng' and prepared.value(0, 3, 1) == 7
    with pytest.raises(ValueError, match='YYYY-MM-DD'):
        build(sheet('Ngày', [column('Ngày', 'date')], [['04/10/2026']]))
    money = build(sheet('Tiền', [column('Khoản'), column('Số tiền', 'vnd')], [['Nhà', '3500000₫'], ['Ăn', '1200000 đ']]))
    assert money.value(0, 2, 1) == 1_200_000


def test_chart_sources_must_be_numbers_and_pies_small():
    rows = [[f'Học sinh {index}', str(index)] for index in range(1, 13)]
    pie = {'type': 'pie', 'title': 'Tỉ lệ', 'category_column': 'A', 'value_columns': ['B']}
    with pytest.raises(ValueError, match='bảng tổng hợp'):
        build(sheet('Lớp', [column('Tên'), column('Điểm', 'number')], rows, charts=[pie]))
    bar = {'type': 'bar', 'title': 'Điểm', 'category_column': 'A', 'value_columns': ['B']}
    with pytest.raises(ValueError, match='cột B phải là số'):
        build(sheet('Lớp', [column('Tên'), column('Điểm', 'number')], [['An', 'Vắng'], ['Bình', '7']], charts=[bar]))


def test_cell_budget_and_schema():
    rows = [[str(index)] * 20 for index in range(250)]
    with pytest.raises(ValueError, match='tối đa 4000'):
        spec.normalize(spec.WorkbookInput.model_validate({'title': 'Lớn', 'sheets': [
            sheet('Lớn', [column(f'Cột {index}', 'number') for index in range(20)], rows)]}))
    parameters = spec.SCHEMA['parameters']
    assert spec.SCHEMA['strict'] and set(parameters['required']) == set(parameters['properties'])
    item = parameters['properties']['sheets']['items']
    for schema in (item, spec.COLUMN_SCHEMA, spec.CHART_SCHEMA):
        assert set(schema['required']) == set(schema['properties'])
    assert 'Không bịa số liệu' in spec.SCHEMA['description'] and 'VLOOKUP' in spec.SCHEMA['description']


# ---------- hiển thị và tệp XLSX ----------
def test_vietnamese_display_and_excel_formats():
    prepared = build(*sheet_sample('chitieu')['sheets'])
    grid = view.grid(prepared)
    spend, groups = grid['sheets']
    assert [cell['d'] for cell in spend['rows'][0]] == ['01/10/2026', 'Tiền nhà tháng 10', 'Nhà ở', '3.500.000 ₫']
    assert spend['total'][3] == {'d': '5.770.000 ₫', 't': 'n', 'f': '=SUM(D2:D9)'}
    assert [row[2]['d'] for row in groups['rows']] == ['71,4%', '17,7%', '6,1%', '4,9%']
    assert groups['charts'][0]['type'] == 'pie' and groups['charts'][0]['series'][0]['values'][0] == 4_120_000
    views = view.column_views(prepared, 0)
    assert [item.code for item in views] == ['dd/mm/yyyy', None, None, '#,##0 "₫"']
    assert view.format_number(-1234567.891, 2) == '-1.234.567,89' and view.format_number(-0.001, 2) == '0,00'


def test_xlsx_keeps_formulas_with_results_charts_and_layout():
    prepared = build(*sheet_sample('diem')['sheets'])
    archive = zipfile.ZipFile(BytesIO(xlsx_out.render(prepared)))
    first = archive.read('xl/worksheets/sheet1.xml').decode()
    assert '<c r="F2" s="4"><f>ROUND((C2+D2*2+E2*3)/6,1)</f><v>7.8</v></c>' in first
    assert re.search(r'<c r="G2" s="\d+" t="str"><f>IF\(F2&gt;=8,"Giỏi".*?</f><v>Khá</v></c>', first)
    assert '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' in first
    assert '<autoFilter ref="A1:G11"/>' in first and 'MOD(ROW(),2)=1' in first
    assert 'Bảng điểm lớp 10A1 - Học kỳ I</oddHeader>' in first
    assert 'fullCalcOnLoad="1"' in archive.read('xl/workbook.xml').decode()
    chart = archive.read('xl/charts/chart1.xml').decode()
    assert "<c:f>'Thống kê'!$B$2:$B$5</c:f>" in chart and '<c:max val="4.0"/>' in chart
    assert '<c:pt idx="3"><c:v>1</c:v></c:pt>' in chart
    second = archive.read('xl/worksheets/sheet2.xml').decode()
    assert "<f>COUNTIF('Bảng điểm'!G$2:G$11,A2)</f><v>3</v>" in second


# ---------- trong chat ----------
async def test_excel_request_creates_card_download_and_grid(client, anon_client, monkeypatch):
    events = await read_events(await client.post('/api/chat', json={'message': '__excel__'}))
    assert events[-1]['type'] == 'done'
    artifact = next(event['artifact'] for event in events if event['type'] == 'artifact')
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    assert artifact['format'] == 'xlsx' and artifact['style'] == 'sheet' and artifact['pages'] == 2
    assert artifact['filename'] == 'Bảng điểm lớp 10A1 - Học kỳ I.xlsx'
    base = f"/api/documents/{artifact['id']}"
    listing = (await client.get(f'/api/documents?conversation_id={conversation}')).json()['documents']
    assert listing[0]['format'] == 'xlsx' and listing[0]['pages'] == 2
    workbook = await client.get(base + '/export/xlsx?version=1')
    assert workbook.status_code == 200
    assert workbook.headers['content-type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert zipfile.ZipFile(BytesIO(workbook.content)).read('xl/workbook.xml')
    for other in ('pdf', 'docx', 'pptx'):
        assert (await client.get(base + f'/export/{other}?version=1')).status_code == 400
    assert (await client.get(base + '/preview?version=1&page=1')).status_code == 404
    grid = (await client.get(base + '/sheet?version=1')).json()
    scores = grid['sheets'][0]
    assert scores['rows'][0][5] == {'d': '7,8', 't': 'n', 'f': '=ROUND((C2+D2*2+E2*3)/6,1)'}
    assert scores['rows'][0][6]['d'] == 'Khá' and scores['total'][5]['d'] == '7,2' and scores['formulas'] == 24
    assert [chart['type'] for chart in grid['sheets'][1]['charts']] == ['column', 'pie']
    assert (await anon_client.get(base + '/sheet?version=1')).status_code == 401
    edit = await client.post(base + '/versions', json={'title': 'Sửa', 'content': '# Sửa', 'base_version': 1})
    assert edit.status_code == 400 and 'Nhờ Peto sửa' in edit.json()['detail']
    seen = []

    class FollowUp:
        async def stream(self, **kwargs):
            seen.extend(kwargs['messages'])
            yield 'Đã đọc bảng cũ.'
    monkeypatch.setattr(chat_service, 'get_provider', lambda model="peto": FollowUp())
    await client.post('/api/chat', json={'message': 'Thêm cột ghi chú', 'conversation_id': conversation})
    # Peto nhận lại bảng cũ (JSON gọn, công thức đã chuẩn hóa) để sửa ở lượt sau.
    assert any('=ROUND((C2+D2*2+E2*3)/6,1)' in a.text_excerpt for m in seen for a in m.attachments)


async def test_documents_without_a_workbook_refuse_xlsx(client):
    events = await read_events(await client.post('/api/chat', json={'message': 'Tạo file docx viết một bài nghị luận xã hội'}))
    artifact = next(event['artifact'] for event in events if event['type'] == 'artifact')
    assert (await client.get(f"/api/documents/{artifact['id']}/export/xlsx?version=1")).status_code == 400
    assert (await client.get(f"/api/documents/{artifact['id']}/sheet?version=1")).status_code == 404


async def test_tool_reports_totals_and_rejects_bad_input(client):
    conversation = await db.create_conversation(TEST_OWNER, 'Chi tiêu')
    session = DocumentSession(TEST_OWNER, conversation)
    result = await session.tabulate(json.dumps(sheet_sample('chitieu'), ensure_ascii=False))
    assert result['ok'] and 'Số tiền (D10) = 5.770.000 ₫' in result['results']
    again = await session.tabulate(json.dumps(sheet_sample('chitieu'), ensure_ascii=False))
    assert again is result and len(session.created) == 1
    broken = sheet_sample('diem')
    broken['sheets'][0]['rows'][0][5] = '=C2/0'
    error = await session.tabulate(json.dumps(broken, ensure_ascii=False))
    assert 'Bảng điểm!F2' in error['error'] and '#DIV/0!' in error['error']
    unaccented = sheet_sample('chitieu')
    unaccented['title'] = 'Ke hoach chi tieu'
    unaccented['sheets'][0]['columns'][1]['header'] = 'Noi dung'
    unaccented['sheets'][0]['rows'] = [['2026-10-01', 'Tai lieu hoc tap', 'Doc sach', '1000']]
    unaccented['sheets'][0]['total_row'] = None
    unaccented['sheets'] = unaccented['sheets'][:1]
    assert 'không dấu' in (await session.tabulate(json.dumps(unaccented)))['error']
    schema = await session.tabulate('{"title": "Thiếu trang"}')
    assert 'create_spreadsheet' in schema['error']


async def test_branch_keeps_the_workbook(client):
    conversation = await db.create_conversation(TEST_OWNER, 'Nhánh bảng tính')
    await db.add_message(conversation, 'user', 'Lập bảng điểm')
    session = DocumentSession(TEST_OWNER, conversation)
    result = await session.tabulate(json.dumps(sheet_sample('diem'), ensure_ascii=False))
    await db.add_message(conversation, 'assistant', 'Đã tạo', artifacts=[result['artifact']])
    second = await db.add_message(conversation, 'user', 'Sửa lại')
    branch, _ = await conversation_actions.fork(TEST_OWNER, conversation, second, 'Sửa lại giúp mình')
    copied = (await db.get_messages(TEST_OWNER, branch))[1]['artifacts'][0]
    assert copied['id'] != result['artifact']['id']
    response = await client.get(f"/api/documents/{copied['id']}/export/xlsx?version=1")
    assert response.status_code == 200 and response.content.startswith(b'PK')


async def test_real_provider_offers_the_spreadsheet_tool(client, monkeypatch):
    from test_clock_tools import FakeStream, call, done, fake_provider
    arguments = json.dumps(sheet_sample('diem'), ensure_ascii=False)
    first = FakeStream([done(call('create_spreadsheet', arguments))])
    second = FakeStream([SimpleNamespace(type='response.output_text.delta', delta='Đã tạo bảng điểm.'), done()])
    provider, requests = fake_provider(monkeypatch, [first, second])
    conversation = await db.create_conversation(TEST_OWNER, 'Bảng tính qua provider')
    token = current_session.set(DocumentSession(TEST_OWNER, conversation))
    try:
        chunks = [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Lập bảng điểm')])]
    finally:
        current_session.reset(token)
    assert any(tool.get('name') == 'create_spreadsheet' for tool in requests[0]['tools'])
    result = json.loads(requests[1]['input'][-1]['output'])
    assert result['ok'] is True and result['artifact']['format'] == 'xlsx' and 'Trung bình lớp' in result['results']
    assert any(isinstance(chunk, StreamChunk) and chunk.kind == 'document_status' and 'bảng tính' in chunk.text for chunk in chunks)

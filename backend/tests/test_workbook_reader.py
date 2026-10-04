"""Đọc tệp Excel người dùng gửi lên (workbook_reader): giá trị đã lưu, công thức gom theo vùng, ngày và phần trăm, giới
hạn an toàn, nhận tệp đính kèm và đưa nội dung cho Peto."""
import base64
import io
import json
import zipfile
from datetime import datetime

import pytest
import xlsxwriter

import storage as db
from features.chat import service as chat_service
from features.documents import reader, workbook_reader
from shared import attachments
from shared.attachment_tools import AttachmentFiles
from conftest import TEST_OWNER, read_events


def workbook(build, **options) -> bytes:
    """Tệp XLSX do XlsxWriter dựng, như tệp Excel thật."""
    output = io.BytesIO()
    book = xlsxwriter.Workbook(output, {'in_memory': True, **options})
    build(book)
    book.close()
    return output.getvalue()


def grades(book):
    sheet = book.add_worksheet('Bảng điểm')
    percent = book.add_format({'num_format': '0.0%'})
    when = book.add_format({'num_format': 'dd/mm/yyyy'})
    sheet.merge_range('A1:D1', 'BẢNG ĐIỂM LỚP 10A1')
    for col, header in enumerate(['Họ và tên', 'Điểm', 'Ngày thi', 'Tỉ lệ']):
        sheet.write(1, col, header)
    for row, (name, score) in enumerate([('Nguyễn Minh Anh', 7.5), ('Trần Gia Bảo', 8.25), ('Lê Thu Hà', 6)], start=2):
        sheet.write_string(row, 0, name)
        sheet.write_number(row, 1, score)
        sheet.write_datetime(row, 2, datetime(2026, 10, 4), when)
        sheet.write_formula(row, 3, f'=B{row + 1}/10', percent, score / 10)
    sheet.write_formula(5, 1, '=AVERAGE(B3:B5)', None, 7.25)
    sheet.write_formula(5, 2, '=COUNT(B3:B5)', None, 3)
    sheet.write_boolean(6, 0, True)
    sheet.write_formula(6, 1, '=1/0', None, '#DIV/0!')
    sheet.write_rich_string(7, 0, 'Ghi ', book.add_format({'bold': True}), 'chú', ' cuối')
    secret = book.add_worksheet('Ẩn')
    secret.write('A1', 'dữ liệu ẩn')
    secret.hide()
    book.define_name('DiemCao', "='Bảng điểm'!$B$4")


def extract(data, chars=80_000):
    return reader.extract_document(data, workbook_reader.XLSX_MIME, chars, 100)


def test_values_formulas_dates_percent_and_layout():
    document = extract(workbook(grades))
    assert document['status'] == 'ready' and document['sheets'] == 2 and document['sheets_read'] == 2
    text = document['text']
    assert '[Bảng tính Excel · 2 trang tính: "Bảng điểm", "Ẩn"]' in text
    assert "Tên vùng: DiemCao = 'Bảng điểm'!$B$4" in text
    assert '[Trang tính 1/2 "Bảng điểm" · vùng A1:D8' in text and 'Ô gộp: A1:D1' in text
    assert 'Hàng 3 | A: Nguyễn Minh Anh | B: 7.5 | C: 2026-10-04 | D: 75%' in text
    assert 'Hàng 4 | A: Trần Gia Bảo | B: 8.25 | C: 2026-10-04 | D: 82.5%' in text
    assert 'Công thức D3:D5 (chép xuống, 3 ô): =B3/10' in text
    assert 'Công thức B6: =AVERAGE(B3:B5)' in text and 'Hàng 6 | B: 7.25 | C: 3' in text
    assert 'Hàng 7 | A: TRUE | B: #DIV/0!' in text and 'Hàng 8 | A: Ghi chú cuối' in text
    assert '[Trang tính 2/2 "Ẩn" · vùng A1:A1 · 1 hàng có dữ liệu · đang ẩn]' in text
    assert 'Có 1 trang tính đang ẩn' in document['notice'] and 'kết quả đã lưu trong tệp' in document['notice']
    public = reader.public_document(document)
    assert public['sheets'] == 2 and public['rows'] == 9 and 'text' not in public


def test_dates_in_1904_workbooks_and_inline_strings():
    def build(book):
        sheet = book.add_worksheet('Lịch')
        sheet.write_datetime(0, 0, datetime(2026, 1, 2, 13, 30), book.add_format({'num_format': 'yyyy-mm-dd hh:mm'}))
        sheet.write_number(0, 1, 0.5, book.add_format({'num_format': 'hh:mm'}))
        sheet.write_string(0, 2, 'chữ ghi thẳng')
    text = extract(workbook(build, date_1904=True, constant_memory=True))['text']
    assert 'Hàng 1 | A: 2026-01-02 13:30 | B: 12:00 | C: chữ ghi thẳng' in text


def package(sheet_xml: str, extra=None, workbook_xml=None) -> bytes:
    """Gói XLSX tối thiểu tự dựng, để thử những gì XlsxWriter không ghi (công thức chung, ô thiếu địa chỉ…)."""
    main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        '_rels/.rels': ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        f'<Relationship Id="r1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
        'xl/workbook.xml': workbook_xml or (f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
                                            '<sheet name="Dữ liệu" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        'xl/_rels/workbook.xml.rels': ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                       f'<Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/>'
                                       '</Relationships>'),
        'xl/worksheets/sheet1.xml': f'<worksheet xmlns="{main}"><sheetData>{sheet_xml}</sheetData></worksheet>',
        **(extra or {}),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_shared_formulas_are_expanded_and_missing_addresses_follow_order():
    rows = ''.join(f'<row r="{r}"><c r="A{r}"><v>{r}</v></c><c r="B{r}">'
                   + (f'<f t="shared" ref="B1:B4" si="0">A1*2</f>' if r == 1 else '<f t="shared" si="0"/>')
                   + f'<v>{r * 2}</v></c></row>' for r in range(1, 5))
    rows += '<row><c><v>9</v></c><c t="inlineStr"><is><t>không địa chỉ</t></is></c></row>'
    rows += '<row r="7"><c r="C7"><f>SUM(B1:B4)</f></c></row>'
    document = extract(package(rows))
    text = document['text']
    assert 'Công thức B1:B4 (chép xuống, 4 ô): =A1*2' in text
    assert 'Hàng 5 | A: 9 | B: không địa chỉ' in text
    assert 'Hàng 7 | C: (chưa có kết quả)' in text and 'Công thức C7: =SUM(B1:B4)' in text
    assert '1 ô công thức chưa có kết quả lưu sẵn' in document['notice']
    assert workbook_reader.shift_formula("=SUM($A1:B$2)&\"A1\"+'Trang 2'!C3", 2, 1) == "=SUM($A3:C$2)&\"A1\"+'Trang 2'!D5"


def test_number_formats_are_classified():
    kinds = {code: workbook_reader.format_kind(code) for code in (
        '#,##0 "₫"', '[$-42A]dd/mm/yyyy', 'mm:ss', '[h]:mm', '0.00E+00', '0.0%', '@', 'General', '"Tháng "m', 'yyyy-mm-dd hh:mm')}
    assert kinds == {'#,##0 "₫"': 'number', '[$-42A]dd/mm/yyyy': 'date', 'mm:ss': 'time', '[h]:mm': 'time',
                     '0.00E+00': 'number', '0.0%': 'percent', '@': 'text', 'General': 'number', '"Tháng "m': 'date',
                     'yyyy-mm-dd hh:mm': 'datetime'}
    assert workbook_reader.format_decimals('0.00%') == 2 and workbook_reader.format_decimals('#,##0') == 0


def test_long_workbooks_are_condensed_and_limits_are_honest(monkeypatch):
    def build(book):
        sheet = book.add_worksheet('Nhật ký')
        for row in range(3000):
            sheet.write_row(row, 0, [f'Mục số {row + 1}', row * 1000, 'ghi chú dài ' * 3])
    data = workbook(build)
    condensed = extract(data, chars=20_000)
    assert condensed['status'] == 'partial' and condensed['characters'] <= 20_000
    excerpt = condensed['text']
    assert 'Hàng 1 | A: Mục số 1 |' in excerpt and 'Hàng 3000 | A: Mục số 3000 |' in excerpt
    assert '[… bỏ qua dòng ' in excerpt and 'đọc bằng read_attachment_lines' in excerpt and 'hàng Excel ' in excerpt
    assert 'Bảng dài' in condensed['notice'] and condensed['total_characters'] > 100_000
    # Số dòng trong dòng báo bỏ qua khớp với dòng của chữ đầy đủ mà công cụ đọc theo dòng dùng.
    full = reader.extract_document(data, workbook_reader.XLSX_MIME, reader.FULL_TEXT_CHARS, 100)['text'].splitlines()
    first = int(excerpt.split('[… bỏ qua dòng ')[1].split('–')[0].replace('.', ''))
    assert full[first - 1].startswith('Hàng ') and full[first - 1] not in excerpt
    monkeypatch.setattr(workbook_reader, 'MAX_ROWS', 100)
    capped = extract(data)
    assert capped['status'] == 'partial' and capped['rows'] == 100
    assert 'dài hơn 100 hàng' in capped['notice']


@pytest.mark.parametrize('data, status, message', [
    (workbook_reader.CFB_MAGIC + b'\0' * 600, 'encrypted', 'mật khẩu'),
    (b'not a zip at all', 'unreadable', 'tệp hỏng'),
    (package('<row r="1"><c r="A1"><v>1</v></c></row>', workbook_xml=(
        '<!DOCTYPE workbook [<!ENTITY a "aaaa">]><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheets/></workbook>')), 'unreadable', 'tệp hỏng'),
])
def test_unsafe_or_broken_files_are_refused(data, status, message):
    document = extract(data)
    assert document['status'] == status and message in document['notice']


def test_oversized_parts_are_cut_off(monkeypatch):
    monkeypatch.setattr(workbook_reader, 'MAX_PART_BYTES', 2_000)
    rows = ''.join(f'<row r="{r}"><c r="A{r}"><v>{r}</v></c></row>' for r in range(1, 400))
    document = extract(package(rows))
    assert document['status'] == 'unreadable' and 'quá lớn' in document['notice']


# ---------- nhận tệp và đưa cho Peto ----------
def test_attachments_accept_xlsx_and_explain_old_or_locked_files():
    data = workbook(grades)
    assert attachments.classify('bang-diem.xlsx', '', data) == ('file', workbook_reader.XLSX_MIME)
    assert attachments.classify('macro.xlsm', 'application/octet-stream', data) == ('file', workbook_reader.XLSM_MIME)
    assert attachments.is_media_attachment('file', workbook_reader.XLSX_MIME)
    with pytest.raises(attachments.AttachmentError, match='mật khẩu hoặc là định dạng Excel cũ'):
        attachments.classify('khoa.xlsx', '', workbook_reader.CFB_MAGIC + b'\0' * 100)
    with pytest.raises(attachments.AttachmentError, match='định dạng Excel cũ'):
        attachments.classify('cu.xls', 'application/vnd.ms-excel', workbook_reader.CFB_MAGIC + b'\0' * 100)
    with pytest.raises(attachments.AttachmentError, match='không phải tệp Excel'):
        attachments.classify('gia.xlsx', workbook_reader.XLSX_MIME, b'hello')


async def test_upload_gives_peto_the_sheet_and_tools_search_it(client, monkeypatch):
    seen = []

    async def spy(self, **kwargs):
        seen.append(kwargs['messages'])
        yield 'Đã đọc bảng.'

    class Spy:
        stream = spy

    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Spy())
    payload = {'name': 'Bảng điểm.xlsx', 'mime': workbook_reader.XLSX_MIME, 'data': base64.b64encode(workbook(grades)).decode()}
    events = await read_events(await client.post('/api/chat', json={'message': 'Ai điểm cao nhất?', 'attachments': [payload]}))
    assert events[-1]['type'] == 'done', events
    meta = next(event for event in events if event['type'] == 'meta')
    document = meta['message']['attachments'][0]['document']
    assert document['status'] == 'ready' and document['sheets'] == 2 and document['rows'] == 9
    excerpt = seen[0][-1].attachments[0].text_excerpt
    assert 'Hàng 4 | A: Trần Gia Bảo | B: 8.25' in excerpt and 'Công thức D3:D5' in excerpt
    rows = await db.get_messages(TEST_OWNER, meta['conversation_id'])
    files = AttachmentFiles(rows)
    found = await files.run('search_attachment', json.dumps({'file': 'Bảng điểm.xlsx', 'query': 'tran gia bao', 'context_lines': 0}))
    assert found['matches'] == 1 and 'Trần Gia Bảo' in found['text']
    lines = await files.run('read_attachment_lines', json.dumps({'file': 'Bảng điểm.xlsx', 'start_line': 1, 'end_line': 3}))
    assert lines['start_line'] == 1 and 'Bảng tính Excel' in lines['text']

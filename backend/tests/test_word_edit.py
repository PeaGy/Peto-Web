"""Sửa thẳng tệp Word người dùng gửi (word_edit, công cụ edit_document): chèn lời giải, điền bảng, thay và xóa đoạn,
tất cả bằng Theo dõi thay đổi của Word, tác giả Peto; phần khác của tệp giữ nguyên từng byte."""
import base64
import io
import zipfile

import pytest
from lxml import etree

from features.documents import reader
from features.documents.word_edit import run
from features.documents.word_edit.ops import parse_target
from test_word_reader import NAMESPACES, NUMBERING, numbered, word

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
DATE = '2026-10-12T08:00:00Z'


def para(text: str) -> str:
    return f'<w:p><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="28"/></w:rPr>' \
           f'<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def table(rows: list[list[str]]) -> str:
    cells = ''.join('<w:tr>' + ''.join(f'<w:tc><w:p>{f"<w:r><w:t>{cell}</w:t></w:r>" if cell else ""}</w:p></w:tc>'
                                       for cell in row) + '</w:tr>' for row in rows)
    return f'<w:tbl><w:tblPr/><w:tblGrid/>{cells}</w:tbl>'


SECTION = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1701"/></w:sectPr>'


def docx(body: str, **parts) -> bytes:
    data = word(body + SECTION, **parts)
    # Thêm một phần không liên quan để kiểm tra nó được giữ nguyên từng byte.
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, 'w') as archive:
        for info in source.infolist():
            archive.writestr(info, source.read(info))
        archive.writestr('word/media/image1.png', b'\x89PNG giu nguyen')
    return output.getvalue()


def change(action: str, target: str, content: str | None = None, row: int | None = None, column: int | None = None):
    return {'action': action, 'target': target, 'content': content, 'row': row, 'column': column}


def edit(data: bytes, *changes) -> dict:
    outcome = run(data, list(changes), DATE, 40_000)
    assert 'error' not in outcome, outcome
    return outcome


def document(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return etree.fromstring(archive.read('word/document.xml'))


def text_of(data: bytes) -> str:
    return reader.extract_document(data, reader.DOCX_MIME, 80_000, 100)['text']


QUESTIONS = (para('Bài 1. Cho hàm Bool') + numbered('Lập bảng giá trị của F;', 1) + numbered('Viết công thức F;', 1)
             + para('Hết.'))


def test_answers_go_under_each_question_as_tracked_insertions_by_peto():
    original = docx(QUESTIONS, numbering=NUMBERING)
    assert '[Đoạn 2]\na) Lập bảng giá trị của F;' in text_of(original)
    outcome = edit(original,
                   change('insert_after', 'Đoạn 2', '| x | y | F |\n|---|---|---|\n| 0 | 0 | 1 |\n| 0 | 1 | $\\overline{x}y$ |'),
                   change('insert_after', 'Đoạn 3', 'Ta có $F = \\overline{x} + y$.\n\n$$F = \\sum m(0, 3)$$'),
                   change('insert_after', 'Đoạn 3', '**Kết luận:** xong.'))
    root = document(outcome['data'])
    marks = root.findall(f'.//{W}ins')
    assert marks and all(mark.get(f'{W}author') == 'Peto' and mark.get(f'{W}date') == DATE for mark in marks)
    assert len({mark.get(f'{W}id') for mark in marks}) == len(marks), 'mỗi dấu sửa một mã riêng'
    # Công thức chèn vào là công thức Word thật, nằm trong phần chèn của Peto.
    assert root.find(f'.//{W}ins/{M}oMath') is not None and root.find(f'.//{W}ins/{M}oMathPara') is not None
    # Phần chèn mặc định lấy phông và cỡ chữ của đoạn bên cạnh, không lấy đậm.
    inserted = root.find(f'.//{W}ins/{W}r/{W}rPr')
    assert inserted.find(f'{W}sz').get(f'{W}val') == '28' and inserted.find(f'{W}rFonts') is not None
    text = text_of(outcome['data'])
    # Số thứ tự a), b) Word tự đánh vẫn đúng; lời giải nằm dưới đúng câu, theo thứ tự gửi.
    assert text.index('a) Lập bảng') < text.index('x | y | F') < text.index('b) Viết công thức') < text.index(
        'Ta có $F=\\overline{x}+y$') < text.index('$$F=\\sum m(0,3)$$') < text.index('Kết luận: xong.') < text.index('Hết.')
    assert outcome['lines'] == ['Chèn sau Đoạn 2: 1 bảng', 'Chèn sau Đoạn 3: 1 đoạn, 1 công thức', 'Chèn sau Đoạn 3: 1 đoạn']
    assert outcome['readout'] == text_of(outcome['data'])
    with zipfile.ZipFile(io.BytesIO(outcome['data'])) as archive:
        assert archive.read('word/media/image1.png') == b'\x89PNG giu nguyen'
        assert archive.read('word/numbering.xml') == zipfile.ZipFile(io.BytesIO(original)).read('word/numbering.xml')


def test_tables_never_touch_and_a_document_never_ends_with_a_table():
    data = docx(para('Câu hỏi') + table([['A', 'B'], ['1', '2']]))
    outcome = edit(data, change('insert_after', 'Bảng 1', '| x |\n|---|\n| 1 |'))
    body = document(outcome['data']).find(f'{W}body')
    kinds = [etree.QName(child).localname for child in body]
    # Bảng cũ, đoạn trống chen giữa (để Word không gộp hai bảng), bảng mới, đoạn trống trước sectPr.
    assert kinds == ['p', 'tbl', 'p', 'tbl', 'p', 'sectPr']
    assert body[2].find(f'{W}pPr/{W}rPr/{W}ins') is not None and body[4].find(f'{W}pPr/{W}rPr/{W}ins') is not None


def test_replace_and_delete_mark_old_text_as_deleted_and_keep_its_formatting():
    data = docx(para('Câu 1: sai chính tả') + para('Đoạn thừa') + para('Cuối'))
    outcome = edit(data, change('replace', 'Đoạn 1', 'Câu 1: đúng chính tả'), change('delete', 'Đoạn 2'))
    root = document(outcome['data'])
    deleted = [node.text for node in root.iter(f'{W}delText')]
    assert deleted == ['Câu 1: sai chính tả', 'Đoạn thừa']
    first = root.find(f'{W}body/{W}p')
    assert first.find(f'{W}del/{W}r/{W}rPr/{W}sz') is not None, 'chữ bị xóa giữ nguyên định dạng cũ'
    second = root.findall(f'{W}body/{W}p')[1]
    assert second.find(f'{W}pPr/{W}rPr/{W}del') is not None, 'dấu xuống đoạn cũng bị xóa, như Word xóa cả đoạn'
    text = text_of(outcome['data'])
    assert '[Đoạn 1]\nCâu 1: đúng chính tả' in text and 'Đoạn thừa' not in text and '[Đoạn 2]\nCuối' in text


def test_retracting_petos_own_insertion_removes_it_instead_of_marking_it():
    data = docx(para('Câu hỏi') + para('Hết'))
    first = edit(data, change('insert_after', 'Đoạn 1', 'Lời giải cũ $x=1$'))
    assert '[Đoạn 2]\nLời giải cũ $x=1$' in first['readout']
    second = edit(first['data'], change('replace', 'Đoạn 2', 'Lời giải mới $x=2$'))
    root = document(second['data'])
    assert not list(root.iter(f'{W}delText')), 'phần Peto chèn bị thay thì bỏ hẳn, không để lại dấu xóa'
    assert '[Đoạn 2]\nLời giải mới $x=2$' in second['readout']
    third = edit(second['data'], change('delete', 'Đoạn 2'))
    body = document(third['data']).find(f'{W}body')
    assert [etree.QName(child).localname for child in body] == ['p', 'p', 'sectPr']
    assert not list(body.iter(f'{W}del')) and third['readout'] == '[Đoạn 1]\nCâu hỏi\n\n[Đoạn 2]\nHết'


def test_empty_answer_tables_are_listed_and_filled_cell_by_cell():
    data = docx(para('Lập bảng giá trị') + table([['x', 'F'], ['', ''], ['', '']]) + table([['', ''], ['', '']]))
    text = text_of(data)
    assert '[Bảng 2]\n(bảng trống: 2 hàng × 2 cột)' in text, 'bảng trống vẫn được đánh số để Peto thấy'
    outcome = edit(data, change('fill_cell', 'Bảng 1', '0', 2, 1), change('fill_cell', 'Bảng 1', '$\\overline{x}$', 2, 2),
                   change('fill_cell', 'Bảng 2', 'Ô', 1, 1))
    assert '[Bảng 1]\nx | F\n0 | $\\overline{x}$' in outcome['readout']
    assert '[Bảng 2]\nÔ | ' in outcome['readout']
    assert outcome['lines'][0] == 'Điền Bảng 1, ô hàng 2 cột 1: 0'


def test_every_problem_is_reported_at_once_and_nothing_is_written():
    data = docx(para('Có $x$ công thức') + '<w:p><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></w:p>'
                + table([['a', 'b']]))
    outcome = run(data, [
        change('insert_after', 'Đoạn 9', 'x'),
        change('replace', 'Bảng 1', 'y'),
        change('fill_cell', 'Bảng 1', 'z', 3, 1),
        change('insert_after', 'Đoạn 1', '![ảnh](anh-1)'),
        change('insert_after', 'Đoạn 1', '$\\unknowncommand{x}$'),
        change('delete', 'Đoạn 2'),
        change('insert_after', 'Trang 1', 'x'),
        change('insert_after', 'Đoạn 1', None),
    ], DATE, 40_000)
    error = outcome['error']
    assert 'data' not in outcome
    lines = error.splitlines()
    assert len(lines) == 8 and all(line.startswith('Thay đổi ') for line in lines)
    assert 'không có Đoạn 9 (có 2 đoạn, 1 bảng' in lines[0]
    assert 'replace chỉ dùng cho đoạn' in lines[1]
    assert 'bảng có 1 hàng, không có hàng 3' in lines[2]
    assert 'chưa nhận ảnh' in lines[3]
    assert 'unknowncommand' in lines[4]
    assert 'công thức Word' in lines[5] and 'insert_after' in lines[5]
    assert '"Đoạn N" hoặc "Bảng N"' in lines[6] and 'cần content' in lines[7]


def test_merged_cells_and_broken_files_are_refused():
    merged = ('<w:tbl><w:tblPr/><w:tblGrid/><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>Gộp</w:t>'
              '</w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>A</w:t></w:r>'
              '</w:p></w:tc><w:tc><w:p/></w:tc></w:tr><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc><w:tc><w:p/>'
              '</w:tc></w:tr></w:tbl>')
    data = docx(merged)
    edit(data, change('fill_cell', 'Bảng 1', 'Hai', 1, 2))  # cột 2 thuộc ô gộp ngang đầu hàng
    assert 'vùng gộp' in run(data, [change('fill_cell', 'Bảng 1', 'x', 3, 1)], DATE, 1000)['error']
    assert 'Word .docx hợp lệ' in run(b'not a zip', [change('delete', 'Đoạn 1')], DATE, 1000)['error']
    assert '.doc cũ' in run(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest', [change('delete', 'Đoạn 1')], DATE, 1000)['error']
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://purl.oclc.org/ooxml/wordprocessingml/main">'
                                              '<w:body/></w:document>')
    strict = output.getvalue()
    assert 'Strict Open XML' in run(strict, [change('delete', 'Đoạn 1')], DATE, 1000)['error']


@pytest.mark.parametrize('target,expected', [('Đoạn 3', ('p', 3)), ('[Bảng 12]', ('tbl', 12)), ('doan 4', ('p', 4)),
                                             ('BẢNG 2', ('tbl', 2)), ('Câu 3', None), ('Đoạn', None)])
def test_targets_accept_the_reader_labels(target, expected):
    assert parse_target(target) == expected


def test_preview_marks_insertions_deletions_and_keeps_reader_numbers():
    data = docx(QUESTIONS, numbering=NUMBERING)
    outcome = edit(data, change('insert_after', 'Đoạn 2', 'Đáp án $x$'), change('replace', 'Đoạn 4', 'Kết thúc'))
    blocks = outcome['preview']['blocks']
    labels = [(block.get('number'), block.get('label'), block.get('state')) for block in blocks]
    assert labels == [(1, None, None), (2, 'a)', None), (3, None, 'ins'), (4, 'b)', None), (5, None, None)]
    inserted = blocks[2]['parts']
    assert inserted == [{'text': 'Đáp án ', 'state': 'ins'}, {'math': 'x', 'display': False, 'state': 'ins'}]
    assert [part['state'] for part in blocks[4]['parts']] == ['del', 'ins']
    assert outcome['preview']['counts'] == {'ins': 3, 'del': 1}


# ---------- trong chat ----------

def upload(name: str, data: bytes) -> dict:
    return {'name': name, 'mime': reader.DOCX_MIME, 'data': base64.b64encode(data).decode()}


async def test_chat_edits_a_word_upload_then_its_latest_version(client, anon_client):
    from conftest import read_events, sign_in

    events = await read_events(await client.post('/api/chat', json={
        'message': 'Bài tập của mình', 'attachments': [upload('Bài tập 05.docx', docx(QUESTIONS, numbering=NUMBERING))]}))
    conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
    events = await read_events(await client.post('/api/chat', json={'message': '__suaword__', 'conversation_id': conversation}))
    assert events[-1]['type'] == 'done', events
    first = next(event['artifact'] for event in events if event['type'] == 'artifact')
    assert first['style'] == 'wordedit' and first['format'] == 'docx' and first['filename'] == 'Bài tập 05.docx'
    assert first['changes'] == ['Chèn sau Đoạn 1: 1 đoạn, 1 bảng'] and first['pages'] == 0
    work = next(event['work'] for event in events if event['type'] == 'work')
    assert any(step['kind'] == 'tool' and step['label'] == 'Đã sửa Bài tập 05.docx' for step in work['steps'])
    base = f"/api/documents/{first['id']}"
    preview = (await client.get(base + '/word?version=1')).json()
    assert preview['kind'] == 'word' and [item['text'] for item in preview['changes']] == ['Chèn sau Đoạn 1: 1 đoạn, 1 bảng']
    assert any(block['type'] == 'table' and block.get('rows', [{}])[0].get('state') == 'ins' for block in preview['blocks'])
    download = await client.get(base + '/export/docx?version=1')
    assert download.headers['content-type'] == reader.DOCX_MIME
    assert '[Đoạn 2]\nLời giải. Ta có' in text_of(download.content)
    assert (await client.get(base + '/export/pdf?version=1')).status_code == 400
    assert (await client.get(base + '/preview?version=1')).status_code == 404
    revised = await client.post(base + '/versions', json={'title': 'x', 'content': 'y', 'base_version': 1})
    assert revised.status_code == 400 and 'Word' in revised.json()['detail']
    events = await read_events(await client.post('/api/chat', json={'message': '__suaword__', 'conversation_id': conversation}))
    second = next(event['artifact'] for event in events if event['type'] == 'artifact')
    assert second['id'] == first['id'] and second['version'] == 2
    latest = text_of((await client.get(base + '/export/docx?version=2')).content)
    assert latest.count('Lời giải. Ta có') == 2, 'lần sửa sau dựa trên bản mới nhất'
    # Bản 2 còn dấu chèn của bản 1; dòng thay đổi của bản 2 chỉ trỏ tới phần chèn mới (theo mã dấu sửa), nên bấm nó
    # trong bản xem là tới đúng chỗ vừa sửa, không phải chỗ sửa lần trước.
    view = (await client.get(base + '/word?version=2')).json()
    low, high = view['changes'][0]['revs']
    hit = [index for index, block in enumerate(view['blocks']) if any(low <= rev <= high for rev in block.get('revs', []))]
    old = [index for index, block in enumerate(view['blocks']) if block.get('revs') and index not in hit]
    assert hit and old and hit == [1, 2] and old == [3, 4], (hit, old)
    await sign_in(anon_client)
    assert (await anon_client.get(base + '/word?version=1')).status_code == 404


async def test_provider_offers_the_word_tool_only_with_a_word_file(client, monkeypatch):
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
    for rows, expected in (([], False), ([{'attachments': [{'kind': 'file', 'mime': reader.DOCX_MIME,
                                                             'path': 'x.docx', 'filename': 'x.docx'}]}], True)):
        token = current_session.set(DocumentSession(TEST_OWNER, conversation, rows))
        try:
            [chunk async for chunk in provider.stream(system_prompt='Peto', messages=[ChatMessage('user', 'Giải giúp')])]
        finally:
            current_session.reset(token)
        tools = [tool.get('name') for tool in requests[-1]['tools']]
        assert ('edit_document' in tools) is expected and 'edit_spreadsheet' not in tools

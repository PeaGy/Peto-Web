"""Log Windows có metadata lỗi nhẹ: nhận tệp, đọc sẵn và tìm/đọc lại dùng cùng văn bản."""
import base64
import codecs

import pytest

from conftest import read_events
from features.chat import service as chat_service
from features.documents import reader
from features.documents.text_reader import MAX_CONTROL_CHARS, read_text
from shared import attachments, attachment_tools
from test_attachment_tools import attached, args


CRASH_LINES = [
    '---- Minecraft Crash Report ----',
    'Time: 2026-10-19 17:08:55',
    'Description: Initializing game',
    'java.lang.RuntimeException: mod loading failed',
    'Caused by: InjectionError: Critical injection failure: Callback method flushItemBatching',
    'in acceleratedrendering.compat.sophisticated.mixins.json:StorageScreenBaseMixin, (0/1) succeeded.',
    *[f'\tat example.Frame{index}.load(Frame{index}.java:{index})' for index in range(80)],
    '\tnvspcap64.dll:NVIDIA Game Proxy\x008\x16\x01FileVersion\x00\x001:11.0.9.565\x00\x008\x16\x01Produc:NVIDIA Corporation\x00\x00',
    'End of report.',
]
CRASH = '\r\n'.join(CRASH_LINES)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16', 'utf-32'])
def test_sparse_controls_are_visible_and_original_line_structure_is_preserved(encoding):
    data = CRASH.encode(encoding)
    original = bytes(data)
    assert attachments.classify('crash-client.txt', 'text/plain', data) == ('file', 'text/plain')
    document = reader.extract_document(data, 'text/plain', 80_000, 100)
    text = document['text']
    assert document['status'] == 'ready' and document['normalized_controls'] == 11
    assert '[U+0000]' in text and '[U+0016]' in text and '[U+0001]' in text
    assert len(text.splitlines()) == len(CRASH_LINES) and text.count('\r\n') == CRASH.count('\r\n')
    assert 'flushItemBatching' in text and 'StorageScreenBaseMixin' in text
    assert 'giữ nguyên dòng và tệp gốc' in document['notice']
    assert data == original


@pytest.mark.parametrize('encoding,bom', [('utf-16-le', codecs.BOM_UTF16_LE), ('utf-16-be', codecs.BOM_UTF16_BE),
                                         ('utf-32-le', codecs.BOM_UTF32_LE), ('utf-32-be', codecs.BOM_UTF32_BE)])
def test_explicit_unicode_byte_orders(encoding, bom):
    text = 'Tiếng Việt và 日本語\r\n\tERROR: mẫu thử'
    assert reader.decode_text(bom + text.encode(encoding)) == text


@pytest.mark.parametrize('data', [b'\x00' * 200, b'abc\x00def', bytes(range(128)), b'\xff\xfe\x00',
                                  b'\xff\xffbroken', b'printable' * 15 + b'\x01' * 10,
                                  (b'x' * 100 + b'\x00') * (MAX_CONTROL_CHARS + 1)],
                         ids=['nul', 'short-binary', 'control-range', 'broken-utf16', 'broken-utf8', 'dense', 'count-cap'])
def test_binary_dense_controls_and_broken_encodings_are_still_rejected(data):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        reader.decode_text(data)
    with pytest.raises(attachments.AttachmentError):
        attachments.classify('renamed-binary.txt', 'text/plain', data)
    assert reader.extract_document(data, 'text/plain', 1000, 100)['status'] == 'unreadable'


def test_clean_text_is_unchanged_and_unknown_encoding_has_an_actionable_error():
    text = '\r\n\tTiếng Việt, 日本語, emoji 🎵\r\n'
    normalized, details = read_text(text.encode())
    assert normalized == text and details['normalized_controls'] == 0
    assert reader.extract_document(text.encode(), 'text/plain', 1000, 100)['text'] == text
    with pytest.raises(attachments.AttachmentError, match='Lưu lại thành UTF-8'):
        attachments.classify('old-codepage.log', 'text/plain', b'caf\xe9\n')


def test_excerpt_budget_applies_to_whitespace_and_expanded_control_markers():
    text = '\n' * 4000 + 'x' * 2000
    document = reader.extract_document(text.encode(), 'text/plain', 1000, 100)
    assert document['status'] == 'partial' and len(document['text']) <= 1000
    assert reader.extract_document(b'\n' * 4000, 'text/plain', 1000, 100)['status'] == 'no_text'


def test_deep_root_cause_wins_over_earlier_warnings_and_survives_an_oversized_candidate():
    lines = [f'INFO route{chr(65 + index % 7)} checking record {index}' for index in range(1400)]
    # Cảnh báo đầu có thể nuốt cả ngân sách hoặc chặn phần lỗi phía sau trong bộ chọn cũ.
    for index in range(80, 300, 10):
        lines[index] = f'WARN different warning category-{chr(65 + index % 26)} ' + 'detail ' * 200
    lines[700] = 'Caused by: InjectionError: Critical injection failure flushItemBatching StorageScreenBaseMixin'
    lines[701] = 'acceleratedrendering.compat.sophisticated.mixins.json (0/1) succeeded'
    text = '\n'.join(lines)
    document = reader.extract_document(text.encode(), 'text/plain', 5000, 100)
    assert document['status'] == 'partial' and len(document['text']) <= 5000
    assert lines[700] in document['text'] and lines[701] in document['text']
    assert '[Dòng 699–703 · có lỗi hoặc cảnh báo]' in document['text']


def test_only_old_long_text_cache_is_invalidated():
    old_log = reader.result('partial', 'Tệp dài 5.000 dòng: Peto đọc phần đầu, phần cuối.', 'old excerpt')
    assert reader.cached_document(old_log) is None
    fresh = reader.extract_document(('INFO ' * 5000).encode(), 'text/plain', 1000, 100)
    assert reader.cached_document(fresh) == fresh
    for details in ({'pages': 1}, {'word_format': reader.WORD_FORMAT}, {'sheets': 1, 'sheet_format': reader.SHEET_FORMAT}):
        cached = reader.result('ready', 'Đã đọc tài liệu.', 'body', **details)
        assert reader.cached_document(cached) == cached


async def test_search_and_line_reads_share_the_normalized_text_and_keep_true_line_numbers(tmp_path):
    data = CRASH.encode()
    path = tmp_path / 'crash.txt'
    rows = await attached(tmp_path, path.name, data, 'text/plain')
    files = attachment_tools.AttachmentFiles(rows)
    search = await files.run('search_attachment', args(file=path.name, query='StorageScreenBaseMixin', context_lines=1))
    assert search['matches'] == 1 and search['lines_total'] == len(CRASH_LINES)
    assert '6: ' + CRASH_LINES[5] in search['text']
    assert 'ký tự điều khiển' in search['note']
    line = len(CRASH_LINES) - 1
    read = await files.run('read_attachment_lines', args(file=path.name, start_line=line, end_line=line))
    expected = reader.decode_text(data).splitlines()[line - 1]
    assert read['text'] == f'{line}: {expected}'
    assert path.read_bytes() == data


async def test_upload_reaches_provider_followup_and_download_retains_original_bytes(client, monkeypatch):
    histories = []
    class Provider:
        async def stream(self, **kwargs):
            histories.append(kwargs['messages'])
            yield 'Đã đọc crash report.'
    monkeypatch.setattr(chat_service, 'get_provider', lambda model='peto': Provider())
    raw = CRASH.encode()
    upload = {'name': 'crash-client.txt', 'mime': 'text/plain', 'data': base64.b64encode(raw).decode()}
    events = await read_events(await client.post('/api/chat', json={'message': 'Tìm lỗi crash', 'attachments': [upload]}))
    assert events[-1]['type'] == 'done', events
    meta = next(event for event in events if event['type'] == 'meta')
    attachment = meta['message']['attachments'][0]
    assert attachment['document']['status'] == 'ready' and 'ký tự điều khiển' in attachment['document']['notice']
    excerpt = histories[0][-1].attachments[0].text_excerpt
    assert 'flushItemBatching' in excerpt and '[U+0000]' in excerpt and '\x00' not in excerpt
    assert (await client.get(attachment['url'])).content == raw
    followup = await read_events(await client.post('/api/chat', json={
        'message': 'Giải thích tiếp', 'conversation_id': meta['conversation_id']}))
    assert followup[-1]['type'] == 'done'
    assert '[U+0000]' in histories[-1][0].attachments[0].text_excerpt

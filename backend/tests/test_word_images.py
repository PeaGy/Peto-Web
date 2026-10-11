"""Ảnh nhúng Word: vị trí, giới hạn, quyền tài khoản và đường gửi ảnh cho cả ba provider."""
import base64
import io
import json
import zipfile

import pytest
from fastapi import HTTPException
from PIL import Image

import storage as db
from ai.xai import build_input_payload
from ai.claude import build_messages
from conftest import TEST_OWNER, read_events, sign_in
from features.chat import history, service
from features.documents import reader, word_images
from features.projects.context import context
from shared.attachments import ValidatedAttachment
from storage import projects
from test_word_reader import NAMESPACES


def picture(color='red', fmt='PNG', size=(80, 40)):
    output = io.BytesIO()
    Image.new('RGB', size, color).save(output, fmt)
    return output.getvalue()


def word(refs=None, assets=None, *, crop='', malformed_rels=False):
    refs = refs or [('r1', 'media/one.png', '')]
    assets = assets if assets is not None else {'one.png': picture()}
    content = '<w:p><w:r><w:t>Mô hình mạng</w:t></w:r></w:p>'
    for rid, _, _ in refs:
        content += (f'<w:p><w:r><w:drawing><pic:pic><pic:blipFill><a:blip r:embed="{rid}"/>{crop}</pic:blipFill>'
                    '</pic:pic></w:drawing></w:r></w:p>')
    content += '<w:p><w:r><w:t>Cấu hình theo hình.</w:t></w:r></w:p>'
    relationships = ''.join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{path}" {mode}/>'
                            for rid, path, mode in dict.fromkeys(refs))
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', f'<w:document {NAMESPACES}><w:body>{content}</w:body></w:document>')
        archive.writestr('word/_rels/document.xml.rels', '<broken' if malformed_rels else
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relationships}</Relationships>')
        for path, data in assets.items():
            archive.writestr(f'word/media/{path}', data)
    return output.getvalue()


def read(data):
    return reader.extract_document(data, reader.DOCX_MIME, 80_000, 100)


def file(key, document):
    return {'id': key, 'filename': key + '.docx', 'kind': 'file', 'mime': reader.DOCX_MIME, 'document': document}


def test_anh_theo_vi_tri_khong_theo_ten_media_va_khong_gui_anh_thua():
    document = read(word([('r2', 'media/two.jpg', ''), ('r1', '/word/media/one.png', ''), ('r2', 'media/two.jpg', '')],
        {'one.png': picture('red'), 'two.jpg': picture('blue', 'JPEG'), 'unused.png': picture('green')}))
    assert document['status'] == 'ready'
    assert document['images'] == document['images_prepared'] == 3
    assert document['images_unread'] == 0
    assert [image['number'] for image in document['embedded_images']] == [1, 2, 3]
    colors = []
    for image in document['embedded_images']:
        with Image.open(io.BytesIO(base64.b64decode(image['data_url'].partition(',')[2]))) as bitmap:
            colors.append(bitmap.getpixel((0, 0))[:3])
    assert colors[0][2] > 200 and colors[1][0] > 200 and colors[2] == colors[0]
    assert '[Hình 2 trong tệp]' in document['text']
    public = reader.public_document(json.dumps(document))
    assert public['images_prepared'] == 3
    assert 'embedded_images' not in public and 'data:' not in json.dumps(public)


def test_lien_ket_ngoai_duong_dan_sai_va_anh_hong_khong_mat_chu():
    refs = [('r1', 'https://example.test/private.png', 'TargetMode="External"'),
            ('r2', '../../secret.png', ''), ('r3', 'media/bad.png', ''), ('r4', 'media/ok.png', '')]
    document = read(word(refs, {'bad.png': b'not an image', 'ok.png': picture()}))
    assert document['status'] == 'partial'
    assert 'Mô hình mạng' in document['text']
    assert document['images_unread'] == 3
    assert [image['number'] for image in document['embedded_images']] == [4]
    assert '3 hình Peto chưa xem được' in document['notice']
    broken = read(word(malformed_rels=True))
    assert broken['status'] == 'partial' and broken['images_prepared'] == 0
    assert 'Cấu hình theo hình.' in broken['text']


def test_vung_cat_giu_dung_noi_dung_hien_trong_word():
    image = Image.new('RGB', (100, 40), 'red')
    image.paste('blue', (50, 0, 100, 40))
    output = io.BytesIO(); image.save(output, 'PNG')
    document = read(word(assets={'one.png': output.getvalue()}, crop='<a:srcRect l="50000"/>'))
    prepared = document['embedded_images'][0]
    assert (prepared['width'], prepared['height']) == (50, 40)
    with Image.open(io.BytesIO(base64.b64decode(prepared['data_url'].partition(',')[2]))) as bitmap:
        assert bitmap.getpixel((0, 0))[:3] == (0, 0, 255)


def test_gioi_han_so_anh_bytes_pixels_va_do_phan_giai(monkeypatch):
    refs = [(f'r{i}', 'media/one.png', '') for i in range(10)]
    document = read(word(refs))
    assert document['images_prepared'] == 8 and document['images_unread'] == 2
    large = read(word(assets={'one.png': picture(size=(3000, 1000))}))['embedded_images'][0]
    assert large['width'] == word_images.MAX_EDGE and large['height'] < 1000
    monkeypatch.setattr(word_images, 'MAX_SOURCE_PIXELS', 100)
    assert read(word())['images_prepared'] == 0
    monkeypatch.setattr(word_images, 'MAX_SOURCE_PIXELS', 20_000_000)
    monkeypatch.setattr(word_images, 'MAX_SOURCE_BYTES', 16)
    assert read(word())['images_prepared'] == 0
    monkeypatch.setattr(word_images, 'MAX_SOURCE_BYTES', 10 * 1024 * 1024)
    monkeypatch.setattr(word_images, 'MAX_TOTAL_BYTES', 16)
    assert read(word())['images_prepared'] == 0


def test_ngan_sach_anh_chung_uu_tien_luot_moi_va_nhan_dung_tep(monkeypatch, tmp_path):
    monkeypatch.setattr(history, 'MAX_HISTORY_IMAGES', 2)
    path = tmp_path / 'new.png'; path.write_bytes(picture())
    rows = [{'role': 'user', 'content': 'Cũ', 'attachments': [file('old', read(word()))]},
            {'role': 'user', 'content': 'Mới', 'attachments': [
                {'id': 'photo', 'filename': 'new.png', 'kind': 'image', 'mime': 'image/png', 'path': str(path), 'number': 1},
                file('new', read(word([('r1', 'media/one.png', ''), ('r2', 'media/one.png', '')])))]}]
    messages = history._to_chat_messages(rows)
    sent = [a for m in messages for a in m.attachments if a.kind == 'image' and a.data_url]
    assert len(sent) == 2 and sent[0].number == 1 and sent[1].number == 0
    assert sent[1].source_label.startswith('[Hình 1 trong tệp: new.docx]')
    assert 'không được gửi do giới hạn' in messages[-1].attachments[1].text_excerpt
    assert 'không có' in messages[0].attachments[0].text_excerpt
    payload = build_input_payload(messages)
    assert sum(p['type'] == 'input_image' for m in payload for p in m['content']) == 2
    claude = build_messages(payload, 'test-model')
    assert sum(p['type'] == 'image' for m in claude for p in m['content']) == 2
    assert 'new.docx' in json.dumps(claude, ensure_ascii=False)


@pytest.mark.parametrize('model', ['peto', 'luna', 'haiku'])
async def test_docx_den_provider_hoi_tiep_khong_doc_lai_va_metadata_khong_lo_anh(client, monkeypatch, model):
    seen = []
    class Spy:
        async def stream(self, **kwargs):
            seen.append(kwargs['messages']); yield 'Đã nhận ảnh.'
    monkeypatch.setattr(service, 'get_provider', lambda model='peto': Spy())
    data = word()
    events = await read_events(await client.post('/api/chat', json={'message': 'Xem sơ đồ', 'model': model,
        'attachments': [{'name': 'diagram.docx', 'mime': reader.DOCX_MIME, 'data': base64.b64encode(data).decode()}]}))
    assert events[-1]['type'] == 'done'
    meta = next(e for e in events if e['type'] == 'meta')
    assert len(meta['message']['attachments']) == 1
    assert meta['message']['attachments'][0]['document']['images_prepared'] == 1
    assert 'data:image' not in json.dumps(meta)
    assert len(seen[0][-1].attachments) == 2
    assert seen[0][-1].attachments[1].data_url.startswith('data:image/png;base64,')
    async def no_read(*args):
        pytest.fail('Ảnh Word đã lưu phải được dùng lại khi hỏi tiếp')
    monkeypatch.setattr(reader, 'read_document', no_read)
    follow = await read_events(await client.post('/api/chat', json={'message': 'Giải thích tiếp', 'model': model, 'conversation_id': meta['conversation_id']}))
    assert follow[-1]['type'] == 'done'
    assert seen[-1][0].attachments[1].data_url == seen[0][-1].attachments[1].data_url
    await sign_in(client)
    assert (await client.get(f'/api/conversations/{meta["conversation_id"]}/messages')).status_code == 404
    assert (await client.get(meta['message']['attachments'][0]['url'])).status_code == 404


async def test_word_cu_duoc_doc_lai_mot_lan(client, tmp_path):
    cid = await db.create_conversation(TEST_OWNER)
    mid = await db.add_message(cid, 'user', 'Ảnh cũ')
    data = word(); path = tmp_path / 'old.docx'; path.write_bytes(data)
    old = {**read(data), 'word_format': 2}; old.pop('embedded_images')
    await db.add_attachment(attachment_id='old-word-picture', owner=TEST_OWNER, conversation_id=cid, message_id=mid,
        filename='old.docx', mime=reader.DOCX_MIME, kind='file', size=len(data), path=str(path), document=old)
    rows = await db.get_messages(TEST_OWNER, cid)
    await history._read_legacy_documents(TEST_OWNER, rows, 4)
    assert history._to_chat_messages(rows)[0].attachments[1].data_url.startswith('data:image/png;base64,')
    saved = await db.get_messages(TEST_OWNER, cid)
    assert reader.cached_document(saved[0]['attachments'][0]['document'])['word_format'] == reader.WORD_FORMAT


async def test_anh_tai_lieu_du_an_chi_gui_khi_chon_va_nang_cap_cache_cu(client):
    project = await projects.create_project(TEST_OWNER, 'Dự án sơ đồ')
    data = word(); old = {**read(data), 'word_format': 2}; old.pop('embedded_images')
    fid = await projects.add_file(TEST_OWNER, project['id'], ValidatedAttachment('diagram.docx', reader.DOCX_MIME, 'file', data), old)
    documents = []
    await context(TEST_OWNER, project['id'], [], documents=documents)
    assert documents == []
    prompt = await context(TEST_OWNER, project['id'], [fid], documents=documents)
    assert '[Hình 1 trong tệp]' in prompt and len(documents) == 1
    messages = history._to_chat_messages([{'role': 'user', 'content': 'Xem hình'}], documents)
    assert messages[0].attachments[1].data_url.startswith('data:image/png;base64,')
    assert 'Mô hình mạng' not in messages[0].attachments[0].text_excerpt
    stored = await projects.get_file(TEST_OWNER, project['id'], fid)
    assert reader.cached_document(stored['document'])['images_prepared'] == 1
    detail = (await client.get(f'/api/projects/{project["id"]}')).json()
    assert 'embedded_images' not in detail['files'][0]['document']
    with pytest.raises(HTTPException) as err:
        await context('github:other-account', project['id'], [fid], documents=[])
    assert err.value.status_code == 404

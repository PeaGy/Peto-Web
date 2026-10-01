"""Lưu trữ giữ dữ liệu, quyền sở hữu và nơi khôi phục hội thoại."""
import sqlite3
import base64
from contextlib import asynccontextmanager

from features.chat import service
from storage import connection
import storage
from conftest import TEST_OWNER, read_events


async def test_archive_preserves_chat_files_pin_and_project(client, tmp_path):
    project = (await client.post('/api/projects', json={'name': 'Lưu trữ thử'})).json()['id']
    cid = await storage.create_conversation(TEST_OWNER, 'Chat lưu thử', project_id=project)
    message = await storage.add_message(cid, 'user', 'Nội dung tra cứu riêng')
    path = tmp_path / 'archive.txt'
    path.write_text('Tài liệu còn nguyên', encoding='utf-8')
    await storage.add_attachment(attachment_id='archive-file', owner=TEST_OWNER, conversation_id=cid,
        message_id=message, filename='archive.txt', mime='text/plain', kind='file', size=path.stat().st_size, path=str(path))
    from storage import documents
    document = await documents.save_document(TEST_OWNER, cid, 'Báo cáo được giữ', 'Nội dung tài liệu', assets={
        'format':'docx', 'pages':1, 'docx':b'tep-word-thu', 'pdf':b'tep-pdf-thu', 'preview':b'anh-thu'})
    await storage.add_message(cid, 'assistant', 'Đã tạo báo cáo', artifacts=[{
        'id':document['id'], 'version':1, 'title':document['title'], 'filename':'bao-cao.docx', 'format':'docx', 'pages':1, 'style':'report'}])
    await client.patch(f'/api/conversations/{cid}', json={'pinned': True})
    before = (await client.get(f'/api/conversations/{cid}/messages')).json()
    assert (await client.patch(f'/api/conversations/{cid}', json={'archived': True})).status_code == 200
    for params in [{}, {'q': 'TRA CUU RIENG'}, {'project_id': project}, {'unassigned': True}]:
        assert cid not in [row['id'] for row in (await client.get('/api/conversations', params=params)).json()['conversations']]
    archived = (await client.get('/api/conversations', params={'archived': True, 'q': 'tra cuu rieng'})).json()['conversations']
    assert archived[0]['id'] == cid and archived[0]['pinned'] and archived[0]['project_id'] == project
    after = (await client.get(f'/api/conversations/{cid}/messages')).json()
    assert after['archived'] and before['messages'] == after['messages']
    assert (await client.get(f"/api/documents/{document['id']}/export/docx?version=1")).content == b'tep-word-thu'
    assert (await client.get(before['messages'][0]['attachments'][0]['url'])).content == path.read_bytes()
    projects = (await client.get('/api/projects')).json()['projects']
    assert next(p for p in projects if p['id'] == project)['conversation_count'] == 0
    assert (await client.patch(f'/api/conversations/{cid}', json={'archived': False})).status_code == 200
    restored = (await client.get('/api/conversations', params={'project_id': project})).json()['conversations']
    assert restored[0]['id'] == cid and restored[0]['pinned']
    assert not (await client.get(f'/api/conversations/{cid}/messages')).json()['archived']
    assert (await client.patch(f'/api/conversations/{cid}', json={'archived': True})).status_code == 200
    assert (await client.delete(f'/api/conversations/{cid}')).status_code == 200
    assert not path.exists()
    assert (await client.get(f'/api/conversations/{cid}/messages')).status_code == 404


async def test_restore_after_deleted_project_returns_to_recents(client):
    project = (await client.post('/api/projects', json={'name': 'Dự án đã xong'})).json()['id']
    cid = await storage.create_conversation(TEST_OWNER, project_id=project)
    await client.patch(f'/api/conversations/{cid}', json={'archived': True})
    await client.delete(f'/api/projects/{project}')
    settings = await storage.conversation_settings(TEST_OWNER, cid)
    assert settings['archived'] and settings['project_id'] is None
    await client.patch(f'/api/conversations/{cid}', json={'archived': False})
    assert cid in [c['id'] for c in (await client.get('/api/conversations?unassigned=true')).json()['conversations']]


async def test_archive_owner_and_mode_isolation(client, anon_client):
    other = await storage.create_conversation('archive-other', 'Chat riêng')
    companion = await storage.create_conversation(TEST_OWNER, mode='companion')
    for cid in [other, companion, 'khong-ton-tai']:
        for archived in [True, False]:
            assert (await client.patch(f'/api/conversations/{cid}', json={'archived': archived})).status_code == 404
    assert (await anon_client.get('/api/conversations?archived=true')).status_code == 401
    assert (await anon_client.patch(f'/api/conversations/{other}', json={'archived': True})).status_code == 401
    from features.chat.conversations import update
    await update('archive-other', other, archived=True)
    assert other not in [c['id'] for c in (await client.get('/api/conversations?archived=true')).json()['conversations']]


async def test_archive_search_pagination_and_repeated_updates(client):
    ids = [await storage.create_conversation(TEST_OWNER, f'archive-page-unique {i}') for i in range(3)]
    for cid in ids:
        for _ in range(2):
            assert (await client.patch(f'/api/conversations/{cid}', json={'archived': True})).status_code == 200
    first = (await client.get('/api/conversations', params={'archived': True, 'q': 'archive-page-unique', 'limit': 2})).json()
    second = (await client.get('/api/conversations', params={'archived': True, 'q': 'archive-page-unique', 'limit': 2, 'offset': 2})).json()
    assert first['has_more'] and not second['has_more']
    assert set(c['id'] for c in first['conversations'] + second['conversations']) == set(ids)


async def test_archived_chat_requires_restore_before_send_or_branch(client):
    cid = await storage.create_conversation(TEST_OWNER)
    uid = await storage.add_message(cid, 'user', 'Tin cũ')
    await client.patch(f'/api/conversations/{cid}', json={'archived': True})
    for extra in [{}, {'branch_message_id': uid}]:
        response = await client.post('/api/chat', json={'conversation_id': cid, 'message': 'Tin mới', **extra})
        assert response.status_code == 409
    assert len(await storage.get_messages(TEST_OWNER, cid)) == 1
    await client.patch(f'/api/conversations/{cid}', json={'archived': False})
    events = await read_events(await client.post('/api/chat', json={'conversation_id': cid, 'message': 'Tin mới'}))
    assert any(e['type'] == 'done' for e in events)


async def test_archive_while_waiting_for_admission_does_not_write(client, monkeypatch):
    cid = await storage.create_conversation(TEST_OWNER)
    from features.chat.conversations import update
    @asynccontextmanager
    async def slot(owner):
        await update(owner, cid, archived=True)
        yield
    monkeypatch.setattr(service.admission, 'slot', slot)
    events = await read_events(await client.post('/api/chat', json={'conversation_id': cid, 'message': 'Chưa được ghi'}))
    assert any(e['type'] == 'error' and 'lưu trữ' in e['message'] for e in events)
    assert not await storage.get_messages(TEST_OWNER, cid)


async def test_archive_while_reading_attachment_does_not_write(client, monkeypatch):
    cid = await storage.create_conversation(TEST_OWNER)
    from features.chat.conversations import update
    from features.documents.reader import result
    async def reader(data, mime):
        await update(TEST_OWNER, cid, archived=True)
        return result('ready', 'Đã đọc', 'Nội dung thử')
    monkeypatch.setattr(service.document_reader, 'read_document', reader)
    events = await read_events(await client.post('/api/chat', json={'conversation_id':cid, 'message':'Đọc tệp',
        'attachments':[{'name':'test.txt','mime':'text/plain','data':base64.b64encode(b'noi dung thu').decode()}]}))
    assert any(e['type'] == 'error' and 'lưu trữ' in e['message'] for e in events)
    assert not await storage.get_messages(TEST_OWNER, cid)


async def test_backup_restore_keeps_archive_status(tmp_path, monkeypatch):
    from ops.backup import create_backup, restore_backup
    from features.chat.conversations import update
    database=tmp_path/'archive-backup.db'
    monkeypatch.setattr(connection, 'DB_PATH', database)
    await storage.init_db()
    cid=await storage.create_conversation(TEST_OWNER, 'Chat đã xong')
    await storage.add_message(cid, 'user', 'Giữ cả trạng thái và nội dung')
    await update(TEST_OWNER, cid, archived=True)
    backup=create_backup(database, tmp_path/'uploads', tmp_path/'backups', offline=True)
    await update(TEST_OWNER, cid, archived=False)
    restore_backup(backup, tmp_path/'restored')
    monkeypatch.setattr(connection, 'DB_PATH', tmp_path/'restored/database/peto_web.db')
    await storage.init_db()
    assert not await storage.list_conversations(TEST_OWNER)
    assert (await storage.list_conversations(TEST_OWNER, archived=True))[0]['id'] == cid
    assert (await storage.get_messages(TEST_OWNER, cid))[0]['content'] == 'Giữ cả trạng thái và nội dung'


async def test_old_database_migrates_archive_without_losing_messages(tmp_path, monkeypatch):
    database = tmp_path / 'old-archive.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL DEFAULT "", created_at REAL NOT NULL, updated_at REAL NOT NULL)')
        db.execute('INSERT INTO conversations VALUES(?,?,?,?,?)', ('old', TEST_OWNER, 'Chat trước nâng cấp', 1, 2))
    monkeypatch.setattr(connection, 'DB_PATH', database)
    await storage.init_db()
    await storage.add_message('old', 'user', 'Giữ tin nhắn')
    await storage.init_db()
    rows = await storage.list_conversations(TEST_OWNER)
    assert rows[0]['id'] == 'old' and not rows[0]['archived']
    assert (await storage.get_messages(TEST_OWNER, 'old'))[0]['content'] == 'Giữ tin nhắn'

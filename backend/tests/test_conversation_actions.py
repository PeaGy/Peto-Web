import sqlite3

import storage as db
from storage import connection as db_connection
from features.chat import conversations as conversation_actions
from conftest import TEST_OWNER, read_events


async def seed(owner=TEST_OWNER):
    cid = await db.create_conversation(owner, 'Bài học', mode='chat')
    user = await db.add_message(cid, 'user', 'nội dung ẩn needle-573')
    await db.add_message(cid, 'assistant', 'bản trả lời cũ')
    await db.add_message(cid, 'user', 'tin phía sau')
    return cid, user


async def test_search_rename_pin_and_ownership(client):
    cid, _ = await seed()
    other, _ = await seed('conversation-actions-other-owner')
    result = (await client.get('/api/conversations', params={'q':'needle-573'})).json()['conversations']
    assert cid in [r['id'] for r in result]
    assert cid in [r['id'] for r in (await client.get('/api/conversations', params={'q':'NOI DUNG AN'})).json()['conversations']]
    assert other not in [r['id'] for r in result]
    assert (await client.patch(f'/api/conversations/{cid}', json={'title':'Tên riêng', 'pinned':True})).status_code == 200
    result = (await client.get('/api/conversations', params={'q':'Tên riêng'})).json()['conversations']
    assert result[0]['id'] == cid and result[0]['pinned']
    assert result[0]['title_state'] == 'locked'
    assert (await client.patch(f'/api/conversations/{other}', json={'title':'bad'})).status_code == 404
    assert (await client.get(f'/api/conversations/{other}/versions')).status_code == 404
    assert (await client.patch(f'/api/conversations/{cid}', json={'title':'   '})).status_code == 400
    await client.patch(f'/api/conversations/{cid}', json={'pinned':False})


async def test_edit_stream_keeps_original_and_excludes_future(client):
    cid, uid = await seed()
    response = await client.post('/api/chat', json={'conversation_id':cid,'branch_message_id':uid,'message':'Nội dung đã sửa'})
    events = await read_events(response)
    meta = next(e for e in events if e['type']=='meta')
    assert meta['conversation_id'] != cid
    original = await db.get_messages(TEST_OWNER, cid)
    assert len(original) == 3 and original[0]['content'] == 'nội dung ẩn needle-573'
    branch = await db.get_messages(TEST_OWNER, meta['conversation_id'])
    assert [m['role'] for m in branch] == ['user','assistant']
    assert branch[0]['content'] == 'Nội dung đã sửa'
    assert len((await client.get(f'/api/conversations/{cid}/versions')).json()['versions']) == 2
    assert (await client.post('/api/chat', json={'conversation_id':cid,'branch_message_id':original[1]['id'],'message':'bad'})).status_code == 404


async def test_branch_copies_files_and_documents_independently(client, tmp_path):
    cid = await db.create_conversation(TEST_OWNER, 'Có tệp')
    first = await db.add_message(cid, 'user', 'tạo tài liệu')
    with sqlite3.connect(db_connection.DB_PATH) as c:
        c.execute('INSERT INTO chat_documents VALUES(?,?,?,?)', ('doc-branch-test',TEST_OWNER,cid,1))
        c.execute('INSERT INTO chat_document_versions(document_id,version,title,content,created_at,style) VALUES(?,?,?,?,?,?)', ('doc-branch-test',1,'Doc','hello',1,'report'))
    await db.add_message(cid, 'assistant', 'Đã tạo', artifacts=[{'id':'doc-branch-test','version':1,'filename':'a.docx'}])
    target = await db.add_message(cid, 'user', 'sửa tài liệu')
    path = tmp_path / 'source.txt'
    path.write_text('file content')
    await db.add_attachment(attachment_id='branch-file',owner=TEST_OWNER,conversation_id=cid,message_id=first,filename='source.txt',mime='text/plain',kind='file',size=12,path=str(path))
    branch_id, _ = await conversation_actions.fork(TEST_OWNER,cid,target,'sửa lại')
    rows = await db.get_messages(TEST_OWNER,branch_id)
    assert rows[0]['attachments'][0]['path'] != str(path)
    assert rows[1]['artifacts'][0]['id'] != 'doc-branch-test'
    assert rows[1]['generated_documents'][0]['content'] == 'hello'
    await db.delete_conversation(TEST_OWNER,cid)
    from pathlib import Path
    assert Path(rows[0]['attachments'][0]['path']).read_text() == 'file content'
    assert (await db.get_messages(TEST_OWNER,branch_id))[1]['artifacts']


async def test_invalid_fork_rolls_back(client):
    cid, uid = await seed()
    before = await db.list_conversations(TEST_OWNER, 1000)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await conversation_actions.fork('other-owner',cid,uid,'no')
    assert len(await db.list_conversations(TEST_OWNER,1000)) == len(before)

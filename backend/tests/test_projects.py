"""Dự án giữ quyền riêng tư, lịch sử và ngữ cảnh chỉ của tài liệu được chọn."""
import base64
import json
import pytest
from features.accounts import auth
from features.chat import service, conversations
from features.projects import api as project_api
from features.projects.context import context, MAX_CONTEXT_CHARS
from features.documents.reader import result
from shared.attachments import ValidatedAttachment
from storage import projects
import storage
from core.config import SESSION_COOKIE
from conftest import TEST_OWNER, OTHER_DISCORD_ID


async def create(client, name='Báo cáo phần mềm'):
    response = await client.post('/api/projects', json={'name': name})
    assert response.status_code == 200, response.text
    return response.json()['id']


def upload_body(text='Nội dung tài liệu riêng', name='notes.txt'):
    return {'name':name, 'mime':'text/plain', 'data':base64.b64encode(text.encode()).decode()}


@pytest.fixture
async def other(anon_client):
    owner=f'discord:{OTHER_DISCORD_ID}'
    await storage.upsert_user(owner=owner,provider='discord',username='other',display_name='Người khác',avatar_url='')
    anon_client.cookies.set(SESSION_COOKIE,auth._sign(owner))
    return anon_client


async def test_project_crud_and_delete_keep_conversations(client):
    project_id=await create(client)
    await client.patch(f'/api/projects/{project_id}',json={'name':'Công việc','instructions':'Trả lời ngắn bằng tiếng Việt'})
    conversation=await storage.create_conversation(TEST_OWNER,title='Chat cũ')
    await storage.add_message(conversation,'user','Giữ lịch sử')
    response=await client.patch(f'/api/conversations/{conversation}',json={'project_id':project_id})
    assert response.status_code == 200
    assert not (await client.get('/api/conversations?unassigned=true')).json()['conversations'] or all(c['id']!=conversation for c in (await client.get('/api/conversations?unassigned=true')).json()['conversations'])
    scoped=(await client.get(f'/api/conversations?project_id={project_id}')).json()['conversations']
    assert [row['id'] for row in scoped]==[conversation]
    detail=(await client.get(f'/api/projects/{project_id}')).json()
    assert detail['name']=='Công việc' and detail['instructions'].startswith('Trả lời')
    assert (await client.delete(f'/api/projects/{project_id}')).status_code==200
    assert (await storage.conversation_settings(TEST_OWNER,conversation))['project_id'] is None
    assert (await storage.get_messages(TEST_OWNER,conversation))[0]['content']=='Giữ lịch sử'


async def test_projects_require_login(anon_client):
    for method,path,body in [('GET','/api/projects',None),('POST','/api/projects',{'name':'Không được'}),('GET','/api/projects/fake',None)]:
        response=await anon_client.request(method,path,json=body)
        assert response.status_code==401


async def test_cross_owner_project_file_and_move_are_404(client,other,monkeypatch):
    monkeypatch.setattr(project_api,'read_document',fake_reader)
    project_id=await create(client)
    file_id=(await client.post(f'/api/projects/{project_id}/files',json=upload_body())).json()['id']
    conversation=await storage.create_conversation(TEST_OWNER)
    alien_conversation=await storage.create_conversation(f'discord:{OTHER_DISCORD_ID}')
    assert project_id not in [p['id'] for p in (await other.get('/api/projects')).json()['projects']]
    for method,path,body in [('GET',f'/api/projects/{project_id}',None),('PATCH',f'/api/projects/{project_id}',{'name':'Sai'}),('DELETE',f'/api/projects/{project_id}',None),('GET',f'/api/projects/{project_id}/files/{file_id}',None),('DELETE',f'/api/projects/{project_id}/files/{file_id}',None),('POST',f'/api/projects/{project_id}/files',upload_body()),('GET',f'/api/conversations?project_id={project_id}',None),('PATCH',f'/api/conversations/{conversation}',{'project_id':None}),('PATCH',f'/api/conversations/{alien_conversation}',{'project_id':project_id})]:
        assert (await other.request(method,path,json=body)).status_code==404
    assert (await client.get(f'/api/projects/{project_id}/files/{file_id}')).status_code==200


async def fake_reader(data,mime):
    return result('ready','Đã đọc tệp chữ.',data.decode())


async def test_file_upload_public_metadata_download_limits_and_delete(client,monkeypatch):
    monkeypatch.setattr(project_api,'read_document',fake_reader)
    monkeypatch.setattr(projects,'MAX_FILES',1)
    project_id=await create(client)
    upload=await client.post(f'/api/projects/{project_id}/files',json=upload_body('Chữ không trả trong metadata'))
    file_id=upload.json()['id']
    detail=(await client.get(f'/api/projects/{project_id}')).json()
    assert 'text' not in detail['files'][0]['document'] and 'data' not in detail['files'][0]
    download=await client.get(detail['files'][0]['url'])
    assert download.text=='Chữ không trả trong metadata' and download.headers['cache-control']=='private, no-store'
    assert (await client.post(f'/api/projects/{project_id}/files',json=upload_body())).status_code==400
    assert (await client.delete(f'/api/projects/{project_id}/files/{file_id}')).status_code==200
    assert (await client.get(f'/api/projects/{project_id}/files/{file_id}')).status_code==404


async def test_context_uses_only_selected_files_with_budget(client):
    project_id=await create(client)
    await projects.update_project(TEST_OWNER,project_id,instructions='Hướng dẫn của dự án')
    chosen=await projects.add_file(TEST_OWNER,project_id,ValidatedAttachment('chosen.txt','text/plain','file',b'ok'),result('ready','Đã đọc','X'*(MAX_CONTEXT_CHARS+100)))
    await projects.add_file(TEST_OWNER,project_id,ValidatedAttachment('hidden.txt','text/plain','file',b'ok'),result('ready','Đã đọc','KHONG_DUOC_GUI'))
    no_files=await context(TEST_OWNER,project_id,[])
    assert 'Hướng dẫn của dự án' in no_files and 'chosen.txt' not in no_files
    prompt=await context(TEST_OWNER,project_id,[chosen,chosen])
    assert prompt.count('chosen.txt')==1 and 'KHONG_DUOC_GUI' not in prompt
    assert prompt.count('X')==MAX_CONTEXT_CHARS and 'bị cắt' in prompt


async def test_chat_project_context_and_branch_preserve_project(client,monkeypatch):
    from ai.base import StreamChunk
    captured=[]
    class Provider:
        async def stream(self,**kwargs):
            captured.append(kwargs['system_prompt'])
            yield StreamChunk('text','Đã trả lời')
    monkeypatch.setattr(service,'get_provider',lambda model='peto':Provider())
    project_id=await create(client)
    await projects.update_project(TEST_OWNER,project_id,instructions='CHI_DAN_DU_AN')
    file_id=await projects.add_file(TEST_OWNER,project_id,ValidatedAttachment('guide.txt','text/plain','file',b'guide'),result('ready','Đã đọc','TAI_LIEU_DUOC_CHON'))
    response=await client.post('/api/chat',json={'message':'Chào','project_id':project_id,'project_file_ids':[file_id]})
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    meta=next(event for event in events if event['type']=='meta')
    conversation=meta['conversation_id']
    assert (await storage.conversation_settings(TEST_OWNER,conversation))['project_id']==project_id
    assert any('CHI_DAN_DU_AN' in prompt and 'TAI_LIEU_DUOC_CHON' in prompt for prompt in captured)
    fork,_=await conversations.fork(TEST_OWNER,conversation,meta['message']['id'],'Sửa câu hỏi')
    assert (await storage.conversation_settings(TEST_OWNER,fork))['project_id']==project_id
    settings=(await client.get(f'/api/conversations/{fork}/messages')).json()
    assert settings['project_id']==project_id


async def test_invalid_project_context_is_rejected_before_writing(client):
    project_id=await create(client)
    other_project=await create(client,'Dự án khác')
    conversation=await storage.create_conversation(TEST_OWNER,project_id=project_id)
    for body,status in [({'message':'Sai','project_id':'missing'},404),({'message':'Sai','project_file_ids':['missing']},400),({'message':'Sai','project_id':project_id,'mode':'companion'},400),({'message':'Sai','conversation_id':conversation,'project_id':other_project},400),({'message':'Sai','project_id':project_id,'project_file_ids':['missing']},404),({'message':'Sai','project_id':project_id,'project_file_ids':['1']*5},422)]:
        assert (await client.post('/api/chat',json=body)).status_code==status
    assert await storage.get_messages(TEST_OWNER,conversation)==[]
    companion=await storage.create_conversation(TEST_OWNER,mode='companion')
    assert (await client.patch(f'/api/conversations/{companion}',json={'project_id':project_id})).status_code==404


async def test_move_during_document_read_does_not_write_stale_project_turn(client,monkeypatch):
    project_id=await create(client)
    conversation=await storage.create_conversation(TEST_OWNER,project_id=project_id)
    async def move_while_reading(data,mime):
        await projects.move_conversation(TEST_OWNER,conversation,None)
        return await fake_reader(data,mime)
    monkeypatch.setattr(service.document_reader,'read_document',move_while_reading)
    response=await client.post('/api/chat',json={'message':'Đọc tệp','conversation_id':conversation,'project_id':project_id,'attachments':[upload_body()]})
    assert 'Hội thoại đã chuyển dự án' in response.text
    assert await storage.get_messages(TEST_OWNER,conversation)==[]


async def test_legacy_schema_migration_preserves_chat_and_is_repeatable(tmp_path):
    import aiosqlite
    async with aiosqlite.connect(tmp_path/'legacy.db') as connection:
        await connection.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY, owner TEXT, title TEXT)')
        await connection.execute('INSERT INTO conversations VALUES(?,?,?)',('old',TEST_OWNER,'Chat trước khi có dự án'))
        await projects.init_tables(connection)
        await projects.init_tables(connection)
        row=await (await connection.execute('SELECT id,title,project_id FROM conversations')).fetchone()
        assert row==('old','Chat trước khi có dự án',None)


async def test_project_limits_and_files_from_other_owned_project(client,monkeypatch):
    monkeypatch.setattr(project_api,'read_document',fake_reader)
    assert (await client.post('/api/projects',json={'name':'   '})).status_code==400
    first=await create(client)
    second=await create(client,'Dự án thứ hai')
    file_id=(await client.post(f'/api/projects/{first}/files',json=upload_body())).json()['id']
    assert (await client.post('/api/chat',json={'message':'Sai tệp','project_id':second,'project_file_ids':[file_id]})).status_code==404
    monkeypatch.setattr(projects,'MAX_PROJECTS',2)
    assert (await client.post('/api/projects',json={'name':'Vượt số dự án'})).status_code==400
    assert (await client.patch(f'/api/projects/{first}',json={'instructions':'x'*8001})).status_code==422
    monkeypatch.setattr(projects,'MAX_BYTES',1)
    assert (await client.post(f'/api/projects/{second}/files',json=upload_body())).status_code==400


async def test_deleted_project_in_backup_keeps_live_data_independent(client,tmp_path,monkeypatch):
    from ops.backup import create_backup,restore_backup
    from storage import connection,schema
    database=tmp_path/'project.db'
    monkeypatch.setattr(connection,'DB_PATH',database)
    await schema.init_db()
    project_id=await projects.create_project(TEST_OWNER,'Thử phục hồi')
    file_id=await projects.add_file(TEST_OWNER,project_id['id'],ValidatedAttachment('keep.txt','text/plain','file','Giữ tệp'.encode()),result('ready','Đã đọc','Giữ tệp'))
    archive=create_backup(database,tmp_path/'uploads',tmp_path/'backups',offline=True)
    await projects.delete_project(TEST_OWNER,project_id['id'])
    restore_backup(archive,tmp_path/'restored')
    monkeypatch.setattr(connection,'DB_PATH',tmp_path/'restored/database/peto_web.db')
    await schema.init_db()
    assert (await projects.get_file(TEST_OWNER,project_id['id'],file_id,data=True))['data']=='Giữ tệp'.encode()

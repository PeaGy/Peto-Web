"""Mỗi nhóm phiên bản là một cuộc trò chuyện ở thanh bên, như ChatGPT và Claude (22/11/2026: bấm "Thử lại" hai lần trên
"Màu sắc Part 4 và Morioh" thành ba dòng trùng tên). Đổi tên, ghim, lưu trữ, chuyển dự án và xóa áp cho cả nhóm."""
import storage as db
from storage import connection
from conftest import TEST_OWNER, read_events

QUESTION = 'Sao Gyro còn sống?'


async def chat_with_two_retries(client):
    events = await read_events(await client.post('/api/chat', json={'message': QUESTION, 'web_search': 'off'}))
    original = events[0]['conversation_id']
    question = (await db.get_messages(TEST_OWNER, original))[0]['id']
    forks = []
    for _ in range(2):
        events = await read_events(await client.post('/api/chat', json={
            'conversation_id': original, 'branch_message_id': question, 'message': QUESTION, 'web_search': 'off'}))
        assert events[-1]['type'] == 'done', events
        forks.append(next(e for e in events if e['type'] == 'meta')['conversation_id'])
    assert len({original, *forks}) == 3
    return original, forks


async def stored(cid):
    async with connection.connect() as conn:
        return await (await conn.execute('SELECT title, pinned FROM conversations WHERE id=?', (cid,))).fetchone()


async def rows(client, **params):
    return (await client.get('/api/conversations', params=params)).json()['conversations']


async def test_retries_show_as_one_sidebar_row_for_the_newest_version(client):
    original, forks = await chat_with_two_retries(client)
    listed = await rows(client)
    group = [row for row in listed if {original, *forks} & set(row['version_ids'])]
    assert [row['id'] for row in group] == [forks[-1]]
    assert sorted(group[0]['version_ids']) == sorted([original, *forks])
    # Tìm kiếm cũng chỉ thấy một dòng.
    assert [row['id'] for row in await rows(client, q='Gyro') if row['id'] in {original, *forks}] == [forks[-1]]
    # Hội thoại không có bản nào khác vẫn là chính nó.
    plain = await db.create_conversation(TEST_OWNER, 'Một mình')
    assert {row['id']: row['version_ids'] for row in await rows(client)}[plain] == [plain]


async def test_rename_pin_archive_and_move_apply_to_every_version(client):
    original, forks = await chat_with_two_retries(client)
    ids = [original, *forks]
    assert (await client.patch(f'/api/conversations/{original}', json={'title': 'Arc Ringo'})).status_code == 200
    assert (await client.patch(f'/api/conversations/{original}', json={'pinned': True})).status_code == 200
    for cid in ids:
        assert tuple(await stored(cid)) == ('Arc Ringo', 1)
    # Bản tách mới giữ ghim, nên dòng của nhóm không rơi khỏi mục ghim sau một lần "Thử lại" nữa.
    question = (await db.get_messages(TEST_OWNER, forks[-1]))[0]['id']
    events = await read_events(await client.post('/api/chat', json={
        'conversation_id': forks[-1], 'branch_message_id': question, 'message': QUESTION, 'web_search': 'off'}))
    newest = next(e for e in events if e['type'] == 'meta')['conversation_id']
    listed = await rows(client)
    assert [(row['id'], row['pinned']) for row in listed if row['title'] == 'Arc Ringo'] == [(newest, 1)]
    ids.append(newest)

    project = (await client.post('/api/projects', json={'name': 'Steel Ball Run'})).json()['id']
    assert (await client.patch(f'/api/conversations/{original}', json={'project_id': project})).status_code == 200
    assert [row['id'] for row in await rows(client, project_id=project)] == [newest]
    assert not {row['id'] for row in await rows(client, unassigned=True)} & set(ids)

    assert (await client.patch(f'/api/conversations/{forks[0]}', json={'archived': True})).status_code == 200
    assert await rows(client, project_id=project) == []
    archived = [row for row in await rows(client, archived=True) if row['title'] == 'Arc Ringo']
    assert [row['id'] for row in archived] == [newest] and sorted(archived[0]['version_ids']) == sorted(ids)
    assert (await client.patch(f'/api/conversations/{newest}', json={'archived': False})).status_code == 200
    assert [row['id'] for row in await rows(client, project_id=project)] == [newest]
    # Dữ liệu test dùng chung: không để lại dòng ghim đứng đầu danh sách của test khác.
    assert (await client.delete(f'/api/conversations/{original}')).status_code == 200


async def test_delete_removes_every_version(client, anon_client):
    original, forks = await chat_with_two_retries(client)
    other = await db.create_conversation(TEST_OWNER, 'Giữ lại')
    # Người khác không xóa được, kể cả khi biết mã.
    assert (await anon_client.delete(f'/api/conversations/{original}')).status_code in {401, 404}
    assert (await client.delete(f'/api/conversations/{original}')).json() == {'deleted': True}
    for cid in [original, *forks]:
        assert await db.conversation_settings(TEST_OWNER, cid) is None
        assert await db.get_messages(TEST_OWNER, cid) == []
    listed = {row['id'] for row in await rows(client)}
    assert other in listed and not listed & {original, *forks}
    assert (await client.delete(f'/api/conversations/{original}')).status_code == 404

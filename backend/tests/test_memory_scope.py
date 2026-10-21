"""Phạm vi ghi nhớ dùng chung và chống kết quả nền cũ ghi lại dữ liệu đã đổi/xóa."""
import uuid
import pytest
import storage as db
from storage import chat_turns, connection, projects
from features.companion import memory


def entry(detail='Sở thích đã lưu'):
    return memory.new_entry('topic', 'Dữ liệu thử', '', [detail])


@pytest.mark.parametrize('change', ['off_on', 'clear', 'manual_edit', 'delete_chat', 'move_project', 'edit_source'])
async def test_background_result_is_discarded_when_memory_epoch_or_source_changes(client, monkeypatch, change):
    owner = 'discord:scope-' + uuid.uuid4().hex
    project = await projects.create_project(owner, 'Dự án nguồn')
    other_project = await projects.create_project(owner, 'Dự án đích')
    cid = await db.create_conversation(owner, project_id=project['id'])
    uid = await db.add_message(cid, 'user', 'Mình thích trà gừng và đang học thiết kế giao diện, đây là dữ liệu giả.')
    await db.ensure_memory_state(owner)
    old = (await db.apply_memory_changes(owner, upserts=[entry()], remove=[], limit=10))[0]
    before = await db.memory_state(owner)
    async def ask(*args):
        if change == 'off_on':
            await db.set_memory_enabled(owner, False)
            await db.set_memory_enabled(owner, True)
        elif change == 'clear':
            await db.clear_memories(owner)
        elif change == 'manual_edit':
            await db.apply_memory_changes(owner, upserts=[{'id': old['id'], 'details': ['Sửa tay mới nhất']}], remove=[], limit=10)
        elif change == 'delete_chat':
            await db.delete_conversation(owner, cid)
        elif change == 'move_project':
            await projects.move_conversation(owner, cid, other_project['id'])
        else:
            async with connection.connect() as sql:
                await sql.execute('UPDATE messages SET content=? WHERE id=?', ('Dữ kiện đã sửa', uid))
                await sql.commit()
        return '{"entries":[{"section":"topic","title":"Kết quả cũ","details":["Không được lưu lại"]}],"remove":[]}'
    monkeypatch.setattr(memory, '_ask', ask)
    monkeypatch.setattr(memory, 'COMPANION_MEMORY_ENABLED', True)
    monkeypatch.setattr(memory, 'MIN_NEW_CHARS', 1)
    await memory._remember_once(owner)
    entries = await db.list_memories(owner)
    assert not any(item['title'] == 'Kết quả cũ' for item in entries)
    if change == 'clear':
        assert entries == []
    elif change == 'manual_edit':
        assert entries[0]['details'] == ['Sửa tay mới nhất']
    else:
        assert entries[0]['details'] == ['Sở thích đã lưu']
    if change == 'clear':
        state = await db.memory_state(owner)
        assert state['cursor'] >= uid
        assert await db.memory_messages_after(owner, state['cursor'], 30) == []
    elif change != 'off_on':
        assert (await db.memory_state(owner))['cursor'] == before['cursor']


async def test_completed_chat_and_companion_share_personal_memory_but_failed_chat_is_not_extracted(client):
    owner = 'discord:scope-' + uuid.uuid4().hex
    chat = await db.create_conversation(owner)
    rid = uuid.uuid4().hex
    await chat_turns.reserve(owner, rid)
    failed = await chat_turns.bind(owner, rid, chat, None, 'Thông tin trong lượt lỗi')
    await chat_turns.persist(owner, rid, content='', state='error')
    complete = await db.add_message(chat, 'user', 'Sở thích từ Chat')
    companion = await db.create_conversation(owner, mode='companion')
    companion_user = await db.add_message(companion, 'user', 'Sở thích từ Companion')
    rows = await db.memory_messages_after(owner, 0, 30)
    assert failed not in [row['id'] for row in rows]
    assert {complete, companion_user} <= {row['id'] for row in rows}
    await db.apply_memory_changes(owner, upserts=[entry()], remove=[], limit=10)
    assert 'Sở thích đã lưu' in await memory.chat_memory_block(owner)
    assert 'Sở thích đã lưu' in await memory.memory_block(owner, companion)
    await db.delete_conversation(owner, chat)
    assert (await db.list_memories(owner))[0]['details'] == ['Sở thích đã lưu']
    assert await db.list_memories('discord:other') == []


async def test_companion_summary_cannot_return_after_off_on_or_source_delete(client):
    owner = 'discord:scope-' + uuid.uuid4().hex
    cid = await db.create_conversation(owner, mode='companion')
    uid = await db.add_message(cid, 'user', 'Dữ liệu tóm tắt giả')
    await db.add_message(cid, 'assistant', 'Dữ liệu mới')
    state = await db.ensure_memory_state(owner)
    source = await db.messages_before_window(owner, cid, after_id=0, window=1, limit=10)
    assert source[0]['id'] == uid
    await db.set_memory_enabled(owner, False)
    await db.set_memory_enabled(owner, True)
    assert not await db.save_companion_summary(owner, cid, text='Không được ghi', upto=uid, expected_upto=None,
        expected_revision=state['revision'], source_rows=source)
    state = await db.memory_state(owner)
    await db.delete_conversation(owner, cid)
    assert not await db.save_companion_summary(owner, cid, text='Không tái tạo chat đã xóa', upto=uid, expected_upto=None,
        expected_revision=state['revision'], source_rows=source)


async def test_memory_cursor_does_not_skip_a_concurrent_running_checkpoint(client):
    owner = 'discord:scope-' + uuid.uuid4().hex
    first = await db.create_conversation(owner)
    rid = uuid.uuid4().hex
    await chat_turns.reserve(owner, rid)
    uid = await chat_turns.bind(owner, rid, first, None, 'Câu đang chạy')
    await chat_turns.persist(owner, rid, content='Checkpoint còn dở')
    second = await db.create_conversation(owner)
    later = await db.add_message(second, 'user', 'Câu đã xong ở chat khác')
    assert await db.memory_messages_after(owner, 0, 30) == []
    await chat_turns.persist(owner, rid, content='Đã xong câu trước', state='complete')
    ids = [row['id'] for row in await db.memory_messages_after(owner, 0, 30)]
    assert uid in ids and later in ids

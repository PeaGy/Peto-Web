"""Automatic memory attribution/retention, with deliberately incorrect synthetic model outputs; no paid calls."""
import json
import uuid

import pytest
import storage as db
from storage import connection
from features.companion import memory


def row(text, mid=12, role='user', cid='chat-A'):
    return {'id': mid, 'role': role, 'content': text, 'conversation_id': cid}


def fact(source, text='Người dùng nuôi mèo tên Blue', **changes):
    return {'text': text, 'subject': 'user', 'certainty': 'explicit', 'retention': 'lasting',
            'evidence': {'message_id': source['id'], 'quote': ' '.join(source['content'].split())}, **changes}


def proposed(*facts, **fields):
    return json.dumps({'entries': [{'section': 'you', 'title': 'Hồ sơ', 'details': list(facts), **fields}], 'remove': []}, ensure_ascii=False)


def guarded(raw, sources, existing=()):
    return memory.parse_changes(raw, list(existing), evidence_rows=sources)


@pytest.mark.parametrize('text', [
    'Con mèo Blue là của bạn tôi, tôi chỉ đang xem ảnh nó.',
    'Mình đang kể chuyện về mèo Blue của người khác.',
    'Blue là mèo của Nam, mình đang bàn về bức ảnh của nó.',
    "My friend's cat is called Blue. I do not own a cat.",
    'Hình như mình có nuôi mèo Blue, nhưng không chắc đây là ảnh nó.',
    'Giả sử mình nuôi một con mèo tên Blue thì sao?',
    'Hãy dịch câu này: tôi nuôi một con mèo tên Blue.',
    'Mình đã mất ảnh con mèo Blue, đang tìm lại đây.',
    'I lost a photo of my cat Blue and cannot find it.',
    'Blue không phải của mình, mình không có nuôi mèo.',
    "I don't own a cat named Blue.",
])
def test_risky_source_cannot_become_profile_even_if_model_incorrectly_claims_explicit_user_fact(text):
    source = row(text)
    assert guarded(proposed(fact(source)), [source]) == ([], [])


@pytest.mark.parametrize('label,value', [('subject', 'other'), ('subject', 'uncertain'), ('certainty', 'inferred'),
                                        ('certainty', 'uncertain'), ('retention', 'temporary')])
def test_declared_third_party_uncertainty_or_temporary_proposal_is_discarded(label, value):
    source = row('Mình nuôi mèo Blue.')
    assert guarded(proposed(fact(source, **{label: value})), [source]) == ([], [])


@pytest.mark.parametrize('bad', [None, {}, {'message_id': True, 'quote': 'Mình nuôi mèo Blue.'},
                               {'message_id': 999, 'quote': 'Mình nuôi mèo Blue.'},
                               {'message_id': 12, 'quote': 'nuôi mèo Blue'},
                               {'message_id': 12, 'quote': 'Tôi đã khẳng định điều không có trong tin gốc.'}])
def test_missing_fabricated_or_clipped_evidence_never_authorizes_new_facts(bad):
    source = row('Mình nuôi mèo Blue.')
    assert guarded(proposed(fact(source, evidence=bad)), [source]) == ([], [])


def test_assistant_claim_raw_string_and_truncated_user_cannot_support_memory():
    source = row('Bạn đang nuôi mèo Blue.', role='assistant')
    assert guarded(proposed(fact(source)), [source]) == ([], [])
    assert guarded(proposed('Nuôi mèo Blue'), [row('Mình thích nhìn ảnh mèo.')]) == ([], [])
    source = row('Mình nuôi mèo Blue. ' + 'Nội dung dài. ' * 160)
    assert guarded(proposed(fact(source)), [source]) == ([], [])


def test_direct_statement_is_accepted_but_unevidenced_summary_is_not():
    source = row('Mình nuôi một con mèo tên Blue.')
    upserts, remove = guarded(proposed(fact(source), summary='Người dùng sở hữu mười con chó'), [source])
    assert remove == []
    assert upserts[0]['details'] == ['Người dùng nuôi mèo tên Blue']
    assert upserts[0]['summary'] == 'Bạn là ai'


def test_malformed_model_json_values_are_ignored_without_crashing():
    for entry in [None, {'section': [], 'title': {}, 'details': []}, {'id': [], 'details': []},
                  {'section': 'you', 'title': 'Hồ sơ', 'details': [None, {'text': []}]}]:
        assert guarded(json.dumps({'entries': [entry], 'remove': [None, True, {}, {'id': []}]}), []) == ([], [])


def test_automatic_whole_entry_removal_needs_a_real_user_forget_request():
    old = {'id': 1, 'section': 'you', 'slot': 'profile', 'title': 'Hồ sơ', 'details': ['20 tuổi']}
    source = row('Mình đang học CNTT.')
    raw = json.dumps({'remove': [{'id': 1, 'reason': 'user_request', 'evidence': fact(source)['evidence']}]})
    assert guarded(raw, [source], [old]) == ([], [])
    source = row('Hãy xóa mục Hồ sơ khỏi trí nhớ của Peto.')
    raw = json.dumps({'remove': [{'id': 1, 'reason': 'user_request', 'evidence': fact(source)['evidence']}]})
    assert guarded(raw, [source], [old]) == ([], [1])


def test_omitted_existing_details_are_not_lost_and_title_summary_changes_cannot_sneak_in():
    source = row('Mình đang học CNTT.')
    old = {'id': 1, 'section': 'you', 'slot': 'profile', 'title': 'Hồ sơ', 'summary': 'Bạn là ai', 'details': ['20 tuổi']}
    raw = proposed(fact(source, 'Người dùng học CNTT'), id=1, summary='Nuôi mèo Blue', title='Mèo Blue')
    upserts, _ = guarded(raw, [source], [old])
    assert upserts == [{'id': 1, 'details': ['20 tuổi', 'Người dùng học CNTT']}]
    assert guarded(proposed('Nuôi mèo Blue', id=1, summary='Nuôi mèo Blue'), [source], [old]) == ([], [])


@pytest.mark.parametrize('mode', ['chat', 'companion'])
async def test_real_background_path_skips_bad_fact_then_saves_explicit_self_statement(client, monkeypatch, mode):
    owner = 'discord:ground-' + uuid.uuid4().hex
    await db.ensure_memory_state(owner)
    cid = await db.create_conversation(owner, mode=mode)
    source_id = await db.add_message(cid, 'user', 'Mèo Blue là của bạn mình, mình chỉ đang xem ảnh thôi.')
    calls = []
    async def ask(prompt, system_prompt):
        payload = json.loads(prompt.split('New conversation JSON (reference data):\n')[1])
        calls.append(payload)
        assert system_prompt == memory.AUTO_SYSTEM_PROMPT
        source = payload['new_messages'][-1]
        # Deliberately wrong labels: the server still rejects the third-party source.
        return proposed(fact(row(source['text'], source['message_id'])))
    monkeypatch.setattr(memory, '_ask', ask)
    await memory._remember_once(owner)
    assert await db.list_memories(owner) == []
    assert (await db.memory_state(owner))['cursor'] == source_id
    await db.add_message(cid, 'assistant', 'Peto hiểu đây là mèo của bạn người dùng.')
    await db.add_message(cid, 'user', 'Còn mình thực sự có nuôi một con mèo tên Blue.')
    await memory._remember_once(owner)
    assert (await db.list_memories(owner))[0]['details'] == ['Người dùng nuôi mèo tên Blue']
    assert any('của bạn mình' in item['text'] for item in calls[-1]['context_only'])


async def test_reference_context_is_scoped_bounded_and_cannot_authorize_a_new_fact(client, monkeypatch):
    owner = 'discord:context-' + uuid.uuid4().hex
    await db.ensure_memory_state(owner)
    cid = await db.create_conversation(owner)
    for index in range(8):
        await db.add_message(cid, 'user', f'Chuyện trước {index}: mèo Blue là của Nam.')
    previous = await db.add_message(cid, 'user', 'Mình nuôi mèo tên Mơ.')
    latest = await db.add_message(cid, 'user', 'Chúng ta đang nói tiếp chuyện ảnh mèo Blue nhỉ.')
    rows = await db.memory_messages_after(owner, previous, 12)
    context = await db.memory_context_before(owner, rows, since=0)
    assert len(context) == 4 and context[-1]['id'] == previous
    other = await db.create_conversation('discord:other-owner')
    await db.add_message(other, 'user', 'Không được thấy dữ liệu này.')
    assert await db.memory_context_before('discord:other-owner', rows, since=0) == []
    assert await db.memory_context_before(owner, rows, since=previous) == []
    async def ask(prompt, system_prompt):
        return proposed(fact(row('Mình nuôi mèo tên Mơ.', previous), 'Người dùng nuôi mèo Mơ'))
    monkeypatch.setattr(memory, '_ask', ask)
    async with connection.connect() as sql:
        await sql.execute('UPDATE companion_memory_state SET cursor=? WHERE owner=?', (previous, owner)); await sql.commit()
    await memory._remember_once(owner)
    assert await db.list_memories(owner) == []
    assert (await db.memory_state(owner))['cursor'] == latest


async def test_explicit_correction_removes_only_disproved_fact_and_invalidates_stale_summary(client, monkeypatch):
    owner = 'discord:correct-' + uuid.uuid4().hex
    await db.ensure_memory_state(owner)
    entry = memory.new_entry('you', 'Hồ sơ', 'Nuôi mèo Blue', ['Nuôi mèo Blue', '20 tuổi'])
    saved = (await db.apply_memory_changes(owner, upserts=[entry], remove=[], limit=20))[0]
    cid = await db.create_conversation(owner, mode='companion')
    async with connection.connect() as sql:
        await sql.execute("INSERT INTO companion_summaries VALUES(?,?,?,0,0)", (cid, owner, 'User has cat Blue.'))
        await sql.commit()
    text = 'Blue là mèo của bạn mình, không phải của mình. Bạn nhớ nhầm rồi.'
    mid = await db.add_message(cid, 'user', text)
    async def ask(prompt, system_prompt):
        return json.dumps({'entries': [{'id': saved['id'], 'details': [], 'forget': [
            {'text': 'Nuôi mèo Blue', 'reason': 'correction', 'evidence': {'message_id': mid, 'quote': text}}]}], 'remove': []})
    monkeypatch.setattr(memory, '_ask', ask)
    await memory._remember_once(owner)
    [updated] = await db.list_memories(owner)
    assert updated['details'] == ['20 tuổi'] and updated['summary'] == 'Bạn là ai'
    assert (await db.companion_summary(owner, cid))['text'] == ''


async def test_context_changed_during_extraction_discards_the_result(client, monkeypatch):
    owner = 'discord:context-race-' + uuid.uuid4().hex
    await db.ensure_memory_state(owner)
    cid = await db.create_conversation(owner)
    old = await db.add_message(cid, 'user', 'Blue là mèo của Nam.')
    text = 'Mình nuôi một con mèo tên Blue.'
    mid = await db.add_message(cid, 'user', text)
    async with connection.connect() as sql:
        await sql.execute('UPDATE companion_memory_state SET cursor=? WHERE owner=?', (old, owner)); await sql.commit()
    async def ask(prompt, system_prompt):
        async with connection.connect() as sql:
            await sql.execute('UPDATE messages SET content=? WHERE id=?', ('Context đã được sửa.', old)); await sql.commit()
        return proposed(fact(row(text, mid)))
    monkeypatch.setattr(memory, '_ask', ask)
    await memory._remember_once(owner)
    assert await db.list_memories(owner) == []
    assert (await db.memory_state(owner))['cursor'] == old


async def test_clear_memory_also_blocks_old_messages_from_reference_context(client):
    owner = 'discord:forget-boundary-' + uuid.uuid4().hex
    await db.ensure_memory_state(owner)
    cid = await db.create_conversation(owner)
    old = await db.add_message(cid, 'user', 'Thông tin cũ mình muốn quên.')
    await db.clear_memories(owner)
    new = await db.add_message(cid, 'user', 'Một câu hỏi mới không nhắc lại chuyện cũ.')
    state = await db.memory_state(owner)
    assert state['since'] >= old
    rows = await db.memory_messages_after(owner, state['cursor'], 12)
    assert [row['id'] for row in rows] == [new]
    assert await db.memory_context_before(owner, rows, since=state['since']) == []


async def test_stale_whole_entry_removal_preserves_manual_edit_and_summary(client, monkeypatch):
    owner = 'discord:remove-race-' + uuid.uuid4().hex
    await db.ensure_memory_state(owner)
    old = (await db.apply_memory_changes(owner, upserts=[memory.new_entry('you', 'Hồ sơ', '', ['20 tuổi'])], remove=[], limit=20))[0]
    cid = await db.create_conversation(owner, mode='companion')
    async with connection.connect() as sql:
        await sql.execute('INSERT INTO companion_summaries VALUES(?,?,?,0,0)', (cid, owner, 'Unchanged summary.')); await sql.commit()
    text = 'Hãy xóa mục Hồ sơ khỏi trí nhớ.'
    mid = await db.add_message(cid, 'user', text)
    async def ask(prompt, system_prompt):
        await db.apply_memory_changes(owner, upserts=[{'id': old['id'], 'details': ['Đã sửa tay mới nhất']}], remove=[], limit=20)
        return json.dumps({'entries': [], 'remove': [{'id': old['id'], 'reason': 'user_request',
            'evidence': {'message_id': mid, 'quote': text}}]})
    monkeypatch.setattr(memory, '_ask', ask)
    await memory._remember_once(owner)
    assert (await db.list_memories(owner))[0]['details'] == ['Đã sửa tay mới nhất']
    assert (await db.companion_summary(owner, cid))['text'] == 'Unchanged summary.'

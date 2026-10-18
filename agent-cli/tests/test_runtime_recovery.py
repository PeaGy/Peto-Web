"""Phục hồi phiên, vòng đời dữ liệu và bằng chứng qua các ranh giới crash; không gọi API."""
import copy
import json
import os
import sqlite3
import time

import pytest
from conftest import FakeUI
from test_agent_workflow import Client, call, message
from test_durable_runtime import work
from peto_agent import history, loop
from peto_agent.client import ApiError
from peto_agent.images import Image
from peto_agent.journal import DurabilityError, Journal
from peto_agent.task_state import TaskState
from peto_agent.workspace import Workspace


def test_missing_or_corrupt_managed_journal_never_falls_back_to_json(project):
    session = work(project, [[message('đã xong')]])
    session.run_task('đề bài')
    journal = session._journal()
    journal.path.unlink()
    with pytest.raises(DurabilityError, match='Thiếu journal'):
        history.load(project, Client.server, session.session_id)
    journal.path.write_bytes(b'not a sqlite database')
    with pytest.raises(DurabilityError, match='Không đọc được journal'):
        history.load(project, Client.server, session.session_id)
    with pytest.raises(DurabilityError):
        work(project).resume(session.items, session_id=session.session_id)


def test_unmanaged_legacy_json_still_opens_without_a_journal(project):
    assert history.save(project, Client.server, [message('cũ')], session_id='legacy')
    saved = history.load(project, Client.server, 'legacy')
    assert saved.items == [message('cũ')]
    session = work(project)
    session.resume(saved.items, session_id=saved.id)
    assert session.items == saved.items and not session.client.bodies


def test_delete_tombstone_blocks_late_checkpoint_and_title_callbacks(project):
    session = work(project, [[message('xong')]])
    session.run_task('gốc')
    journal = session._journal()
    assert history.delete(project, Client.server, session.session_id)
    with pytest.raises(DurabilityError, match='đã bị xóa'):
        journal.snapshot(session._runtime_data())
    with pytest.raises(DurabilityError):
        journal.request_started({'context': {'purpose': 'title'}})
    history.rename(project, Client.server, session.session_id, 'tên muộn')
    # Một bản xuất cũ được chép lại cũng không được làm sống lại phiên đã xóa.
    history.save(project, Client.server, session.items, session_id=session.session_id)
    assert history.load(project, Client.server, session.session_id) is None
    assert not history.list_sessions(project, Client.server)
    assert not journal.path.exists()


def test_title_metadata_survives_a_stale_runtime_checkpoint(project):
    session = work(project, [[message('xong')]])
    session.run_task('gốc')
    before = session._journal().read()
    history.rename(project, Client.server, session.session_id, 'Tên đã đổi')
    session._journal().snapshot(before)
    saved = history.load(project, Client.server, session.session_id)
    assert saved.title == 'Tên đã đổi' and saved.items == before['items']


def test_retention_and_delete_respect_an_active_execution_lease(project):
    session = work(project, [[message('xong')]])
    session.run_task('phiên cũ')
    journal = session._journal()
    exported = history._folder(project) / f'{session.session_id}.json'
    old = time.time() - history.MAX_AGE_SECONDS - 1
    os.utime(exported, (old, old))
    journal.claim()
    try:
        with pytest.raises(DurabilityError):
            history.delete(project, Client.server, session.session_id)
        history.save(project, Client.server, [message('giữ')], session_id='keep')
        assert journal.path.exists() and exported.exists()
    finally:
        journal.release()
    history.save(project, Client.server, [message('giữ')], session_id='keep')
    assert not journal.path.exists() and not exported.exists() and journal.deleted()


def test_future_journal_schema_is_not_silently_modified(project):
    journal = work(project)._journal()
    journal.snapshot({'items': []})
    with sqlite3.connect(journal.path) as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(DurabilityError, match='CLI mới hơn'):
        journal.read()


def test_storage_failure_at_cli_boundary_leaves_terminal_and_reports_a_clear_error(monkeypatch):
    from peto_agent import __main__ as cli
    ui = FakeUI()
    stopped = []
    monkeypatch.setattr(ui, 'stop_footer', lambda: stopped.append(True), raising=False)
    monkeypatch.setattr(cli, 'create_ui', lambda: ui)
    def broken(*args, **kwargs):
        raise DurabilityError('Thiếu journal; chưa chạy gì.')
    monkeypatch.setattr(cli, 'session', broken)
    assert cli.main([]) == 1
    assert stopped and 'Thiếu journal' in ui.text


def test_physical_retry_has_a_new_request_id_but_one_logical_step(project, monkeypatch):
    monkeypatch.setattr(loop, 'RETRY_WAITS', (0,))
    session = work(project, [ApiError(0, 'Mạng ngắt giả'), [message('đã nhận')]])
    session.run_task('gửi')
    events = session._journal().events()
    starts = [row for row in events if row['kind'] == 'model.started']
    assert len(starts) == 2 and starts[0]['entity'] != starts[1]['entity']
    assert starts[0]['data']['logical_step'] == starts[1]['data']['logical_step']
    published = next(row for row in events if row['kind'] == 'step.published')
    assert published['data']['request_id'] == starts[1]['entity']
    assert published['entity'] == starts[1]['data']['logical_step']


def test_pending_tool_images_survive_resume_once_without_rerunning_capture(project):
    session = work(project)
    session.items = [{'type': 'message', 'role': 'user', 'content': 'xem ảnh'}]
    journal = session._journal()
    image_message = {'type': 'message', 'role': 'user', 'content': [
        {'type': 'input_text', 'text': history.TOOL_IMAGES_NOTE},
        {'type': 'input_image', 'image_url': 'data:image/png;base64,dGVzdA=='}]}
    journal.snapshot({**session._runtime_data(), 'pending_images': image_message})
    resumed = work(project)
    resumed.resume(session.items, session_id=session.session_id)
    assert resumed.items.count(image_message) == 1 and not resumed.client.bodies
    resumed.resume(resumed.items, session_id=session.session_id)
    assert resumed.items.count(image_message) == 1


def test_same_text_without_images_does_not_consume_an_attached_queued_message(project):
    session = work(project, [[message('chữ mới')], [message('đã xem ảnh')]])
    image = Image(b'test', 'image/png', 1, 1)
    session.enqueue('giống nhau', [(3, image)], delivery='queue')
    session.run_task('giống nhau')
    assert len(session.pending_input()) == 1
    assert 'data:image' not in json.dumps(session.client.bodies[0])
    session.ui.answers = ['1', '1']
    session.show_pending()
    assert not session.pending_input()
    assert image.data_url() in json.dumps(session.client.bodies[-1])


def test_pending_slash_command_requires_enter_and_cancellation_never_executes(project, monkeypatch):
    session = work(project)
    session.enqueue('/new', delivery='queue')
    prefills = []
    monkeypatch.setattr(session.ui.target, 'prefill', prefills.append)
    session.ui.answers = ['1', '1']
    session.show_pending()
    assert prefills == ['/new'] and len(session.pending_input()) == 1
    assert not session.client.bodies
    session.ui.answers = ['1', '2']
    session.show_pending()
    assert not session.pending_input() and not session.client.bodies


def test_projection_is_bounded_without_discarding_full_state(project):
    state = TaskState(Workspace(project))
    state.data['goal'] = 'mục tiêu ' * 1000
    state.data['plan'] = [{'title': 'việc' * 40, 'status': 'pending'}] * 10
    for index in range(100):
        state.record(f'check:{index}', 'run_python', {'code': 'x' * 1000}, {'exit_code': 0, 'output': 'y' * 3000})
    state.data['artifacts'] = {f'a{index}.txt': {'status': 'deleted'} for index in range(40)}
    for index in range(30):
        state.accept(f'c{index}' + 'x' * 290, 'unverified', [], 'note' * 300)
    before = copy.deepcopy(state.data)
    view = state.view()
    assert len(json.dumps(view, ensure_ascii=False)) < 14200
    assert all(view['omitted'][key] > 0 for key in ('artifacts', 'evidence', 'acceptance'))
    assert state.data == before


@pytest.mark.parametrize('tool,result', [('write_file', {'ok': True}), ('update_plan', {'ok': True}),
                                       ('run_command', {'exit_code': 1}), ('read_file', {'error': 'đọc lỗi'})])
def test_failed_checks_and_mutations_cannot_be_claimed_as_passed(project, tool, result):
    state = TaskState(Workspace(project))
    state.record('observation', tool, {}, result)
    with pytest.raises(ValueError):
        state.accept('Ứng dụng chạy được', 'passed', ['observation'], 'Kiểm phạm vi ứng dụng.')


def test_reread_external_change_invalidates_old_acceptance_and_can_establish_new_scope(project):
    state = TaskState(Workspace(project))
    target = project / 'a.txt'
    target.write_text('old')
    state.record('write', 'write_file', {}, {'ok': True, 'path': 'a.txt'})
    state.record('read', 'read_file', {'path': 'a.txt'}, {'path': 'a.txt'})
    state.accept('Nội dung', 'passed', ['read'], 'Chỉ đọc lại tệp.')
    target.write_text('new')
    assert not state.accepted()
    state.record('read-new', 'read_file', {'path': 'a.txt'}, {'path': 'a.txt'})
    with pytest.raises(ValueError):
        state.accept('Nội dung', 'passed', ['read'], 'Bằng chứng cũ.')
    state.accept('Nội dung', 'passed', ['read-new'], 'Đã đọc lại bản sửa bên ngoài.')
    assert state.accepted()

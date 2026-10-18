"""Ranh giới lưu trước hiệu ứng/trình bày, inbox, crash thật và nghiệm thu, không gọi API."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from conftest import FakeUI, handoff
from test_agent_workflow import Client, call, message
from peto_agent import history
from peto_agent.journal import Journal, DurabilityError
from peto_agent.loop import Session
from peto_agent.observer import observe
from peto_agent.task_state import TaskState
from peto_agent.tools import Tools
from peto_agent.workspace import Workspace


def work(project, replies=(), ui=None):
    session = Session(Client(replies), Workspace(project), ui or FakeUI())
    session.auto_title = False
    return session


@pytest.mark.parametrize('method', ['tool_started', 'tool_finished', 'preview', 'request_finished', 'status'])
def test_renderer_failure_cannot_erase_a_completed_result(project, monkeypatch, method):
    ui = FakeUI()
    def broken(*args, **kwargs):
        raise RuntimeError('Lỗi renderer giả.')
    monkeypatch.setattr(ui, method, broken)
    session = work(project, [[call(1, 'write_file', path='a.txt', content='một lần')], [message('Đã ghi.')], [message('Chưa chạy test ứng dụng.')]], ui)
    session.run_task('Ghi tệp')
    saved = history.load(project, session.client.server)
    outputs = [json.loads(row['output']) for row in saved.items if row.get('type') == 'function_call_output']
    assert outputs[0]['ok'] and (project / 'a.txt').read_text(encoding='utf-8') == 'một lần'
    assert len([row for row in session._journal().events() if row['kind'] == 'tool.finished']) == 1


def test_actual_output_is_durable_before_renderer_observes_it(project, monkeypatch):
    session = work(project, [[call(1, 'write_file', path='a.txt', content='x')], [message('Xong.')], [message('Chưa có test.')]])
    seen = []
    def inspect(done):
        durable = session._journal().read()
        seen.append(json.loads(durable['items'][-1]['output']))
        raise RuntimeError('Renderer dừng sau khi đã đọc projection.')
    monkeypatch.setattr(session.ui.target, 'tool_finished', inspect)
    session.run_task('Ghi')
    assert len(seen) == 1 and seen[0]['ok']


def test_permission_and_question_renderer_failure_never_grants_permission(project, monkeypatch, ask_permissions):
    ui = FakeUI()
    def broken(*args, **kwargs):
        raise RuntimeError('Khung tương tác lỗi.')
    monkeypatch.setattr(ui, 'ask', broken)
    tools = Tools(Workspace(project), ui)
    result = tools.call('write_file', json.dumps({'path': 'x.txt', 'content': 'x'}))
    assert result.get('error') and not (project / 'x.txt').exists()
    monkeypatch.setattr(ui, 'questions', broken)
    assert observe(ui).questions([]) is None


def test_reply_renderer_failure_does_not_change_physical_request_or_result(project, monkeypatch):
    ui = FakeUI()
    def broken():
        raise RuntimeError('Không tạo được writer.')
    monkeypatch.setattr(ui, 'reply', broken)
    session = work(project, [[message('Đã trả lời.')]], ui)
    session.run_task('Hỏi')
    events = session._journal().events()
    assert [row['kind'] for row in events if row['kind'].startswith('model.')] == ['model.started', 'model.completed']
    assert 'Đã trả lời.' in json.dumps(history.load(project, session.client.server).items, ensure_ascii=False)


def test_failed_outcome_commit_stops_before_next_effect(project, monkeypatch):
    session = work(project, [[call(1, 'write_file', path='first.txt', content='x'),
                              call(2, 'write_file', path='second.txt', content='x')]])
    def broken(*args, **kwargs):
        raise DurabilityError('Đĩa đầy giả.')
    monkeypatch.setattr(Journal, 'tool_finished', broken)
    with pytest.raises(DurabilityError):
        session.run_task('Ghi hai tệp')
    assert (project / 'first.txt').exists() and not (project / 'second.txt').exists()
    assert not session.task_state.data['evidence']
    assert not session.task_state.data['artifacts']


@pytest.mark.parametrize('crash', ['before-result', 'after-result', 'input-only'])
def test_real_process_death_recovers_without_replaying_any_tool(project, crash):
    script = '''
import os,sys
from conftest import FakeUI
from test_agent_workflow import Client,call,message
from peto_agent.loop import Session
from peto_agent.workspace import Workspace
from pathlib import Path
root=Path(sys.argv[1]); phase=sys.argv[2]
ui=FakeUI()
s=Session(Client([[call(1,'write_file',path='effect.txt',content='đã chạy')],[message('xong')]]),Workspace(root),ui)
s.auto_title=False
if phase=='input-only':
    s.enqueue('tin chưa chạy',delivery='input',item_id='same')
    os._exit(23)
if phase=='before-result': s.tools.record_result=lambda done: os._exit(23)
else: ui.tool_finished=lambda done: os._exit(23)
s.run_task('Ghi tệp')
'''
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(Path(__file__).resolve().parents[1]), str(Path(__file__).parent)])}
    result = subprocess.run([sys.executable, '-c', script, str(project), crash], env=env, timeout=15, capture_output=True)
    assert result.returncode == 23, result.stderr.decode(errors='replace')
    saved = history.load(project, Client.server)
    assert saved is not None
    resumed = work(project)
    resumed.resume(saved.items, session_id=saved.id)
    assert not resumed.client.bodies, 'Mở lại không được gọi model hay chạy lại công cụ.'
    if crash == 'input-only':
        assert len(resumed.pending_input()) == 1 and not (project / 'effect.txt').exists()
        resumed.client.client.replies = [[message('Đã nhận tin.')]]
        resumed.run_task('tin chưa chạy')
        assert not resumed.pending_input()
        assert sum(row.get('content') == 'tin chưa chạy' for row in resumed.items) == 1
    else:
        assert (project / 'effect.txt').read_text(encoding='utf-8') == 'đã chạy'
        output = next(json.loads(row['output']) for row in resumed.items if row.get('type') == 'function_call_output')
        assert bool(output.get('ok')) is (crash == 'after-result')
        if crash == 'before-result':
            assert 'chạy một phần' in output['error']


def test_admission_first_wins_delivery_is_atomic_and_cancellation_does_not_execute(project):
    session = work(project)
    journal = session._journal()
    first = session.enqueue('đầu', item_id='one')
    assert session.enqueue('payload retry khác', item_id='one') == first
    assert journal.pending()[0]['data']['text'] == 'đầu'
    with pytest.raises(DurabilityError):
        journal.deliver(['one', 'missing'], session._runtime_data())
    assert len(journal.pending()) == 1
    journal.cancel_input('one')
    assert journal.pending() == [] and not session.client.bodies
    with pytest.raises(DurabilityError):
        journal.enqueue({'text': 'khác'}, 'queue', 'one')


def test_two_runners_cannot_own_the_same_session(project):
    one = work(project)._journal()
    two = Journal(project, Client.server, one.identity['id'])
    one.claim()
    try:
        with pytest.raises(DurabilityError):
            two.claim()
    finally:
        one.release()
    two.claim(); two.release()


def test_reused_provider_call_id_is_scoped_to_each_step(project):
    session = work(project, [[call(0, 'list_files')], [call(0, 'list_files')], [message('Xong.')]])
    session.run_task('Đọc hai lần')
    events = session._journal().events()
    ids = [row['entity'] for row in events if row['kind'] == 'tool.finished']
    assert len(ids) == len(set(ids)) == 2


def test_journal_is_authoritative_when_json_export_is_stale_or_lost(project):
    session = work(project, [[message('kết quả mới')]])
    session.run_task('đề bài')
    path = history._folder(project) / (session.session_id + '.json')
    path.write_text('{}')
    assert history.load(project, Client.server, session.session_id).items == session.items
    path.unlink()
    assert history.load(project, Client.server).id == session.session_id
    assert history.load(project, 'https://other.test') is None
    assert history.delete(project, Client.server, session.session_id)
    assert history.load(project, Client.server, session.session_id) is None


def test_task_acceptance_requires_real_current_evidence_and_survives_compaction(project):
    session = work(project)
    state = session.task_state
    (project / 'a.txt').write_text('x')
    state.record('write', 'write_file', {}, {'ok': True, 'path': 'a.txt'})
    state.record('check', 'run_command', {'command': 'consumer'}, {'exit_code': 0, 'output': 'đã kiểm cấu trúc'})
    with pytest.raises(ValueError):
        state.accept('Ứng dụng', 'passed', ['invented'], '')
    state.accept('Cấu trúc', 'passed', ['check'], 'Chưa nghe thử trong game; chỉ kiểm cấu trúc.')
    assert state.accepted()
    (project / 'a.txt').write_text('bị sửa ngoài', encoding='utf-8')
    with pytest.raises(ValueError):
        state.accept('Cấu trúc', 'passed', ['check'], '')
    state.record('write2', 'write_file', {}, {'ok': True, 'path': 'a.txt'})
    assert not state.accepted() and state.data['acceptance'][0]['status'] == 'stale'
    state.record('failed', 'run_command', {}, {'exit_code': 1})
    with pytest.raises(ValueError):
        state.accept('Cấu trúc', 'passed', ['failed'], '')
    session.items = [{'type': 'message', 'role': 'user', 'content': 'Đề bài ' * 200}] * 35
    session.client.client.replies = [[message(handoff())]]
    assert session.compact()
    saved = history.load(project, Client.server)
    resumed = work(project)
    resumed.resume(saved.items, session_id=saved.id)
    assert resumed.task_state.data == state.data
    assert resumed.task_state.data['acceptance'][0]['status'] == 'stale'


def test_btw_request_lifecycle_keeps_question_and_answer_private(project):
    session = work(project, [[message('câu trả lời riêng')]])
    assert session.side_question('câu hỏi riêng') == 'câu trả lời riêng'
    log = json.dumps(session._journal().events(), ensure_ascii=False)
    assert 'model.started' in log and 'model.completed' in log
    assert 'câu hỏi riêng' not in log and 'câu trả lời riêng' not in log


@pytest.mark.parametrize('busy', [True, False])
def test_real_composer_admits_before_acknowledging_and_survives_render_error(project, monkeypatch, busy):
    from peto_agent.line_editor import Key
    from peto_agent.tui.footer import FooterEngine
    from test_footer import session as composer
    ui, console, terminal, _ = composer(start=False)
    ui.engine = FooterEngine(ui, ui.editor, size=lambda: (80, 24))
    session = work(project, ui=ui)
    ui.engine.busy = busy
    def broken(*args, **kwargs):
        raise RuntimeError('Không vẽ được tin.')
    monkeypatch.setattr(ui, 'commit_user', broken)
    ui.editor.state.insert('tin cần giữ')
    ui.engine._key(Key('enter'))
    assert not ui.editor.state.text
    pending = session.pending_input()
    assert len(pending) == 1 and pending[0]['data']['text'] == 'tin cần giữ'
    if busy:
        session._inbox()
        assert not session.pending_input()
        assert 'tin cần giữ' in json.dumps(session.items, ensure_ascii=False)
    else:
        assert ui.engine.submitted.get_nowait()[0] == 'tin cần giữ'


def test_failed_composer_admission_keeps_text_and_does_not_acknowledge(project):
    from peto_agent.line_editor import Key
    from peto_agent.tui.footer import FooterEngine
    from test_footer import session as composer
    ui, *_ = composer(start=False)
    ui.engine = FooterEngine(ui, ui.editor, size=lambda: (80, 24))
    def broken(*args, **kwargs):
        raise DurabilityError('Đĩa đầy')
    ui.bind_runtime(broken, lambda: [])
    ui.editor.state.insert('chưa được gửi')
    ui.engine._key(Key('enter'))
    assert ui.editor.state.text == 'chưa được gửi'
    assert ui.engine.submitted.empty() and not ui.engine.steers


def test_acceptance_tool_schema_flow_uses_runtime_issued_evidence(project):
    class Model(Client):
        def stream(self, path, body, **kwargs):
            self.bodies.append(body)
            turn = len(self.bodies)
            if turn == 1:
                output = [call(0, 'write_file', path='checked.txt', content='x')]
            elif turn == 2:
                output = [call(0, 'read_file', path='checked.txt')]
            elif turn == 3:
                evidence = json.loads(body['input'][-1]['output'])['evidence_id']
                output = [call(0, 'record_acceptance', criterion='Nội dung tệp', status='passed',
                               evidence_ids=[evidence], note='Đã đọc lại; không phải kiểm thử ứng dụng.')]
            else:
                output = [message('Nội dung tệp đã được đọc lại, chưa kiểm thử ứng dụng.')]
            yield {'type': 'done', 'output': output}
    session = Session(Model(), Workspace(project), FakeUI())
    session.auto_title = False
    session.tools.features += ['task_state']
    session.run_task('Tạo tệp và đọc lại')
    assert session.task_state.accepted()
    assert len(session.client.bodies) == 4
    assert session.task_state.data['acceptance'][0]['reported_by'] == 'agent'
    assert 'Đạt trong phạm vi đã kiểm' in session.ui.text
    before = session.task_state.view()
    saved = history.load(project, Client.server)
    resumed = work(project)
    resumed.resume(saved.items, session_id=saved.id)
    assert resumed.task_state.view() == before

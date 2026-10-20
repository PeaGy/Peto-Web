"""Model changes, usage anchors, transport limits and bounded overflow recovery."""
import copy
import json

import pytest
from conftest import FakeUI, handoff
from test_agent_workflow import Client, call, message

from peto_agent import history, recall
from peto_agent.budget import Tracker, ceiling, estimate
from peto_agent.context import compact_input, compact_prefix, efficient_input, text_of
from peto_agent.loop import Session, user_message
from peto_agent.workspace import Workspace, WorkspaceError


def entry(key="peto", window=128000):
    return {"key": key, "context_limits": {"identity": "test/" + key, "context": window,
                                          "input": window, "output": 8192}}


def work(project, client=None, window=128000):
    session = Session(client or Client(), Workspace(project), FakeUI())
    session.tools.features = ["context_budget", "recall"]
    session.configure_models([entry(window=window), entry("sol", 1050000)])
    return session


def test_same_history_fits_large_model_and_compacts_small_one(project):
    session = work(project)
    session.items = [user_message("Keep exactly these requirements."), *[message("x" * 170000) for _ in range(3)]]
    assert session._compact_due() and session.context_share() > 1
    session.context_tokens = 123456
    session.set_model("sol", 4)
    assert not session._compact_due() and session.context_share() < .2
    assert session.context_tokens is None


def test_item_limit_does_not_pretend_to_be_token_usage(project):
    session = work(project, window=1050000)
    session.items = [message("ok") for _ in range(181)]
    assert not session._compact_due() and session.context_share() < .1
    session.items += [message("ok") for _ in range(60)]
    assert session._compact_due() and session.context_share() < .1
    session.tools.features = []
    assert session.context_share() >= 1  # Old server retains the old, explicitly separate fallback.


def test_usage_anchor_counts_cache_and_reasoning_once_and_invalidates_on_model_change():
    tracker = Tracker()
    tracker.configure([entry(), entry("sol", 1050000)])
    items = [user_message("goal"), message("done")]
    tracker.measured("peto", items, {"input_tokens": 10000, "output_tokens": 2000,
                                     "cached_tokens": 8000, "reasoning_tokens": 1000})
    assert tracker.tokens("peto", items) == 12000
    items.append({"type": "function_call_output", "call_id": "a", "output": "x" * 4000})
    assert 13000 < tracker.tokens("peto", items) < 14000
    assert tracker.tokens("sol", items) < 12000
    tracker.observe("peto", {**entry()["context_limits"], "model": "sol", "overhead_tokens": 900000})
    assert "peto" not in tracker.overhead


def test_changed_server_model_identity_discards_stale_usage():
    tracker = Tracker()
    tracker.configure([entry("sol", 1050000)])
    tracker.measured("sol", [], {"input_tokens": 900000, "output_tokens": 500})
    tracker.observe("sol", {**entry("sol", 1050000)["context_limits"], "identity": "openai/gpt-6.1-sol",
                             "model": "sol", "overhead_tokens": 1200})
    assert tracker.anchor is None and tracker.tokens("sol", []) < 2000


def test_large_signed_tool_group_can_be_summarized_without_splitting_it():
    rows = [user_message("goal"), message("inspect"), message("details"),
            {"type": "reasoning", "anthropic_model": "claude-sonnet-5-5", "anthropic_output_count": 4},
            call(1, "read_file", path="one.py"), call(2, "read_file", path="two.py"),
            {"type": "function_call_output", "call_id": "1", "output": "x" * 100000},
            {"type": "function_call_output", "call_id": "2", "output": "y" * 100000}]
    prefix, tail = compact_prefix(rows, keep_tokens=15000)
    assert prefix == rows and not tail


def test_compaction_transport_copy_preserves_requests_and_reports_clipping():
    goal = "Do not replace ID 3; this correction supersedes the prototype."
    rows = [user_message(goal), call(1, "read_file", path="data.txt"),
            {"type": "function_call_output", "call_id": "1", "output": "x" * 300000}]
    original = copy.deepcopy(rows)
    bounded = compact_input(rows, 10000)
    assert goal in bounded[0]["content"] and "tool result 1" in bounded[0]["content"]
    assert estimate(bounded) < 10000 and rows == original
    with pytest.raises(WorkspaceError):
        compact_input([user_message("indispensable " * 50000)], 1000)


class StreamClient(Client):
    def stream(self, path, body, **kwargs):
        self.bodies.append(copy.deepcopy(body))
        reply = self.replies.pop(0)
        if isinstance(reply, list) and reply and reply[0].get("type") in {"error", "meta", "done"}:
            yield from reply
        else:
            yield {"type": "done", "output": reply, "purpose": body.get("context", {}).get("purpose")}


def old_history():
    return [user_message("Keep the old payloads; final success requires a separate consumer."),
            *[message("observed result " * 150) for _ in range(40)]]


def test_overflow_compacts_once_and_retries_without_replaying_effects(project):
    client = StreamClient([[{"type": "error", "message": "too long", "code": "context_overflow"}],
                           [message(handoff())], [message("No edits made; checked previous result.")]])
    session = work(project, client, window=1050000)
    session.items = old_history()
    session.run_task("Continue")
    assert len(client.bodies) == 3
    assert client.bodies[1]["context"]["purpose"] == "compact"
    assert "Keep the old payloads" in str(client.bodies[2]["input"])
    assert history.load(project, client.server).items == session.items
    assert recall.folder(project, session.session_id).exists()


def test_second_overflow_stops_after_one_recovery(project):
    rejected = [{"type": "error", "message": "too long", "code": "context_overflow"}]
    client = StreamClient([rejected, [message(handoff())], rejected])
    session = work(project, client, window=1050000)
    session.items = old_history()
    session.run_task("Continue")
    assert len(client.bodies) == 3 and "không tự thử lại" in session.ui.text


def test_summarizer_overflow_shrinks_its_view_only_then_saves_original_archive(project):
    client = StreamClient([[{"type": "error", "code": "context_overflow", "message": "too long"}],
                           [message(handoff())]])
    session = work(project, client, window=1050000)
    session.items = old_history()
    original = copy.deepcopy(session.items)
    assert session.compact() and len(client.bodies) == 2
    assert len(client.bodies[1]["input"]) == 2 and 'Historical transcript' in str(client.bodies[1]["input"])
    assert estimate(client.bodies[1]['input']) < estimate(client.bodies[0]['input'])
    archive = json.loads(next(recall.folder(project, session.session_id).glob('*.json')).read_text(encoding='utf-8'))
    n = len(archive['items'])
    assert [text_of(row) for row in archive['items']] == [text_of(row) for row in original[:n]]
    assert session.items[-len(original[n:]):] == original[n:]


def test_unknown_or_malformed_metadata_keeps_legacy_fallback(project):
    session = work(project)
    session.configure_models([{"key": "peto", "context_limits": {"context": True, "output": 8192}}])
    session.items = [message("old") for _ in range(180)]
    assert session._compact_due()


def test_server_byte_limit_and_changed_guidance_are_accounted_for(project):
    session = work(project, window=1050000)
    session.configure_models([entry(window=1050000)], {"max_request_bytes": 65536})
    session.items = [user_message("hi"), message("x" * 60000)]
    assert session.context_share() < .1 and session._compact_due()
    before = session.context_share()
    (project / 'AGENTS.md').write_text('Important requirement. ' * 400, encoding='utf-8')
    assert session.context_share() > before


def test_saved_none_effort_is_not_sent_to_sol_61(monkeypatch):
    from peto_agent import config
    from peto_agent.__main__ import _effort
    monkeypatch.setattr(config, 'load', lambda: {'model': 'sol', 'effort': 'none'})
    assert _effort({'models':[{'key':'sol','label':'6.1 Sol','efforts':['low','medium','high','xhigh','max']}]}) == 'medium'


def test_sol_upgrade_rebuilds_portable_history_but_keeps_new_identity_reasoning(project):
    session = work(project)
    session.set_model('sol', 4)
    rows = [user_message('unfinished goal'), {'type':'reasoning','encrypted_content':'old-model-state'}, message('observed')]
    session.resume(rows, model='sol', model_identity='openai/gpt-6-sol')
    assert all(row.get('type') != 'reasoning' for row in session.items)
    assert 'unfinished goal' in str(session.items)
    session.resume(rows, model='sol', model_identity=entry('sol', 1050000)['context_limits']['identity'])
    assert session.items == rows
    assert session.save()
    saved = history.load(project, session.client.server)
    assert saved.model_identity == entry('sol', 1050000)['context_limits']['identity']


@pytest.mark.parametrize('kind', ['delta', 'thinking', 'search'])
def test_partial_response_is_not_compacted_and_retried_as_an_unstarted_request(project, kind):
    client = StreamClient([[{'type':'meta'}, {'type':kind,'text':'partial'},
                            {'type':'error','code':'context_overflow','message':'failed after output'}]])
    session = work(project, client)
    session.run_task('check')
    assert len(client.bodies) == 1 and 'failed after output' in session.ui.text


def test_wrapup_usage_does_not_count_the_response_twice(project):
    output = [message('remaining work ' * 200)]
    client = StreamClient([[{'type':'done', 'output':output, 'usage':{'input_tokens':10000,'output_tokens':2000}}]])
    session = work(project, client)
    session.items = [user_message('goal')]
    result = session._attempt('wrapup', may_retry=False)
    session.items += result
    assert session.context_budget.tokens('peto', efficient_input(session.items)) == 12000

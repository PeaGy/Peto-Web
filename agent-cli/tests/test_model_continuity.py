"""Nhiều nguồn model, mốc M2: chọn nguồn, phần mờ theo phạm vi, đổi nguồn giữa hội thoại, lưu và mở lại."""
import json

import pytest
from conftest import FakeUI, handoff
from test_agent_workflow import Client, call, message

from peto_agent import __main__ as cli
from peto_agent import history
from peto_agent.budget import Tracker
from peto_agent.loop import Session, user_message
from peto_agent.providers import ModelSourceError, Selection
from peto_agent.workspace import Workspace

REASONING = {"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque", "summary": []}


def tagged(item, item_id):
    return {**item, "id": item_id}


class FakeSource:
    """Nguồn trực tiếp giả: cổng giao lượt gọi cho nó thay vì máy chủ Peto."""

    id = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def stream(self, request, transport, **options):
        self.requests.append(request)
        output = self.replies.pop(0)
        yield {"type": "done", "output": output, "usage": {},
               **({"purpose": request.purpose} if request.purpose != "work" else {})}


def history_with_opaque():
    return [user_message("Sửa a.txt"), REASONING, tagged(call(1, "read_file", path="a.txt"), "fc_1"),
            {"type": "function_call_output", "call_id": "1", "output": json.dumps({"content": "một"})},
            tagged(message("Đã đọc."), "msg_1")]


def test_selection_keys_keep_peto_budget_keys_and_separate_other_sources():
    assert Selection("peto", "luna", "low").budget_key == "luna"
    assert Selection("openai-key", "luna", "low", "c1").budget_key == "openai-key:c1:luna"
    assert Selection("peto", "luna", "low").opaque_scope("gpt-6-luna") != \
        Selection("openai-key", "luna", "low", "c1").opaque_scope("gpt-6-luna")
    for bad in ({"source": "Peto"}, {"source": "../x"}, {"connection": "a b"}, {"connection": ""}, {"model": ""}):
        with pytest.raises(ValueError):
            Selection(**{"source": "peto", "model": "luna", "effort": "low", **bad})


def test_same_model_name_on_two_sources_never_shares_a_usage_anchor():
    tracker = Tracker()
    tracker.configure([{"key": "luna", "context_limits": {"identity": "gpt-6-luna", "context": 400000,
                                                          "input": 400000, "output": 8192}}])
    tracker.catalog["openai-key:c1:luna"] = dict(tracker.catalog["luna"])
    items = [user_message("goal")]
    tracker.measured("luna", items, {"input_tokens": 90000, "output_tokens": 10})
    assert tracker.tokens("luna", items) == 90010
    assert tracker.tokens("openai-key:c1:luna", items) < 20000


def test_switching_source_keeps_the_conversation_and_drops_only_opaque_state(project):
    session = Session(Client(), Workspace(project), FakeUI(), model="luna")
    session.items = history_with_opaque()
    session.session_id = history.new_id()
    session.task_state.data["goal"] = "Sửa a.txt"
    same = list(session.items)
    session.select("peto", "luna")
    assert session.items == same, "cùng nguồn, cùng model: giữ suy nghĩ mã hóa"
    session.select("fake", "luna", connection="c1")
    assert REASONING not in session.items and all("id" not in item for item in session.items)
    assert [item.get("type", "message") for item in session.items] == \
        ["message", "function_call", "function_call_output", "message"]
    assert session.task_state.data["goal"] == "Sửa a.txt" and session.session_id is not None
    assert (session.source, session.connection, session.model) == ("fake", "c1", "luna")


def test_source_cannot_change_while_a_request_runs(project):
    session = Session(Client(), Workspace(project), FakeUI())
    session._running = True
    with pytest.raises(RuntimeError):
        session.select("fake", "m1")
    assert session.source == "peto"


def test_after_switching_no_request_reaches_the_old_source(project):
    peto = Client([[message("Nguồn Peto trả lời.")]])
    session = Session(peto, Workspace(project), FakeUI(), model="luna")
    fake = FakeSource([[message("Nguồn mới trả lời.")]])
    session.models.sources["fake"] = fake
    session.run_task("Một")
    session.select("fake", "m1", connection="c1")
    session.run_task("Hai")
    assert len(peto.bodies) == 1, "không lượt nào về nguồn cũ sau khi đổi"
    assert [request.selection.reference() for request in fake.requests] == \
        [{"source": "fake", "model": "m1", "effort": "medium", "connection": "c1"}]
    started = [(event["data"]["source"], event["data"]["model"]) for event in session._journal().events()
               if event["kind"] == "model.started"]
    assert started == [("peto", "luna"), ("fake", "m1")]


def test_unregistered_source_fails_cleanly_without_retry_or_retry_prompt(project):
    session = Session(Client(), Workspace(project), FakeUI())
    session.select("missing", "m1")
    session.run_task("Một")
    assert "Chưa có nguồn model" in session.ui.text and not session.can_retry
    assert issubclass(ModelSourceError, Exception)


def test_saved_files_keep_version_2_for_peto_and_use_version_3_for_other_sources(project):
    server = Client.server
    items = [user_message("Một"), message("Hai")]
    assert history.save(project, server, items, session_id="20261020-100000-aaaaaa", model="luna")
    assert history.save(project, server, items, session_id="20261020-100001-bbbbbb", model="m1",
                        source="fake", connection="c1")
    folder = history._folder(project)
    peto = json.loads((folder / "20261020-100000-aaaaaa.json").read_text(encoding="utf-8"))
    other = json.loads((folder / "20261020-100001-bbbbbb.json").read_text(encoding="utf-8"))
    assert peto["version"] == history.VERSION == 2 and "source" not in peto and "connection" not in peto
    assert other["version"] == history.SOURCE_VERSION == 3, "CLI cũ chỉ đọc bản 2 nên bỏ qua tệp này"
    assert (other["source"], other["connection"]) == ("fake", "c1")
    loaded = {saved.id: saved for saved in history.list_sessions(project, server)}
    assert (loaded["20261020-100000-aaaaaa"].source, loaded["20261020-100000-aaaaaa"].connection) == ("peto", "")
    assert (loaded["20261020-100001-bbbbbb"].source, loaded["20261020-100001-bbbbbb"].connection) == ("fake", "c1")
    history.rename(project, server, "20261020-100001-bbbbbb", "Tên mới")
    renamed = history.load(project, server, "20261020-100001-bbbbbb")
    assert (renamed.title, renamed.source, renamed.connection) == ("Tên mới", "fake", "c1")


def test_unknown_or_newer_files_are_never_opened_and_resume_says_so(project):
    server = Client.server
    folder = history._folder(project)
    folder.mkdir(parents=True, exist_ok=True)
    base = {"server": server, "root": str(project), "saved_at": 1.0, "items": [user_message("x")], "model": "m"}
    (folder / "20261020-100002-cccccc.json").write_text(json.dumps(
        {**base, "version": 3, "id": "20261020-100002-cccccc", "source": "../bad"}), encoding="utf-8")
    newer = folder / "20261020-100003-dddddd.json"
    newer.write_text(json.dumps({**base, "version": 4, "id": "20261020-100003-dddddd"}), encoding="utf-8")
    assert history.list_sessions(project, server) == []
    assert history.newer_sessions(project, server) == 1
    session = Session(Client(), Workspace(project), FakeUI())
    cli._resume(session.ui, session)
    assert "bản peto mới hơn" in session.ui.text
    assert json.loads(newer.read_text(encoding="utf-8"))["version"] == 4, "không ghi đè"


def test_resuming_another_sources_session_keeps_tool_results_and_says_which_source_continues(project):
    first = Session(Client(), Workspace(project), FakeUI(), model="m1")
    first.models.sources["fake"] = FakeSource([])
    first.select("fake", "m1", connection="c1")
    first.items = history_with_opaque()
    first.task_state.data["goal"] = "Sửa a.txt"
    assert first.save()
    saved = history.load(project, Client.server, first.session_id)
    assert saved.source == "fake" and REASONING in saved.items

    second = Session(Client(), Workspace(project), FakeUI(), model="luna")
    cli._open_session(second.ui, second, saved)
    assert second.session_id == first.session_id, "đổi nguồn vẫn là cùng một hội thoại"
    assert REASONING not in second.items
    assert any(item.get("type") == "function_call_output" for item in second.items)
    assert second.task_state.data["goal"] == "Sửa a.txt"
    assert "nguồn fake" in second.ui.text and second.source == "peto"


def test_same_source_resume_keeps_opaque_state(project):
    first = Session(Client(), Workspace(project), FakeUI(), model="luna")
    first.items = history_with_opaque()
    assert first.save()
    saved = history.load(project, Client.server, first.session_id)
    second = Session(Client(), Workspace(project), FakeUI(), model="luna")
    cli._open_session(second.ui, second, saved)
    assert REASONING in second.items and "giờ tiếp tục" not in second.ui.text


def small_catalog(session):
    session.tools.features = ["context_budget", "recall"]
    session.configure_models([{"key": "luna", "context_limits": {"identity": "gpt-6-luna", "context": 1050000,
                                                                 "input": 1050000, "output": 8192}}])
    session.context_budget.catalog["fake:c1:tiny"] = {"identity": "tiny-1", "context": 40000, "input": 40000,
                                                      "output": 4096}


def long_items():
    return [user_message("Giữ đúng yêu cầu này."), *[message("x" * 40000) for _ in range(6)], user_message("Làm tiếp")]


def test_switching_to_a_smaller_window_compacts_with_the_new_source_first(project):
    session = Session(Client(), Workspace(project), FakeUI(), model="luna")
    small_catalog(session)
    session.items = long_items()
    assert not session._compact_due()
    fake = FakeSource([[message(handoff())], [message("Xong bằng nguồn mới.")]])
    session.models.sources["fake"] = fake
    session.select("fake", "tiny", connection="c1")
    assert session._compact_due()
    session.run_task("Tiếp")
    assert [request.purpose for request in fake.requests] == ["compact", "work"]
    assert all(request.selection.model == "tiny" for request in fake.requests)
    assert session.items[-1] == message("Xong bằng nguồn mới.")


def test_failed_compaction_on_the_new_source_keeps_history_and_task_state(project):
    session = Session(Client(), Workspace(project), FakeUI(), model="luna")
    small_catalog(session)
    session.items = long_items()
    session.task_state.data["goal"] = "Giữ đúng yêu cầu này."
    fake = FakeSource([[message("không đúng định dạng")], [message("không đúng định dạng")],
                       [message("Vẫn trả lời.")]])
    session.models.sources["fake"] = fake
    session.select("fake", "tiny", connection="c1")
    before = list(session.items)
    assert not session.compact()
    assert session.items == before and session.task_state.data["goal"] == "Giữ đúng yêu cầu này."

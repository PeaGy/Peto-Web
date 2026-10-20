"""Cổng yêu cầu model (lộ trình nhiều nguồn, mốc M1): mọi lượt gọi đi qua cổng, nguồn Peto giữ nguyên hành vi."""
import copy
import json

import pytest
from conftest import FakeUI

from peto_agent import loop
from peto_agent.client import ApiError
from peto_agent.loop import Session
from peto_agent.providers import ModelGateway, ModelRequest, ModelSourceError, Selection, classify
from peto_agent.workspace import Workspace


def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def call(number, name, **args):
    return {"type": "function_call", "call_id": str(number), "name": name, "arguments": json.dumps(args)}


def done(output, purpose=None):
    return [{"type": "meta", "steps_used": 1, "steps_limit": 200},
            {"type": "done", "output": output, "usage": {}, **({"purpose": purpose} if purpose else {})}]


class Client:
    """Máy chủ giả ghi lại đường dẫn, nội dung và tham số của từng lượt gọi."""

    server = "https://example.test"

    def __init__(self, replies, on_call=None):
        self.replies = list(replies)
        self.calls = []
        self.on_call = on_call

    def stream(self, path, body, **kwargs):
        self.calls.append((path, copy.deepcopy(body), sorted(kwargs)))
        if self.on_call:
            self.on_call(len(self.calls))
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        yield from reply


def started_sources(session):
    return [(event["data"]["purpose"], event["data"].get("source"), event["data"]["model"])
            for event in session._journal().events() if event["kind"] == "model.started"]


def test_request_snapshot_does_not_follow_later_changes():
    selection = Selection("peto", "luna", "low")
    body = {"input": [], "model": "luna", "effort": "low", "context": {"purpose": "btw"}}
    request = ModelGateway(lambda: None).request("btw", body, selection)
    body["model"] = "sol"
    body["context"]["purpose"] = "compact"
    assert request.body["model"] == "luna" and request.body["context"]["purpose"] == "btw"
    assert request.selection.reference() == {"source": "peto", "model": "luna", "effort": "low"}
    with pytest.raises(Exception):
        request.selection.model = "sol"


@pytest.mark.parametrize("purpose,body", [
    ("work", {"model": "sol", "effort": "low", "context": {}}),
    ("work", {"model": "luna", "effort": "high", "context": {}}),
    ("work", {"model": "luna", "effort": "low", "context": {"purpose": "compact"}}),
    ("compact", {"model": "luna", "effort": "low", "context": {}}),
    ("chat", {"model": "luna", "effort": "low", "context": {"purpose": "chat"}}),
])
def test_request_must_match_its_selection_and_purpose(purpose, body):
    with pytest.raises(ValueError):
        ModelRequest(purpose, Selection("peto", "luna", "low"), body)


def test_unknown_source_is_refused_before_any_transport_call():
    calls = []

    class Transport:
        def stream(self, *args, **kwargs):
            calls.append(args)
            yield {}

    gateway = ModelGateway(lambda: Transport())
    request = gateway.request("work", {"model": "x", "effort": "low", "context": {}}, Selection("chatgpt", "x", "low"))
    with pytest.raises(ModelSourceError):
        gateway.stream(request)
    assert calls == []


@pytest.mark.parametrize("fields,category", [
    ({"status": 401}, "authentication"), ({"status": 403}, "permission"), ({"status": 429}, "quota"),
    ({"status": 0}, "network"), ({"status": 503}, "network"), ({"status": 500}, "server"),
    ({"status": 413}, "capability"), ({"status": 400}, "invalid_request"),
    ({"code": "context_overflow"}, "context_overflow"), ({"code": "queue_full"}, "rate_limit"),
    ({"retryable": True}, "rate_limit"), ({}, "provider"),
])
def test_errors_fall_into_shared_categories(fields, category):
    assert classify(**fields) == category


def test_every_purpose_goes_through_the_gateway_to_the_peto_step_endpoint(project, monkeypatch):
    """Work + công cụ + work, đặt tên, /btw, agent con: cùng một endpoint, nội dung như trước, nhật ký ghi nguồn."""
    (project / "a.txt").write_text("một\n", encoding="utf-8")
    client = Client([
        done([call(1, "read_file", path="a.txt", start_line=None, end_line=None)]),
        done([message("Đã đọc.")]),
        done([message("Tên phiên")], purpose="title"),
        done([message("Trả lời bên lề")], purpose="btw"),
    ])
    session = Session(client, Workspace(project), FakeUI(), model="luna", effort="medium")
    session.tools.features = [*session.tools.features, "title"]
    routed = []
    real_stream = session.models.stream

    def spy(request, **options):
        routed.append((request.purpose, request.selection.reference()))
        return real_stream(request, **options)

    monkeypatch.setattr(session.models, "stream", spy)
    session.run_task("Đọc a.txt")
    session._name_conversation()
    for _ in range(200):
        if not session._titling:
            break
        loop.time.sleep(0.01)
    assert session.side_question("Ý chính?") == "Trả lời bên lề"

    assert {path for path, _, _ in client.calls} == {"/api/agent/step"}
    bodies = [body for _, body, _ in client.calls]
    assert [body["model"] for body in bodies] == ["luna", "luna", "peto", "luna"]
    assert [body["context"].get("purpose") for body in bodies] == [None, None, "title", "btw"]
    assert all("source" not in body and "source" not in body["context"] for body in bodies)
    assert all("source" not in kwargs for _, _, kwargs in client.calls), "nguồn chỉ dùng trong CLI, không gửi lên"
    assert [purpose for purpose, _ in routed] == ["work", "work", "title", "btw"]
    assert routed[2][1] == {"source": "peto", "model": "peto", "effort": "low"}
    work_rows = [row for row in started_sources(session) if row[0] == "work"]
    assert work_rows == [("work", "peto", "luna")] * 2


def test_compact_and_explore_use_the_gateway(project):
    (project / "b.py").write_text("x = 1\n", encoding="utf-8")
    client = Client([done([message("Kết luận: b.py đặt x.")])])
    session = Session(client, Workspace(project), FakeUI(), model="luna")
    session.tools.features = [*session.tools.features, "subagent"]
    from peto_agent import subagent
    result = subagent.run(session, "Tìm x", "quick", lambda text: None)
    assert "b.py" in result["summary"]
    path, body, _ = client.calls[0]
    assert path == "/api/agent/step" and body["context"]["purpose"] == "explore" and body["model"] == "luna"
    assert ("explore", "peto", "luna") in started_sources(session)


def test_one_selection_for_a_whole_logical_step_including_retries(project, monkeypatch):
    """Đổi model giữa hai lần tự thử lại không làm lượt đang chạy đổi model."""
    monkeypatch.setattr(loop, "RETRY_WAITS", (0.01, 0.01, 0.01))
    holder = {}

    def switch(count):
        if count == 1:
            holder["session"].model = "sol"

    client = Client([ApiError(503, "Máy chủ bận."), done([message("Xong.")])], on_call=switch)
    session = Session(client, Workspace(project), FakeUI(), model="luna")
    holder["session"] = session
    session.run_task("Làm đi")
    assert [body["model"] for _, body, _ in client.calls] == ["luna", "luna"]
    assert session.model == "sol", "lượt sau mới dùng model mới"


def test_error_log_carries_the_shared_category(project):
    client = Client([[{"type": "meta", "steps_used": 1, "steps_limit": 200},
                      {"type": "error", "message": "Hết bước hôm nay."}], ApiError(429, "Hết bước hôm nay.")])
    session = Session(client, Workspace(project), FakeUI())
    entries = []
    session._log = lambda kind, **fields: entries.append((kind, fields))
    session.run_task("Một")
    session.run_task("Hai")
    errors = [fields for kind, fields in entries if kind == "error"]
    assert [row["category"] for row in errors] == ["provider", "quota"]


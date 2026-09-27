"""Ghi chú riêng của Peto trong Companion: model nhớ được bí mật trò chơi, người dùng không thấy và không nghe."""
import pytest

import companion_memory
import db
from ai import StreamChunk
from ai.mock import MockProvider
from companion_memory import MEMORY_MARKER
from persona import COMPANION_SYSTEM_PROMPT
from private_notes import NoteFilter, strip
from tests.conftest import TEST_OWNER, read_events


async def turn(client, message: str, conversation: str | None = None, mode: str = "companion") -> list[dict]:
    body = {"message": message, "mode": mode}
    if conversation:
        body["conversation_id"] = conversation
    async with client.stream("POST", "/api/chat", json=body) as response:
        return await read_events(response)


def shown(events: list[dict]) -> str:
    return "".join(event["text"] for event in events if event["type"] == "delta")


async def test_the_secret_stays_hidden_but_peto_reads_it_back_next_turn(client):
    events = await turn(client, "Chọn một số từ 1 tới 9 rồi nhớ nha __bimat__:số 7")
    assert events[-1]["type"] == "done"
    assert shown(events) == "Mình chọn xong rồi. Đoán đi!"
    conversation = events[0]["conversation_id"]
    stored = await db.get_messages(TEST_OWNER, conversation)
    assert "<private>số 7</private>" in stored[-1]["content"]
    for url in ("/api/companion", f"/api/conversations/{conversation}/messages"):
        messages = (await client.get(url)).json()["messages"]
        assert [item["content"] for item in messages if item["role"] == "assistant"] == ["Mình chọn xong rồi. Đoán đi!"]

    events = await turn(client, "Mình chịu, số mấy vậy __doan__", conversation)
    assert shown(events) == "Ghi chú riêng của mình: số 7"


async def test_the_chat_tab_keeps_the_tag_as_written(client):
    # Ở tab Trò chuyện "<private>" có thể là chữ thật, ví dụ trong code XML.
    events = await turn(client, "Cho mình ví dụ XML __bimat__:x", mode="chat")
    assert "<private>x</private>" in shown(events)


async def test_a_reply_that_is_only_a_note_is_not_saved_as_an_empty_bubble(client, monkeypatch):
    original = MockProvider.stream

    async def only_a_note(self, *, system_prompt, messages, **kwargs):
        if "Chế độ Companion" not in system_prompt:
            async for chunk in original(self, system_prompt=system_prompt, messages=messages, **kwargs):
                yield chunk
            return
        yield StreamChunk("text", "<private>7</private>")

    monkeypatch.setattr(MockProvider, "stream", only_a_note)
    events = await turn(client, "Chọn một số đi")
    assert events[-1]["type"] == "error" and not shown(events)
    stored = await db.get_messages(TEST_OWNER, events[0]["conversation_id"])
    assert [row["role"] for row in stored] == ["user"]


async def test_memory_never_reads_the_secret(client, monkeypatch):
    await db.set_memory_enabled(TEST_OWNER, True)
    seen: list[str] = []
    original = MockProvider.stream

    async def spy(self, *, system_prompt, messages, **kwargs):
        if MEMORY_MARKER in system_prompt:
            seen.append(messages[-1].content)
        async for chunk in original(self, system_prompt=system_prompt, messages=messages, **kwargs):
            yield chunk

    monkeypatch.setattr(MockProvider, "stream", spy)
    await turn(client, "Chọn một số từ 1 tới 9 rồi nhớ nha __bimat__:số 7")
    assert seen and "Peto: Mình chọn xong rồi. Đoán đi!" in seen[-1] and "<private>" not in seen[-1]


def test_summaries_keep_the_note_so_a_long_game_survives_the_history_window():
    rows = [{"role": "user", "content": "Chọn một số"}, {"role": "assistant", "content": "Xong. <private>7</private> Đoán đi!"}]
    assert "<private>7</private>" in companion_memory._summary_prompt("", rows)
    assert "<private>" not in companion_memory._prompt([], rows)


def test_the_companion_prompt_tells_peto_how_to_keep_a_secret():
    assert "<private>...</private>" in COMPANION_SYSTEM_PROMPT
    assert "no memory between turns" in COMPANION_SYSTEM_PROMPT
    assert "Never say you picked" in COMPANION_SYSTEM_PROMPT


CASES = [
    "Mình chọn xong rồi. <private>số 7</private> Đoán đi!",
    "<private>7</private> Alright, go ahead.",
    "Go ahead. <private>7</private>",
    "Hai ghi chú <private>a</private> ở đây <PRIVATE>b</Private> nữa.",
    "Chưa đóng <private>bí mật mà hết câu",
    "Tim <3 và a < b vẫn là chữ thường, cả <priv nữa",
    "Không có ghi chú nào.",
]


def same(left: str, right: str) -> bool:
    return " ".join(left.split()) == " ".join(right.split())


@pytest.mark.parametrize("text", CASES)
def test_the_stream_filter_matches_strip_however_the_text_is_cut(text):
    expected = strip(text)
    for size in range(1, len(text) + 1):
        notes = NoteFilter()
        out = "".join(notes.feed(text[i:i + size]) for i in range(0, len(text), size)) + notes.flush()
        assert same(out, expected), (size, out)
    for cut in range(len(text) + 1):
        notes = NoteFilter()
        out = notes.feed(text[:cut]) + notes.feed(text[cut:]) + notes.flush()
        assert same(out, expected), (cut, out)


def test_no_double_space_where_a_note_was():
    assert strip("one. <private>7</private> Go") == "one. Go"
    assert strip("<private>7</private> Alright") == "Alright"
    assert strip("Chưa đóng <private>bí mật") == "Chưa đóng"
    assert strip("Tim <3") == "Tim <3"
    notes = NoteFilter()
    out = "".join(notes.feed(part) for part in ["one. <priv", "ate>7</pri", "vate> Go"]) + notes.flush()
    assert out == "one. Go"

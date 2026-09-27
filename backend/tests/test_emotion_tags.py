"""Cảm xúc Peto tự chọn cho câu trả lời Companion: thẻ kiểu AIRI bị gỡ khỏi chữ, cảm xúc đi riêng tới nhân vật."""
import pytest

import companion_memory
import db
from emotion_tags import EMOTIONS, MarkerFilter, emotion_of, first, strip
from persona import COMPANION_SYSTEM_PROMPT
from tests.conftest import TEST_OWNER, read_events


async def turn(client, message: str, conversation: str | None = None, mode: str = "companion") -> list[dict]:
    body = {"message": message, "mode": mode}
    if conversation:
        body["conversation_id"] = conversation
    async with client.stream("POST", "/api/chat", json=body) as response:
        return await read_events(response)


def shown(events: list[dict]) -> str:
    return "".join(event["text"] for event in events if event["type"] == "delta")


async def test_the_emotion_reaches_the_stage_before_the_words_and_never_the_text(client):
    events = await turn(client, "Mình vừa thi đậu rồi nè __camxuc__:happy")
    kinds = [event["type"] for event in events]
    assert kinds.index("emotion") < kinds.index("delta")
    assert [event["emotion"] for event in events if event["type"] == "emotion"] == ["happy"]
    assert "<|" not in shown(events) and shown(events).startswith("Mình đã nhận tin nhắn")

    conversation = events[0]["conversation_id"]
    stored = await db.get_messages(TEST_OWNER, conversation)
    assert stored[-1]["content"].startswith("<|EMOTE_HAPPY|>")
    for url in ("/api/companion", f"/api/conversations/{conversation}/messages"):
        reply = [item for item in (await client.get(url)).json()["messages"] if item["role"] == "assistant"][-1]
        assert reply["emotion"] == "happy" and "<|" not in reply["content"]


async def test_emotion_and_private_note_in_one_reply(client):
    events = await turn(client, "Chọn một số đi __camxuc__:think __bimat__:số 7")
    assert [event["emotion"] for event in events if event["type"] == "emotion"] == ["think"]
    assert shown(events) == "Mình chọn xong rồi. Đoán đi!"


async def test_unknown_or_missing_markers_send_no_emotion(client):
    events = await turn(client, "Kể chuyện đi __camxuc__:banana")
    assert not [event for event in events if event["type"] == "emotion"]
    assert "<|" not in shown(events)
    events = await turn(client, "Kể chuyện tiếp đi")
    assert not [event for event in events if event["type"] == "emotion"]


async def test_the_chat_tab_keeps_markers_as_written(client):
    events = await turn(client, "Giải thích cú pháp <|x|> __camxuc__:happy", mode="chat")
    assert not [event for event in events if event["type"] == "emotion"]
    assert "<|EMOTE_HAPPY|>" in shown(events)


def test_the_companion_prompt_lists_the_nine_airi_emotions():
    for emotion in EMOTIONS:
        assert f"<|EMOTE_{emotion.upper()}|>" in COMPANION_SYSTEM_PROMPT


def test_memory_and_summaries_never_see_markers():
    rows = [{"role": "user", "content": "Mình đậu rồi"}, {"role": "assistant", "content": "<|EMOTE_HAPPY|> Tuyệt quá!"}]
    assert "<|" not in companion_memory._prompt([], rows)
    assert "<|" not in companion_memory._summary_prompt("", rows)


def test_marker_names_follow_airi_and_common_variants():
    assert emotion_of("EMOTE_HAPPY") == emotion_of("EMOTION_HAPPY") == emotion_of("happy") == "happy"
    assert emotion_of("EMOTE_SURPRISE") == "surprised" and emotion_of("thinking") == "think"
    assert emotion_of("DELAY:1") is None and emotion_of("EMOTE_BANANA") is None
    assert first("<|DELAY:1|> <|EMOTE_SAD|> ừ <|EMOTE_HAPPY|>") == "sad"
    assert first("không có thẻ") is None


CASES = [
    "<|EMOTE_HAPPY|> Congrats, that's huge!",
    "<|EMOTE_THINK|>Hmm, let me see.",
    "Oh! <|EMOTE_SURPRISED|> Really?",
    "Tim <3 và a < b, cả <| này không phải thẻ vì nó dài quá mức cho phép của một thẻ ngắn",
    "Hai thẻ <|EMOTE_SAD|> ở đây <|DELAY:1|> nữa.",
    "Thẻ rỗng <||> và <|a|b|> không tính.",
    "Chưa khép <|EMOTE_HAP",
    "Không có thẻ nào.",
]


def same(left: str, right: str) -> bool:
    return " ".join(left.split()) == " ".join(right.split())


@pytest.mark.parametrize("text", CASES)
def test_the_stream_filter_matches_strip_however_the_text_is_cut(text):
    expected, emotion = strip(text), first(text)
    for size in range(1, len(text) + 1):
        markers = MarkerFilter()
        out = "".join(markers.feed(text[i:i + size]) for i in range(0, len(text), size)) + markers.flush()
        assert same(out, expected) and markers.emotion == emotion, (size, out)
    for cut in range(len(text) + 1):
        markers = MarkerFilter()
        out = markers.feed(text[:cut]) + markers.feed(text[cut:]) + markers.flush()
        assert same(out, expected) and markers.emotion == emotion, (cut, out)


def test_the_emotion_is_announced_once_and_spacing_stays_clean():
    markers = MarkerFilter()
    assert markers.feed("<|EMOTE_HA") == "" and markers.take_emotion() is None
    assert markers.feed("PPY|> Yay") == "Yay" and markers.take_emotion() == "happy"
    assert markers.feed(" <|EMOTE_SAD|> ok") == " ok" and markers.take_emotion() is None
    assert strip("<|EMOTE_HAPPY|> Congrats!") == "Congrats!"
    assert strip("Oh! <|EMOTE_SURPRISED|> Really?") == "Oh! Really?"

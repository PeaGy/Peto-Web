"""Tên hội thoại là câu tóm tắt do AI đặt, không phải tin nhắn đầu bị cắt."""

from __future__ import annotations

import asyncio

import pytest

import titles
from conftest import read_events


async def _send(client, message: str, conversation_id: str = "") -> tuple[str, list[dict]]:
    body = {"message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    events = await read_events(await client.post("/api/chat", json=body))
    meta = next(event for event in events if event["type"] == "meta")
    return meta["conversation_id"], events


async def _title(client, conversation_id: str) -> str:
    body = (await client.get("/api/conversations")).json()
    return next(item["title"] for item in body["conversations"] if item["id"] == conversation_id)


async def test_ten_la_tom_tat_chu_khong_phai_tin_nhan_dau(client):
    conversation_id, _ = await _send(client, "asyncio trong python là gì vậy ad")
    # Nhà cung cấp giả rút còn sáu từ đầu và viết hoa chữ cái đầu.
    assert await _title(client, conversation_id) == "Asyncio trong python là gì vậy"


async def test_khong_doi_ten_o_luot_sau(client):
    conversation_id, _ = await _send(client, "chào Peto")
    before = await _title(client, conversation_id)
    await _send(client, "kể chuyện gì vui đi", conversation_id)
    assert await _title(client, conversation_id) == before


async def test_dat_ten_hong_thi_giu_ten_cat_tam(client, monkeypatch):
    async def vo(*args, **kwargs):
        raise RuntimeError("nhà cung cấp chết giữa chừng")

    monkeypatch.setattr(titles, "suggest_title", vo)
    conversation_id, events = await _send(client, "một câu hỏi rất dài dòng về cuộc đời")
    assert events[-1]["type"] == "done"
    assert await _title(client, conversation_id) == "một câu hỏi rất dài dòng về cuộc đời"


async def test_dat_ten_cham_thi_khong_giu_luot_chat(client, monkeypatch):
    """Lượt đặt tên treo thì vẫn phải trả lời xong và giữ tên cắt tạm."""

    async def cham(*args, **kwargs):
        await asyncio.sleep(30)
        return "Không bao giờ tới đây"

    monkeypatch.setattr(titles, "suggest_title", cham)
    monkeypatch.setattr(titles, "WAIT_SECONDS", 0.1)
    conversation_id, events = await _send(client, "hỏi nhanh thôi")
    assert events[-1]["type"] == "done"
    assert await _title(client, conversation_id) == "hỏi nhanh thôi"


@pytest.mark.parametrize("raw, expected", [
    ('"Học Python cơ bản"', "Học Python cơ bản"),
    ("Tiêu đề: Học Python cơ bản", "Học Python cơ bản"),
    ("Học Python cơ bản.", "Học Python cơ bản"),
    ("  Học   Python\ncơ bản  ", "Học Python cơ bản"),
    ("**Học Python**", "Học Python"),
])
def test_lam_gon_ten(raw, expected):
    assert titles.clean_title(raw) == expected


def test_ten_dai_bi_cat_gon():
    title = titles.clean_title("Cách dùng " + "package manager " * 10)
    assert len(title) <= titles.MAX_TITLE_CHARS
    assert title.endswith("…")

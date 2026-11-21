"""Đồng bộ trực tiếp tab Trò chuyện giữa các thiết bị (20/11/2026, chủ web chọn kiểu Claude): khi một lượt chat chạy,
mọi tab khác của cùng tài khoản thấy câu hỏi, nhật ký "Đang làm" và chữ chạy dần như tab đã gửi.

Câu trả lời của Chat được tạo trên máy chủ, nên chỉ cần phát lại đúng các sự kiện SSE mà tab gửi nhận được:
``relay`` bọc luồng của ``POST /api/chat`` và chép từng sự kiện (từ ``meta`` trở đi) vào ``hub``; mỗi tab mở
``GET /api/chat/live`` một lần cho cả tài khoản và nhận chúng, bọc trong ``{"type": "live", "request_id", "event"}``.
Tab tự gửi bỏ qua ``request_id`` của chính nó. Tab mở giữa chừng (hay kết nối lại) nhận lại lượt đang chạy từ đầu.

Mọi thứ ở trong bộ nhớ của tiến trình, như sổ lượt chat và hàng chờ: Peto Web chạy một tiến trình. Không lưu gì thêm
xuống database; lượt xong thì các tab đọc lại bản đã lưu qua API thường. Log không bao giờ ghi nội dung.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, field

log = logging.getLogger('peto_web.chat_live')

MAX_SUBSCRIBERS_PER_OWNER = 20
# Tab đọc chậm quá số sự kiện này thì bị ngắt; nó tự kết nối lại và nhận lại lượt đang chạy từ đầu.
MAX_QUEUE = 2_000
# Một lượt giữ lại tối đa chừng này để phát cho tab mở giữa chừng; quá thì tab đó chỉ thấy "đang trả lời" rồi tải lại.
MAX_REPLAY_BYTES = 4_000_000
KEEPALIVE_SECONDS = 20
TERMINAL = {'done', 'error', 'stopped'}


@dataclass
class _Turn:
    request_id: str
    conversation_id: str
    events: list[str] = field(default_factory=list)
    size: int = 0
    truncated: bool = False


@dataclass(eq=False)
class _Subscriber:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(MAX_QUEUE))
    closed: bool = False


def frame(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


class Hub:
    def __init__(self):
        self.subscribers: dict[str, set[_Subscriber]] = {}
        self.turns: dict[str, dict[str, _Turn]] = {}

    def subscribe(self, owner: str) -> tuple[_Subscriber, list[str]] | None:
        """Đăng ký một tab; trả về kèm các sự kiện của những lượt đang chạy để phát lại. None khi tài khoản đã quá
        nhiều tab. Không có ``await`` ở giữa nên không sót sự kiện nào giữa ảnh chụp và lúc đăng ký."""
        current = self.subscribers.setdefault(owner, set())
        if len(current) >= MAX_SUBSCRIBERS_PER_OWNER:
            return None
        subscriber = _Subscriber()
        current.add(subscriber)
        replay = []
        for turn in self.turns.get(owner, {}).values():
            if turn.truncated:
                replay.append(frame({'type': 'live', 'request_id': turn.request_id,
                                     'conversation_id': turn.conversation_id, 'event': {'type': 'live_partial'}}))
            else:
                replay.extend(turn.events)
        return subscriber, replay

    def unsubscribe(self, owner: str, subscriber: _Subscriber) -> None:
        current = self.subscribers.get(owner)
        if current is not None:
            current.discard(subscriber)
            if not current:
                self.subscribers.pop(owner, None)

    def _send(self, owner: str, data: str) -> None:
        for subscriber in list(self.subscribers.get(owner, ())):
            if subscriber.closed:
                continue
            try:
                subscriber.queue.put_nowait(data)
            except asyncio.QueueFull:
                # Tab không đọc kịp: ngắt nó, nó tự kết nối lại và nhận lại từ đầu lượt.
                subscriber.closed = True
                self.unsubscribe(owner, subscriber)

    def publish(self, owner: str, request_id: str, conversation_id: str, event: dict) -> None:
        data = frame({'type': 'live', 'request_id': request_id, 'conversation_id': conversation_id, 'event': event})
        turns = self.turns.setdefault(owner, {})
        turn = turns.get(request_id)
        if turn is None:
            turn = turns[request_id] = _Turn(request_id, conversation_id)
        if not turn.truncated:
            turn.size += len(data)
            if turn.size > MAX_REPLAY_BYTES:
                turn.truncated, turn.events = True, []
            else:
                turn.events.append(data)
        self._send(owner, data)
        if event.get('type') in TERMINAL or event.get('type') == 'live_end':
            turns.pop(request_id, None)
            if not turns:
                self.turns.pop(owner, None)

    def finish(self, owner: str, request_id: str) -> None:
        """Luồng của tab gửi đã đóng mà chưa có sự kiện kết thúc (tab gửi ngắt, máy chủ dừng lượt): báo các tab khác
        để chúng đọc lại bản đã lưu."""
        turn = self.turns.get(owner, {}).get(request_id)
        if turn is not None:
            self.publish(owner, request_id, turn.conversation_id, {'type': 'live_end'})


hub = Hub()


def _events(chunk: str) -> list[dict]:
    found = []
    for block in chunk.split('\n\n'):
        for line in block.split('\n'):
            if line.startswith('data: '):
                try:
                    payload = json.loads(line[6:])
                except ValueError:
                    continue
                if isinstance(payload, dict):
                    found.append(payload)
    return found


async def relay(owner: str, request_id: str | None, stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """Chuyển nguyên luồng cho tab gửi, đồng thời phát cho các tab khác từ sự kiện ``meta`` (lúc tin người dùng đã
    lưu và đã biết hội thoại). Sự kiện trước đó (đọc tệp mới gửi, xếp hàng) chỉ tab gửi thấy."""
    conversation_id: str | None = None
    try:
        # aclosing: tab gửi ngắt thì luồng gốc phải được đóng ngay tại đây (nó lưu phần trả lời dở trong lúc đóng), không
        # đợi bộ dọn rác.
        async with aclosing(stream) as inner:
            async for chunk in inner:
                if request_id:
                    try:
                        for event in _events(chunk):
                            if conversation_id is None and event.get('type') == 'meta':
                                conversation_id = str(event.get('conversation_id') or '') or None
                            if conversation_id and event.get('type') != 'player_command':
                                hub.publish(owner, request_id, conversation_id, event)
                    except Exception:  # noqa: BLE001 - phát cho tab khác hỏng không được làm hỏng lượt chat
                        log.exception('chat_live publish_failed')
                yield chunk
    finally:
        if request_id and conversation_id:
            hub.finish(owner, request_id)


def full(owner: str) -> bool:
    return len(hub.subscribers.get(owner, ())) >= MAX_SUBSCRIBERS_PER_OWNER


async def stream(owner: str) -> AsyncIterator[str]:
    """Luồng của một tab. Đăng ký ngay khi luồng bắt đầu chạy (không trước đó), nên tab nào ngắt sớm cũng không để lại
    chỗ đăng ký mồ côi."""
    joined = hub.subscribe(owner)
    if joined is None:
        yield frame({'type': 'live_full'})
        return
    subscriber, replay = joined
    try:
        yield frame({'type': 'live_ready'})
        for data in replay:
            yield data
        while not subscriber.closed:
            try:
                data = await asyncio.wait_for(subscriber.queue.get(), KEEPALIVE_SECONDS)
            except TimeoutError:
                # Giữ kết nối qua Cloudflare (ngắt sau 100 giây im lặng) và cho trình duyệt biết máy chủ còn đó.
                yield ': ping\n\n'
                continue
            yield data
    finally:
        hub.unsubscribe(owner, subscriber)

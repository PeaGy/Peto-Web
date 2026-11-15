"""Giới hạn thời gian một lần gọi model của Agent (CLI và ứng dụng máy tính), từ 15/11/2026.

Trước đó một lần gọi bị cắt sau tổng ``AGENT_STEP_TIMEOUT_SECONDS`` (300 giây), kể cả khi model đang viết đều: Peto viết
cả bản báo cáo 30 trang trong một lời gọi công cụ thì lần nào cũng bị cắt, và ứng dụng gửi lại y nguyên năm lần. Nay
lần gọi chỉ dừng khi dịch vụ AI im lặng quá lâu (mọi sự kiện của ``agent_step`` đều tính, kể cả "pulse"), và không bao
giờ quá ``AGENT_STEP_MAX_SECONDS``, như cách Chat làm từ 5/10/2026.

Khoảng im lặng tùy dịch vụ: OpenAI và Claude gửi dần đối số công cụ nên im 5 phút (``AGENT_STEP_TIMEOUT_SECONDS``) là
kẹt; xAI trả nguyên lời gọi công cụ một lần khi viết xong, nên Grok viết tệp dài là im hẳn nhiều phút
(``AGENT_XAI_SILENCE_SECONDS``, mặc định bằng trần tổng).

Dùng::

    limits = StepLimits(model.service)
    async with asyncio.timeout_at(limits.next()) as scope:
        async for event in agent_step(...):
            scope.reschedule(limits.next())
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress

from ai.agent import AgentEvent
from core import config


def silence_seconds(service: str) -> float:
    return config.AGENT_XAI_SILENCE_SECONDS if service == "xai" else config.AGENT_STEP_TIMEOUT_SECONDS


class StepLimits:
    def __init__(self, service: str) -> None:
        self.loop = asyncio.get_running_loop()
        self.silence = silence_seconds(service)
        self.deadline = self.loop.time() + config.AGENT_STEP_MAX_SECONDS

    def next(self) -> float:
        """Mốc dừng tính từ lúc này: hết khoảng im lặng cho phép, hoặc trần tổng nếu tới trước."""
        return min(self.deadline, self.loop.time() + self.silence)

    def overall(self) -> bool:
        """Lần dừng vừa rồi là do trần tổng (model vẫn đang chạy), không phải do im lặng."""
        return self.loop.time() >= self.deadline - 1.0

    def failure(self, produced: bool) -> tuple[str, str]:
        """Mã lỗi và lời báo khi lần gọi bị dừng. ``produced``: model đã kịp gửi gì đó (bước đã tính, không hoàn).

        Ứng dụng máy tính (pi-ai) tự gửi lại lỗi có chữ "timeout". Chỉ dùng chữ đó khi chưa có gì (bước được hoàn),
        như một lần kẹt mạng. Đã có phản hồi mà gửi lại y nguyên thì tốn thêm bước, còn chạm trần tổng thì lần gửi lại
        cũng chạm như cũ, nên hai trường hợp đó dùng mã và lời báo không có chữ ấy.
        """
        if self.overall():
            minutes = round(config.AGENT_STEP_MAX_SECONDS / 60)
            return ("step_too_long", f"Lần gọi này đã chạy hơn {minutes} phút nên Peto dừng lại. Nhờ Peto chia việc thành "
                                     "nhiều phần nhỏ hơn rồi làm tiếp nhé.")
        if produced:
            return ("stalled", "Dịch vụ AI im lặng quá lâu giữa chừng nên Peto dừng lần gọi này. Nhắn Peto làm tiếp nhé.")
        return ("timeout", "Dịch vụ AI im lặng quá lâu nên Peto dừng lần gọi này.")


async def ticking(events: AsyncIterator[AgentEvent], every: float) -> AsyncIterator[AgentEvent]:
    """Chuyển tiếp ``events``, chen một AgentEvent("tick") mỗi ``every`` giây không có gì, để nơi gọi gửi dòng giữ kết
    nối (Cloudflare cắt luồng im lặng, mà xAI có thể im nhiều phút). "tick" là đồng hồ của máy chủ, không phải dấu hiệu
    dịch vụ AI còn sống: nơi gọi không được tính nó vào khoảng im lặng."""
    iterator = events.__aiter__()
    pending: asyncio.Future | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=every)
            if not done:
                yield AgentEvent("tick")
                continue
            task, pending = pending, None
            try:
                event = task.result()
            except StopAsyncIteration:
                return
            yield event
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(BaseException):
                await pending
        with suppress(BaseException):
            await iterator.aclose()  # type: ignore[attr-defined]

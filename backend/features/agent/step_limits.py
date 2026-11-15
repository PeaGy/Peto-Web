"""Giới hạn thời gian một lần gọi model của Agent (CLI và ứng dụng máy tính), từ 15/11/2026.

Trước đó một lần gọi bị cắt sau tổng ``AGENT_STEP_TIMEOUT_SECONDS`` (300 giây), kể cả khi model đang viết đều: Peto viết
cả bản báo cáo 30 trang trong một lời gọi công cụ thì lần nào cũng bị cắt, và ứng dụng gửi lại y nguyên năm lần. Nay
lần gọi chỉ dừng khi dịch vụ AI im lặng quá ``AGENT_STEP_TIMEOUT_SECONDS`` (mọi sự kiện của ``agent_step`` đều tính,
kể cả "pulse"), và không bao giờ quá ``AGENT_STEP_MAX_SECONDS``, như cách Chat làm từ 5/10/2026.

Dùng::

    limits = StepLimits()
    async with asyncio.timeout_at(limits.next()) as scope:
        async for event in agent_step(...):
            scope.reschedule(limits.next())
"""

from __future__ import annotations

import asyncio

from core import config


class StepLimits:
    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.deadline = self.loop.time() + config.AGENT_STEP_MAX_SECONDS

    def next(self) -> float:
        """Mốc dừng tính từ lúc này: hết khoảng im lặng cho phép, hoặc trần tổng nếu tới trước."""
        return min(self.deadline, self.loop.time() + config.AGENT_STEP_TIMEOUT_SECONDS)

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

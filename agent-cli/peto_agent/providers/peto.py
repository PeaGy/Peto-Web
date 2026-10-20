"""Nguồn Peto: lượt gọi model đi qua máy chủ Peto (/api/agent/step), như trước khi có cổng yêu cầu.

Máy chủ vẫn giữ đăng nhập, thương lượng khả năng, lời nhắc, schema công cụ, hạn mức bước và quyền dùng model.
Nguồn này chỉ chuyển nguyên nội dung lượt gọi sang transport đang ghi nhật ký của phiên.
"""

from __future__ import annotations

from collections.abc import Iterator

from .contract import ModelRequest

STEP_PATH = "/api/agent/step"


class PetoSource:
    id = "peto"
    # Transport của phiên (RuntimeClient.stream) đã ghi nhật ký bền cho lượt gọi máy chủ Peto.
    journals_itself = True

    def stream(self, request: ModelRequest, transport, **options) -> Iterator[dict]:
        return transport.stream(STEP_PATH, request.body, source=self.id, **options)

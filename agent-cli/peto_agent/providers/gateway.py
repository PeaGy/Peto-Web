"""Cổng yêu cầu model của phiên (mốc M1–M2): mọi lượt gọi model đi qua đây, kể cả đặt tên, /btw và agent con.

Cổng chọn nguồn theo Selection của lượt gọi rồi giao cho nguồn đó; vòng chạy, công cụ và cách xử lý sự kiện vẫn ở
phiên. Mọi nguồn đều được ghi vào nhật ký bền của phiên: nguồn Peto tự ghi qua transport (RuntimeClient.stream), các
nguồn khác được cổng bọc bằng RuntimeClient.journaled, nên không lượt gọi nào thoát khỏi nhật ký.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from .contract import ModelRequest, ModelSourceError, Selection
from .openai_key import OpenAIKeySource
from .peto import PetoSource


class ModelGateway:
    def __init__(self, transport: Callable[[], object]):
        # Transport lấy lúc gọi (không giữ sẵn), để phiên đổi hay bọc lại transport vẫn có hiệu lực.
        self._transport = transport
        self.sources = {PetoSource.id: PetoSource(), OpenAIKeySource.id: OpenAIKeySource()}

    def request(self, purpose: str, body: dict, selection: Selection) -> ModelRequest:
        """Chụp một lượt gọi: bản sao nông của nội dung (và context) để lượt đang chạy không đổi theo phiên."""
        body = dict(body)
        if isinstance(body.get("context"), dict):
            body["context"] = dict(body["context"])
        return ModelRequest(purpose, selection, body)

    def stream(self, request: ModelRequest, *, transport=None, **options) -> Iterator[dict]:
        source = self.sources.get(request.selection.source)
        if source is None:
            raise ModelSourceError(f"Chưa có nguồn model “{request.selection.source}”.")
        transport = transport if transport is not None else self._transport()
        if getattr(source, "journals_itself", False):
            return source.stream(request, transport, **options)
        return transport.journaled(request.body, source.id, lambda: source.stream(request, transport, **options))

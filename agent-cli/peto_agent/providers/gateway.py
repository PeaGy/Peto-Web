"""Cổng yêu cầu model của phiên (mốc M1–M2): mọi lượt gọi model đi qua đây, kể cả đặt tên, /btw và agent con.

Cổng chọn nguồn theo Selection của lượt gọi rồi giao cho nguồn đó; vòng chạy, công cụ và cách xử lý sự kiện vẫn ở
phiên. Mọi nguồn đều được ghi vào nhật ký bền của phiên: nguồn Peto tự ghi qua transport (RuntimeClient.stream), các
nguồn khác được cổng bọc bằng RuntimeClient.journaled, nên không lượt gọi nào thoát khỏi nhật ký.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator

from .contract import ModelRequest, ModelSourceError, Selection
from .openai_key import OpenAIKeySource
from .peto import PetoSource


class ModelGateway:
    def __init__(self, transport: Callable[[], object]):
        # Transport lấy lúc gọi (không giữ sẵn), để phiên đổi hay bọc lại transport vẫn có hiệu lực.
        self._transport = transport
        self.sources = {PetoSource.id: PetoSource(), OpenAIKeySource.id: OpenAIKeySource()}
        # Token mỗi nguồn và kết nối đã dùng trong phiên, theo số nhà cung cấp trả về ở sự kiện done (cho /usage, M4).
        # Là số ước tính của phiên trên máy này, không phải hóa đơn hay hạn mức chính thức.
        self.usage: dict[tuple[str, str | None], dict[str, int]] = {}
        self._usage_lock = threading.Lock()

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
            events = source.stream(request, transport, **options)
        else:
            events = transport.journaled(request.body, source.id, lambda: source.stream(request, transport, **options))
        return _Counted(events, lambda usage: self._record(request.selection, usage))

    def _record(self, selection: Selection, usage) -> None:
        usage = usage if isinstance(usage, dict) else {}
        details = usage.get("input_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else usage.get("cached_tokens")
        values = {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                  "cached_tokens": cached}
        with self._usage_lock:
            row = self.usage.setdefault((selection.source, selection.connection),
                                        {"calls": 0, "reported": 0, "input_tokens": 0, "output_tokens": 0,
                                         "cached_tokens": 0})
            row["calls"] += 1
            if all(type(values[name]) is int and values[name] >= 0 for name in ("input_tokens", "output_tokens")):
                row["reported"] += 1
                for name, value in values.items():
                    if type(value) is int and value >= 0:
                        row[name] += value


class _Counted:
    """Bọc luồng sự kiện để đếm usage ở sự kiện done. Không dùng generator: đóng một generator chưa chạy thì không
    đóng được luồng bên trong (kết nối, luồng đọc SSE)."""

    def __init__(self, events, on_done: Callable[[object], None]):
        self._events = events
        self._iterator = iter(events)
        self._on_done = on_done

    def __iter__(self):
        return self

    def __next__(self) -> dict:
        event = next(self._iterator)
        if isinstance(event, dict) and event.get("type") == "done":
            self._on_done(event.get("usage"))
        return event

    def close(self) -> None:
        close = getattr(self._events, "close", None)
        if close is not None:
            close()

"""Nguồn khóa OpenAI riêng của người dùng (lộ trình nhiều nguồn, M3): CLI gọi thẳng Responses API của OpenAI.

Không qua máy chủ Peto và không tính bước Peto. Chỉ dẫn, schema công cụ và ngân sách lấy từ ``peto_agent.bundle`` (bản
chép của chính máy chủ Peto), nên Peto làm việc như khi chạy qua máy chủ. Khóa đọc từ kho DPAPI ngay trước khi gọi, chỉ
nằm trong phần đầu yêu cầu tới đúng địa chỉ API của kết nối. Tìm web của OpenAI chưa bật ở nguồn này.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from .. import connections, credentials
from ..bundle import assembly
from .contract import ModelRequest, ModelSourceError
from .transport import ProviderHTTP, ProviderHTTPError

SERVICE = "openai"
# Trần output của nguồn này, như máy chủ Peto (PETO_OPENAI_MAX_OUTPUT_TOKENS): suy nghĩ cũng tính vào output, trần thấp
# giữ một bước không tiêu quá nhiều tiền của người dùng.
OUTPUT_CAP = 16_000
MAX_REQUEST_BYTES = 16 * 1024 * 1024
EFFORTS = ("low", "medium", "high")
OVERFLOW_CODES = {"context_length_exceeded", "context_window_exceeded", "prompt_too_long"}
OVERFLOW_TEXT = ("maximum context length", "context window exceeded", "prompt is too long",
                 "input token count exceeds", "exceeds the context window")


def local_clock() -> str:
    """Mốc giờ trên máy người dùng, cùng định dạng mốc giờ của máy chủ (làm tròn theo giờ). Windows chỉ cho tên múi giờ
    kiểu "SE Asia Standard Time" (có máy còn trả tên vùng khác cùng độ lệch), nên chỉ ghi độ lệch UTC thật của máy."""
    now = datetime.now().astimezone()
    offset = now.strftime("%z") or "+0000"
    return assembly.time_text(now.strftime("%Y-%m-%d"), now.strftime("%H"), "local machine time",
                              f"UTC{offset[:3]}:{offset[3:]}")


def _overflow(code: str, message: str) -> bool:
    text = (message or "").lower()
    return code in OVERFLOW_CODES or any(phrase in text for phrase in OVERFLOW_TEXT)


class OpenAIKeySource:
    id = "openai-key"

    def __init__(self, *, clock=local_clock, http=ProviderHTTP):
        self.clock, self.http = clock, http

    def models(self, connection: connections.Connection) -> tuple[str, ...]:
        """Model của kết nối mà danh mục biết giới hạn (lưu lúc kiểm khóa)."""
        return tuple(model for model in connection.models if model in assembly.CATALOG)

    def check(self, endpoint: str, secret: str) -> tuple[str, ...]:
        """Kiểm khóa bằng danh sách model (không tốn token); trả các model danh mục Peto biết giới hạn."""
        payload = self.http(endpoint, {"Authorization": f"Bearer {secret}"}).json("GET", "/models")
        names = {row.get("id") for row in payload.get("data") or [] if isinstance(row, dict)}
        return tuple(slug for slug in assembly.CATALOG if slug.startswith("gpt-") and slug in names)

    def stream(self, request: ModelRequest, transport=None, **options) -> Iterator[dict]:
        connection = connections.get(request.selection.connection)
        if connection is None or connection.source != self.id:
            raise ModelSourceError("Không tìm thấy kết nối OpenAI này trên máy. Chạy peto connect openai để kết nối lại.")
        try:
            secret = credentials.load(connection.id)
        except credentials.CredentialError as err:
            raise ModelSourceError(str(err)) from None
        return self._events(request, connection, secret, options.get("on_idle"))

    def _events(self, request, connection, secret, on_idle) -> Iterator[dict]:
        body = request.body
        context = body.get("context") if isinstance(body.get("context"), dict) else {}
        items = body.get("input") if isinstance(body.get("input"), list) else []
        slug = request.selection.model
        step = assembly.prepare(context, service=SERVICE, web_search=False, clock=self.clock())
        info = assembly.limits(SERVICE, slug, OUTPUT_CAP)
        budget = assembly.request_budget(info, slug, step.instructions, step.tools, items,
                                         compact=step.special == "compact", max_request_bytes=MAX_REQUEST_BYTES)
        budgeting = "context_budget" in (context.get("features") or [])
        if budgeting:
            yield {"type": "meta", "context_budget": budget}
            if budget["max_output_tokens"] < 1024 or (step.special is None and budget["request_tokens"] >= budget["ceiling"]):
                yield {"type": "error", "code": "context_overflow",
                       "message": "Ngữ cảnh đã tới ngân sách model; cần tóm tắt trước khi tiếp tục."}
                return
        payload = self._payload(step, budget, items, request.selection)
        purpose = step.special or ("explore" if step.exploring else None)
        produced = False
        client = self.http(connection.endpoint, {"Authorization": f"Bearer {secret}"})
        try:
            for event in client.stream("/responses", payload, on_idle=on_idle):
                kind = event.get("type", "")
                if kind == "response.reasoning_summary_text.delta" and event.get("delta"):
                    produced = True
                    yield {"type": "thinking", "text": str(event["delta"])}
                elif kind == "response.output_text.delta" and event.get("delta"):
                    produced = True
                    yield {"type": "delta", "text": str(event["delta"])}
                elif kind == "response.completed":
                    response = event.get("response") if isinstance(event.get("response"), dict) else {}
                    if response.get("status", "completed") != "completed":
                        yield self._error("OpenAI chưa làm xong bước này. Thử lại nhé.", retryable=not produced)
                        return
                    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
                    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
                    output = [item for item in response.get("output") or [] if isinstance(item, dict)]
                    yield {"type": "done", "output": output,
                           "usage": {"input_tokens": int(usage.get("input_tokens") or 0),
                                     "output_tokens": int(usage.get("output_tokens") or 0),
                                     **({"cached_tokens": details["cached_tokens"]}
                                        if type(details.get("cached_tokens")) is int else {})},
                           **({"purpose": purpose} if purpose else {})}
                    return
                elif kind == "response.incomplete":
                    yield self._error("Bước này chạm giới hạn độ dài output của model. Thử chia nhỏ yêu cầu nhé.")
                    return
                elif kind in {"response.failed", "error"}:
                    error = (event.get("response") or {}).get("error") if kind == "response.failed" else event
                    yield self._failed(error if isinstance(error, dict) else {}, produced)
                    return
            yield self._error("Kết nối tới OpenAI bị ngắt trước khi xong bước này. Thử lại nhé.", retryable=not produced)
        except ProviderHTTPError as err:
            yield self._http_error(err, connection, slug, produced)

    def _payload(self, step, budget: dict, items: list, selection) -> dict:
        return {"model": selection.model, "instructions": step.instructions, "input": items, "tools": step.tools,
                "max_output_tokens": budget["max_output_tokens"], "reasoning": {"effort": selection.effort},
                "include": ["reasoning.encrypted_content"], "store": False, "stream": True,
                **({"tool_choice": "none"} if step.final and step.tools else {})}

    def _failed(self, error: dict, produced: bool) -> dict:
        """Sự kiện response.failed hay error giữa luồng."""
        if _overflow(str(error.get("code") or ""), str(error.get("message") or "")) and not produced:
            return {"type": "error", "code": "context_overflow",
                    "message": "Ngữ cảnh vượt giới hạn model; cần tóm tắt trước khi tiếp tục."}
        return self._error("OpenAI gặp lỗi ở bước này. Thử lại nhé.", retryable=not produced)

    @staticmethod
    def _error(message: str, *, retryable: bool = False, code: str | None = None) -> dict:
        return {"type": "error", "message": message, **({"retryable": True} if retryable else {}),
                **({"code": code} if code else {})}

    def _http_error(self, err: ProviderHTTPError, connection, slug: str, produced: bool) -> dict:
        label = connection.label
        if err.status == 0:
            return self._error(f"Không kết nối được OpenAI ({label}). Kiểm tra mạng rồi thử lại.",
                               retryable=not produced, code="network")
        if err.status == 401:
            return self._error(f"Khóa OpenAI của kết nối “{label}” không dùng được (sai hoặc đã bị thu hồi). Chạy "
                               "peto connect openai để nhập khóa khác.", code="authentication")
        if err.status == 403:
            return self._error(f"Khóa OpenAI của kết nối “{label}” không được dùng model {slug}.", code="permission")
        if err.status == 404:
            return self._error(f"Tài khoản OpenAI của kết nối “{label}” không có model {slug}.", code="capability")
        if err.status == 429 and err.code == "insufficient_quota":
            return self._error(f"Tài khoản OpenAI của kết nối “{label}” đã hết hạn mức hoặc hết tiền. Nạp thêm trên "
                               "trang OpenAI, hoặc gõ /model để chọn nguồn khác.", code="quota")
        if err.status == 429:
            return self._error("OpenAI đang giới hạn lượt cho khóa của bạn. Đợi chút rồi thử lại nhé.",
                               retryable=not produced, code="rate_limit")
        if err.status in {400, 413} and _overflow(err.code, err.message) and not produced:
            return self._error("Ngữ cảnh vượt giới hạn model; cần tóm tắt trước khi tiếp tục.", code="context_overflow")
        if err.status in {400, 413}:
            return self._error("OpenAI không nhận nội dung bước này. Gõ /new để bắt đầu hội thoại mới nhé.",
                               code="invalid_request")
        if 300 <= err.status < 400:
            return self._error(err.message, code="invalid_request")
        return self._error("OpenAI đang gặp sự cố. Thử lại sau nhé.", retryable=err.status >= 500 and not produced,
                           code="server")

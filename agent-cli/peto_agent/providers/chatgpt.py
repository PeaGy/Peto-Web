"""Nguồn "gói ChatGPT" (lộ trình nhiều nguồn, M5): gọi Responses API của OpenAI bằng access token đăng nhập ChatGPT, tính
vào hạn mức gói của người dùng.

Cùng vòng chạy, chỉ dẫn và schema công cụ với nguồn khóa OpenAI (kế thừa ``OpenAIKeySource``), khác ở yêu cầu theo
tài liệu "Preview limitations" (đọc 2026-10-21): ``store: false`` và ``stream: true``; không gửi ``max_output_tokens`` hay
các tham số bị cấm; công cụ function phải nằm trong một namespace. Ngân sách ngữ cảnh vẫn tính trên máy, chỉ không gửi
trần output. Lỗi theo bảng "Errors and recovery": hết hạn mức thì chỉ đường tới trang Usage của ChatGPT, không tự chuyển
sang khóa API tính tiền và không đăng nhập lại để chữa lỗi hạn mức.
"""

from __future__ import annotations

from collections.abc import Iterator

from .. import chatgpt_auth, connections, credentials
from .contract import ModelRequest, ModelSourceError
from .openai_key import OpenAIKeySource
from .transport import ProviderHTTPError

NAMESPACE = "peto"
NAMESPACE_DESCRIPTION = "Peto Agent tools that act on the user's local project on this machine."
EFFORTS = ("low", "medium", "high")
# Trường được gửi; mọi trường khác bị bỏ (danh sách trắng, không phải danh sách đen).
ALLOWED = {"model", "instructions", "input", "tools", "tool_choice", "reasoning", "include", "store", "stream",
           "parallel_tool_calls"}
# Trang quản lý mức dùng của ChatGPT (tài liệu không cho địa chỉ cố định) và bài trợ giúp "Using your ChatGPT plan in
# other apps and sites" của OpenAI.
USAGE_PAGE = "ChatGPT → Settings → Usage"
HELP_PAGE = "https://help.openai.com/articles/20001542"
MANAGE_USAGE = f"Manage usage: {USAGE_PAGE}"


def namespaced(items: list) -> list:
    """Lời gọi công cụ trong lịch sử (kể cả từ nguồn khác) mang namespace của Peto; tin vai system bị đường này từ chối
    nên không bao giờ có trong input (chỉ dẫn đi qua ``instructions``)."""
    result = []
    for item in items:
        if not isinstance(item, dict) or (item.get("type") == "message" and item.get("role") == "system"):
            continue
        if item.get("type") == "function_call" and not item.get("namespace"):
            item = {**item, "namespace": NAMESPACE}
        result.append(item)
    return result


class ChatGPTSource(OpenAIKeySource):
    id = "chatgpt-plan"

    def models(self, connection: connections.Connection) -> tuple[str, ...]:
        """Model tài khoản dùng được (danh sách OpenAI trả lúc đăng nhập), chỉ khi có quyền dùng gói."""
        if not connection.extra.get("plan") or connection.extra.get("status") == "signed_out":
            return ()
        return tuple(connection.models)

    def stream(self, request: ModelRequest, transport=None, **options) -> Iterator[dict]:
        connection = connections.get(request.selection.connection)
        if connection is None or connection.source != self.id:
            raise ModelSourceError("Không tìm thấy đăng nhập ChatGPT này trên máy. Gõ /connect để đăng nhập lại.")
        if not connection.extra.get("plan"):
            raise ModelSourceError("Tài khoản ChatGPT này chưa cho phép Peto Agent dùng gói (Use your ChatGPT plan). "
                                   "Gõ /connect, chọn tài khoản để bật, hoặc dùng khóa API riêng.")
        token = self._token(connection)
        return self._attempts(request, connection, token, options.get("on_idle"))

    @staticmethod
    def _token(connection, *, force: bool = False) -> str:
        try:
            return chatgpt_auth.access_token(connection, force=force)
        except chatgpt_auth.AuthError as err:
            raise ModelSourceError(str(err)) from None
        except credentials.CredentialError as err:
            raise ModelSourceError(str(err)) from None

    def _attempts(self, request, connection, token, on_idle) -> Iterator[dict]:
        """Một lần gọi; 401 trước khi có output thì làm mới token một lần rồi gọi lại (token có thể vừa bị thu hồi phía
        OpenAI trước giờ hết hạn)."""
        for attempt in range(2):
            events = self._events(request, connection, token, on_idle)
            for event in events:
                if event.get("type") == "error" and event.get("code") == "reauth":
                    if attempt == 0:
                        break
                    event = {**event, "code": "authentication",
                             "message": f"{event['message']} Gõ /connect để đăng nhập lại."}
                yield event
            else:
                return
            events.close()
            try:
                token = chatgpt_auth.access_token(connections.get(connection.id) or connection, force=True)
            except (chatgpt_auth.AuthError, credentials.CredentialError) as err:
                yield self._error(str(err), code="authentication")
                return

    def _payload(self, step, budget: dict, items: list, selection) -> dict:
        payload = {"model": selection.model, "instructions": step.instructions, "input": namespaced(items),
                   "reasoning": {"effort": selection.effort}, "include": ["reasoning.encrypted_content"],
                   "store": False, "stream": True}
        if step.tools:
            payload["tools"] = [{"type": "namespace", "name": NAMESPACE, "description": NAMESPACE_DESCRIPTION,
                                 "tools": step.tools}]
            if step.final:
                payload["tool_choice"] = "none"
        return {key: value for key, value in payload.items() if key in ALLOWED}

    def _failed(self, error: dict, produced: bool) -> dict:
        code = str(error.get("code") or "")
        if code == "subscription_sharing_usage_limit_exceeded":
            return self._error("Đã chạm giới hạn dùng gói ChatGPT (có thể là giới hạn riêng cho Peto Agent). Peto tạm "
                               f"dừng các yêu cầu tính vào gói. {MANAGE_USAGE}. Hoặc gõ /models để chọn nguồn khác.",
                               code="quota")
        if code in {"subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable"}:
            return self._error("Gói ChatGPT tạm thời chưa dùng được. Thử lại sau ít phút nhé.", retryable=not produced,
                               code="server")
        if code:
            mapped = self._mapped(code, error.get("param"), produced)
            if mapped is not None:
                return mapped
        return super()._failed(error, produced)

    def _mapped(self, code: str, param, produced: bool) -> dict | None:
        if code == "subscription_sharing_user_not_eligible":
            return self._error("Tài khoản ChatGPT này không đủ điều kiện dùng gói trong ứng dụng khác. Gõ /models để "
                               "chọn Peto hay khóa API riêng.", code="permission")
        if code == "subscription_sharing_unsupported_capability":
            what = f" ({str(param)[:60]})" if param else ""
            return self._error(f"Gói ChatGPT không hỗ trợ một phần của bước này{what}. Gõ /models để chọn model khác.",
                               code="capability")
        if code == "subscription_sharing_route_not_supported":
            return self._error("OpenAI không nhận đường gọi này cho gói ChatGPT. Cập nhật peto bằng /update nhé.",
                               code="capability")
        if code in {"chatpass_v2_scope_not_authorized", "chatpass_v2_invalid_authorization_context"}:
            return self._error("OpenAI chưa cấp quyền dùng gói cho đăng nhập này. Gõ /connect để đăng nhập lại và "
                               "chọn Use your ChatGPT plan.", code="permission")
        if code == "subscription_sharing_invalid_user":
            return self._error("OpenAI không nhận đăng nhập ChatGPT này.", code="reauth" if not produced
                               else "authentication")
        return None

    def _http_error(self, err: ProviderHTTPError, connection, slug: str, produced: bool) -> dict:
        label = connection.label
        if err.code:
            if err.code == "subscription_sharing_usage_limit_exceeded" or err.status == 429:
                return self._failed({"code": "subscription_sharing_usage_limit_exceeded"}, produced)
            mapped = self._mapped(err.code, err.param, produced)
            if mapped is not None:
                return mapped
            if err.code in {"subscription_sharing_usage_unavailable", "subscription_sharing_user_unavailable"}:
                return self._failed({"code": err.code}, produced)
        if err.status == 0:
            return self._error(f"Không kết nối được OpenAI ({label}). Kiểm tra mạng rồi thử lại.",
                               retryable=not produced, code="network")
        if err.status == 401:
            return self._error(f"OpenAI không nhận đăng nhập ChatGPT ({label}).",
                               code="reauth" if not produced else "authentication")
        if err.status == 403:
            return self._error(f"OpenAI chặn yêu cầu dùng gói ChatGPT ({label}), ví dụ do khu vực hay chính sách của "
                               "tài khoản.", code="permission")
        if err.status == 503:
            return self._error("Đường dùng gói ChatGPT tạm thời chưa sẵn sàng. Thử lại sau ít phút nhé.",
                               retryable=not produced, code="server")
        return super()._http_error(err, connection, slug, produced)

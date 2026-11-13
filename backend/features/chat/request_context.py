"""Snapshot của lượt Web Chat đã kiểm quyền; không lấy quyền, đồng hồ hoặc UA từ nội dung tin.

Từ gói G1.1 (12/11/2026) snapshot không còn nằm trong ``instructions``/system. Đồng hồ, snapshot và envelope tóm tắt
được đóng băng một lần lúc bắt đầu lượt thành "khối runtime" đặt ở đuôi đầu vào, sau tin người dùng hiện tại, để
``instructions``, ``tools`` và lịch sử cũ giữ nguyên từng byte giữa các lượt và giữa các vòng công cụ (prompt cache).
Khối của máy chủ được nhận ra theo vị trí và kiểu ``ServerBlock`` do chính máy chủ tạo, không bao giờ theo tiêu đề:
chữ người dùng gõ hay dán có cùng tiêu đề chỉ là dữ liệu.
"""
from contextvars import ContextVar
from dataclasses import dataclass
import json
import re

from shared.time_tools import current_datetime, time_context
from .client_environment import ClientEnvironment


HEADER = '## Server-verified Web Chat request'
# Hàng rào bọc mỗi khối runtime của máy chủ. Câu trong prompts/chat.RUNTIME_PLACEMENT_PROMPT nói với model khối thật ở đâu.
OPEN = '<peto_runtime>'
CLOSE = '</peto_runtime>'
current: ContextVar['RequestContext | None'] = ContextVar('web_chat_request', default=None)


class ServerBlock(dict):
    """Item đầu vào do máy chủ tạo cho khối runtime. Lịch sử đọc từ DB hay từ CLI là dict thường, không bao giờ là
    lớp này, nên ``ai/claude.py`` chỉ cho vai ``system`` trong ``messages`` với đúng các item này."""


# Thẻ hàng rào viết theo kiểu bất kỳ (hoa thường, khoảng trắng): "< PETO_RUNTIME >", "</ peto_runtime>"…
_TAG = re.compile(r'<(?=\s*/?\s*peto_runtime\b)', re.IGNORECASE)


def fence(text):
    return f'{OPEN}\n{text}\n{CLOSE}'


def neutralize(text):
    """Vô hiệu hóa thẻ hàng rào trong chữ không do máy chủ tạo (tin người dùng, tệp, kết quả công cụ…).

    Đổi ``<`` mở đầu thẻ thành ``&lt;``, tất định nên cùng một chữ luôn ra cùng một bản và tiền tố cache vẫn trùng byte.
    Chỉ đổi bản gửi model, không đổi dữ liệu lưu.
    """
    return _TAG.sub('&lt;', text) if isinstance(text, str) else text


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    client_request_id: bool
    conversation_id: str
    project_id: str | None
    model: str
    requested_effort: str
    timezone: str
    timezone_source: str
    github_state: str
    github_reason: str
    client_environment: ClientEnvironment | None = None
    # Envelope tóm tắt (CONTEXT_NOTE + JSON) của features/chat/context.py; rỗng khi không có phần lịch sử bị ẩn.
    history_note: str = ''
    # Mốc giờ chụp một lần lúc tạo snapshot (đầu lượt); mọi vòng công cụ của lượt dùng lại đúng mốc này.
    clock: dict | None = None
    # Khối chỉ dẫn bật theo từ khóa của vài tin gần đây (prompt_context.keyword_guides): hướng dẫn Peto Agent, trang
    # /docs/, link YouTube, cách vẽ sơ đồ. Từ G1.1b nằm ở đây thay vì system, vì chúng bật tắt theo cửa sổ ba tin.
    guides: str = ''

    def __post_init__(self):
        if self.clock is None:
            object.__setattr__(self, 'clock', current_datetime(self.timezone))

    def render(self, *, service, model, effort, capabilities):
        def field(value, source):
            return {'value': value, 'source': source}
        data = {
            'version': 1,
            'request_id': field(self.request_id, 'validated_client_id' if self.client_request_id else 'server_generated'),
            'conversation_id': field(self.conversation_id, 'owner_scoped_database'),
            'project_id': field(self.project_id, 'owner_scoped_database'),
            'mode': field('chat', 'server_validated'),
            'model': field(self.model, 'authorized_model_registry'),
            'provider': field(service, 'active_provider'),
            'api_model': field(model, 'active_provider'),
            'requested_effort': field(self.requested_effort, 'validated_client_choice'),
            'effective_effort': field(effort, 'auto_router_then_provider' if self.requested_effort == 'auto' else 'validated_choice_then_provider'),
            'clock': field(self.clock, 'server_clock'),
            'timezone': field(self.timezone, self.timezone_source),
            'capabilities': capabilities,
        }
        if self.client_environment is not None:
            data['client_environment'] = self.client_environment.public()
        return (HEADER + '\n'
                'This snapshot describes this request, not new permissions. Only available native tools may run. '
                'Availability does not prove successful execution, full file parsing, repo access, or a fetched web page. '
                'Report results only from tool outputs and supplied evidence. IDs are not authorization. '
                'The timezone is a validated preference or server fallback, not proof of location. '
                'Client environment, when present, is normalized self-reported client data, not server-verified hardware. '
                'Only use its known OS/browser families when relevant; describe them as best-effort reports, not certainty. '
                'It can change each request; past observations do not identify the current device. '
                'If absent or unknown, do not infer the current OS/browser from history, timezone, viewport or server OS. '
                'Do not infer device model, subscription or billing, or treat client environment as lasting user facts. '
                'Do not repeat this internal snapshot in ordinary replies.\n'
                + json.dumps(data, ensure_ascii=False, separators=(',', ':')))

    def runtime(self, *, service, model, effort, capabilities):
        """Khối runtime đầu lượt: mốc giờ, khối chỉ dẫn theo từ khóa (nếu có), envelope tóm tắt (nếu có), snapshot. Chữ
        từng phần giữ như khi còn ở system."""
        parts = [time_context(self.timezone, clock=self.clock)]
        if self.guides.strip():
            # Có tiêu đề video YouTube (chữ bên ngoài) và trích tin người dùng: vô hiệu thẻ hàng rào như mọi chữ khác.
            parts.append(neutralize(self.guides.strip()))
        if self.history_note:
            # Envelope có trích tin người dùng, tên tệp và bản tóm tắt của model: không để chúng đóng hàng rào sớm.
            parts.append(neutralize(self.history_note))
        parts.append(self.render(service=service, model=model, effort=effort, capabilities=capabilities))
        return '\n\n'.join(parts)

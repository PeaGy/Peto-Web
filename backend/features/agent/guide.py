"""Web knowledge of the CLI build actually served by this backend. Never read user project skills/config."""
import json
import re
import unicodedata
from functools import lru_cache

from features.agent import install as agent_install


def _version(text):
    return tuple(int(part) for part in text.split('.'))


@lru_cache(maxsize=4)
def _read_catalog(path, stamp):
    data = json.loads(path.read_text(encoding='utf-8'))
    if data['schema_version'] != 1 or not isinstance(data['commands'], list):
        raise ValueError('Unsupported command catalog')
    for item in data['commands']:
        if not all(isinstance(item[key], str) for key in ('name', 'description', 'usage', 'details', 'since')):
            raise ValueError('Invalid command documentation')
    return data['commands']


def catalog():
    version = agent_install.cli_version()
    path = agent_install.CLI_DIR / 'peto_agent' / 'command_catalog.json'
    try:
        entries = _read_catalog(path, path.stat().st_mtime_ns)
        return version, [item for item in entries if _version(item['since']) <= _version(version)]
    except (OSError, ValueError, KeyError, TypeError):
        return '', []


def _fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
                   if unicodedata.category(c) != 'Mn')


def build_agent_guide(*, install_command: str, daily_steps: int, question: str = '', english: bool = False) -> str:
    if english:
        return _english_guide(install_command, daily_steps, question)
    version, entries = catalog()
    install = install_command or 'irm https://<địa chỉ Peto>/install.ps1 | iex'
    blocks = [
        '## Peto Agent: hướng dẫn đúng bản máy chủ đang phục vụ',
        f'Bản CLI máy chủ đang cung cấp: {version or "chưa xác định"}. Đây không phải phiên bản đã cài trên máy người dùng. '
        'Dùng `peto --version` để họ kiểm tra; CLI tự nhắc khi máy chủ có bản mới. Không giới thiệu bản chưa triển khai.',
        'Web chỉ hướng dẫn, không chạy lệnh hoặc truy cập máy người dùng. Peto Agent là CLI chạy trong thư mục dự án. '
        'Chỉ nhắc khi liên quan. Không bịa lệnh hay tính năng không có trong tài liệu; hỏi phiên bản khi khác biệt. '
        'Lệnh / bên dưới dành cho Agent CLI, gõ ở khung chat web không thực thi chúng.',
        'Cần Windows, Python 3.12 trở lên và tài khoản Peto (Discord, Google hoặc GitHub). '
        'Chưa có Python: `winget install -e --id Python.Python.3.14`.',
        f'Cài/cập nhật: mở PowerShell, chạy `{install}`; không cần quyền quản trị. '
        'Nếu là địa chỉ mẫu thì thay bằng HTTPS của trang đang dùng, đừng tự đoán tên miền. '
        'Lỗi is not recognized: đóng hẳn terminal và mở lại để nhận PATH mới, không nhất thiết cài lại.',
        'Chạy `peto login`, mở liên kết, kiểm tra mã rồi cho phép trên web. Vào thư mục dự án, chạy `peto`; '
        'gõ `/` là hiện danh sách lệnh, Tab/Enter chọn; Ctrl+C dừng việc. Alt+V dán ảnh hoặc kéo tệp ảnh thả vào terminal. '
        '`peto status` xem trạng thái ngoài phiên; `peto logout` đăng xuất.',
        f'Hạn mức cấu hình: {daily_steps} bước mỗi ngày. Chi phí phụ thuộc model và effort; mức high/xhigh/max nhân đôi '
        'chi phí cơ sở. /usage, peto status hoặc Cài đặt → Peto Agent cho biết số bước và thiết bị. Không suy đoán quyền '
        'model hay số bước còn lại của người dùng từ hạn mức chung.',
        'Công cụ tệp của CLI giới hạn trong dự án, chặn bí mật/.env/.git; hỏi trước khi sửa tệp hay chạy lệnh trừ quyền '
        'người dùng đã cấp. Đây không phải sandbox cho lệnh shell hoặc MCP cục bộ: chúng chạy với quyền tài khoản máy. '
        'Nội dung được đọc và kết quả công cụ có thể gửi qua máy chủ tới dịch vụ AI; lịch sử lưu trên máy người dùng. '
        'Không yêu cầu người dùng dán API key/token vào chat.',
        'Gỡ: `peto logout`, xóa %LOCALAPPDATA%\\PetoAgent và %APPDATA%\\PetoAgent; có thể gỡ mục bin khỏi PATH.',
    ]
    if not entries:
        blocks.append('Không đọc được danh mục lệnh của bản đang phục vụ. Hướng dẫn người dùng dùng /help trong CLI; không đoán cú pháp.')
        return '\n'.join(blocks)
    blocks.append('Danh mục chung với /help của CLI:\n' + '\n'.join(
        f"- `{item['name']}`: {item['description']}" for item in entries))
    # Only trusted documentation is inserted, never the user's text. Include recent user turns for follow-ups.
    folded = _fold(question[-12000:])
    aliases = {'/skill': ('skill', 'skills', 'ky nang'), '/mcp': ('mcp',),
               '/effort': ('effort', 'suy nghi', 'reasoning'), '/model': ('model', 'mo hinh'),
               '/trinhduyet': ('trinh duyet', 'trinhduyet', 'browser'),
               '/permissions': ('permissions', 'quyen'), '/compact': ('compact', 'chat dai', 'hoi thoai dai')}
    for item in entries:
        terms = aliases.get(item['name'], (item['name'].lstrip('/'),))
        if any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', folded) for term in terms):
            since = f" (từ bản {item['since']})" if item['since'] != '0.0.0' else ''
            blocks.append(f"Chi tiết `{item['usage']}`{since}: {item['details']}")
    return '\n'.join(blocks)


def _english_guide(install_command: str, daily_steps: int, question: str) -> str:
    """Không chèn toàn bộ hướng dẫn CLI vào câu hỏi không liên quan; danh mục thật giữ nguyên ngôn ngữ."""
    folded = _fold(question[-12000:])
    if not re.search(r'(?<!\w)(agent|cli|peto|/skill|/mcp|/model|/effort|/permissions|/compact|/resume|/usage)(?!\w)', folded):
        return ''
    version, entries = catalog()
    install = install_command or 'irm https://<địa chỉ Peto>/install.ps1 | iex'
    blocks = [
        '## Peto Agent reference',
        f'The server serves CLI {version or "unknown"}, not necessarily the installed version. Check with `peto --version`.',
        'Web chat can explain Agent but cannot run commands or access the computer. Agent runs in the local project. '
        'CLI slash commands do not execute in web chat. Use only documented commands; link /docs/lenh-agent/ for details.',
        f'Windows and Python 3.12+ required; Discord/Google/GitHub sign-in. Install/update in PowerShell: `{install}` '
        '(no admin needed). Replace a placeholder with the current site HTTPS URL, never guess a domain. '
        'If Python is missing: `winget install -e --id Python.Python.3.14`. For “is not recognized”, reopen the terminal for PATH.',
        '`peto login`, verify the device code on web, then run `peto` in the project. `/` lists commands, Tab/Enter selects; '
        'Ctrl+C stops work. Alt+V pastes images or drag an image file into the terminal. CLI announces available updates.',
        f'Configured daily allowance: {daily_steps} steps. Model base costs differ; high/xhigh/max double base cost. '
        'Use /usage, `peto status` or Cài đặt → Peto Agent for actual quota/devices; do not infer account rights or remaining quota.',
        'File tools enforce project/secret boundaries; edits and commands follow user approvals. Shell and local MCP run '
        'as the OS user, not in a sandbox. Read content/results may reach the AI service; history is local. Never request API keys.',
        'Logout: `peto logout`. Uninstall: remove %LOCALAPPDATA%\\PetoAgent and %APPDATA%\\PetoAgent, optionally its bin PATH entry.',
    ]
    if not entries:
        blocks.append('Command catalog unavailable: use /help in the CLI; do not invent syntax.')
    else:
        blocks.append('Served CLI command catalog (reference data):\n' + '\n'.join(
            f"- `{item['name']}`: {item['description']}" for item in entries))
        aliases = {'/skill': ('skill', 'skills', 'ky nang'), '/mcp': ('mcp',),
                   '/effort': ('effort', 'suy nghi', 'reasoning'), '/model': ('model', 'mo hinh'),
                   '/trinhduyet': ('trinh duyet', 'trinhduyet', 'browser'),
                   '/permissions': ('permissions', 'quyen'), '/compact': ('compact', 'chat dai', 'hoi thoai dai')}
        for item in entries:
            if any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', folded)
                   for term in aliases.get(item['name'], (item['name'].lstrip('/'),))):
                blocks.append(f"`{item['usage']}` (since {item['since']}): {item['details']}")
    return '\n'.join(blocks)

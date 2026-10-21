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


def build_agent_guide(*, install_command: str, daily_steps: int, question: str = '') -> str:
    """Hướng dẫn Peto Agent cho chat web, chỉ khi vài tin gần đây nói tới Agent/CLI/Peto: không chèn cả hướng dẫn CLI
    vào câu hỏi không liên quan. Danh mục lệnh thật giữ nguyên ngôn ngữ của nó."""
    folded = _fold(question[-12000:])
    if not re.search(r'(?<!\w)(agent|cli|peto|/skill|/mcp|/models?|/connect|/effort|/permissions|/compact|/resume|/usage)'
                     r'(?!\w)', folded):
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
        'Own sources skip Peto steps and the Peto server: `peto connect openai` (own OpenAI API key, billed to the '
        'user\'s OpenAI account; CLI 0.31+) and `peto connect chatgpt` ("Continue with ChatGPT": sign in to use the '
        'ChatGPT plan; CLI 0.33+). In a session: /connect and /models; changing a model affects only that conversation. '
        'Keys and tokens stay encrypted on the user\'s Windows machine; never ask the user to paste a key or token into '
        'web chat.',
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
                   '/models': ('models', 'doi model', 'chon model'),
                   '/connect': ('connect', 'ket noi', 'chatgpt', 'khoa api', 'api key'),
                   '/browser': ('trinh duyet', 'trinhduyet', 'browser'), '/plan': ('plan', 'lap ke hoach'),
                   '/remember': ('remember', 'ghi nho', 'nho'),
                   '/permissions': ('permissions', 'quyen'), '/compact': ('compact', 'chat dai', 'hoi thoai dai')}
        for item in entries:
            if any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', folded)
                   for term in aliases.get(item['name'], (item['name'].lstrip('/'),))):
                blocks.append(f"`{item['usage']}` (since {item['since']}): {item['details']}")
    return '\n'.join(blocks)

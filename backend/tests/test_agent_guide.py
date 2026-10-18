import json

from features.agent import guide as agent_guide
from features.agent import install as agent_install


def guide(question=''):
    return agent_guide.build_agent_guide(install_command='', daily_steps=200, question=question)


def test_web_and_cli_share_all_command_summaries():
    data = json.loads((agent_install.CLI_DIR / 'peto_agent/command_catalog.json').read_text(encoding='utf-8'))
    text = guide('Peto Agent')
    for item in data['commands']:
        assert f"`{item['name']}`: {item['description']}" in text
        assert item['usage'] and item['details'] and item['since']
    assert agent_install.cli_version() in text
    assert 'not necessarily the installed version' in text


def test_the_guide_is_only_added_when_the_question_mentions_agent():
    # Câu hỏi không nói tới Agent/CLI/Peto thì không tốn token cho cả hướng dẫn CLI (cả Peto lẫn GPT, Claude).
    assert guide('giải thích asyncio') == ''
    assert guide('Peto Agent cài sao?').startswith('## Peto Agent reference')


def test_details_are_selected_without_copying_user_text_into_system_prompt():
    generic = guide('chào Peto')
    assert 'docs-mcp.json' not in generic and '24.000' not in generic
    mcp = guide('Peto Agent thêm MCP sao?\nTiếp theo làm gì? USER_INJECTION_MARKER')
    assert '/mcp add docs docs-mcp.json' in mcp and 'chưa hỗ trợ OAuth' in mcp
    assert 'USER_INJECTION_MARKER' not in mcp and '24.000' not in mcp
    assert '.agents/skills' in guide('Peto Agent nạp SKILLS được không')
    assert '/effort max' in guide('Peto Agent cho biết mức suy nghĩ')


def test_missing_catalog_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_install, 'CLI_DIR', tmp_path)
    text = guide('Peto Agent mcp')
    assert 'Command catalog unavailable' in text
    assert '/mcp add' not in text


def test_not_yet_shipped_commands_are_not_advertised(monkeypatch):
    monkeypatch.setattr(agent_install, 'cli_version', lambda: '0.12.1')
    text = guide('Peto Agent skills mcp')
    assert '`/skill`' not in text and '`/mcp`' not in text
    assert '0.12.1' in text

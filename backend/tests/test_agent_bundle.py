"""Bản chép lời nhắc, schema và cách ghép bước Agent mà CLI mang theo cho nguồn trực tiếp (agent-cli/peto_agent/bundle).

Sửa lời nhắc hay schema Agent ở backend mà quên chạy agent-cli/tools/make_bundle.py thì test này đỏ: CLI dùng khóa riêng
sẽ chạy bằng lời nhắc cũ.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

from features.agent import assembly
from shared.time_tools import TIME_HEADER_EN, agent_time_context

TOOL = Path(__file__).resolve().parents[2] / "agent-cli" / "tools" / "make_bundle.py"


def test_cli_bundle_matches_the_backend_sources():
    result = subprocess.run([sys.executable, str(TOOL), "--check"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_bundle_copies_only_pure_modules():
    spec = importlib.util.spec_from_file_location("make_bundle", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files = module.render()
    assert sorted(files) == ["__init__.py", "agent_prompts.py", "assembly.py", "core_prompt.py", "provider_prompts.py",
                             "tool_schemas.py"]
    for name, text in files.items():
        assert not module.BACKEND_IMPORT.search(text), name


def test_agent_clock_uses_the_shared_format():
    text = agent_time_context()
    assert text.startswith(TIME_HEADER_EN + "\n") and len(text.splitlines()) == 3
    assert assembly.time_text("2026-10-20", "09", "Asia/Ho_Chi_Minh", "UTC+07:00").splitlines()[1] == \
        "2026-10-20, between 09:00 and 09:59 (Asia/Ho_Chi_Minh, UTC+07:00)."


def test_limits_without_an_override_use_the_catalog():
    info = assembly.limits("openai", "gpt-6-luna", 16_000)
    assert info == {"identity": "openai/gpt-6-luna", "context": 1_050_000, "input": 1_050_000, "output": 16_000,
                    "known": True}
    assert assembly.limits("openai", "gpt-6-luna", 16_000, {}) == info

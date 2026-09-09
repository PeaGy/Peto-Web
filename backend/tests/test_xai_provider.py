"""Kiểm thử provider xAI mà không gọi mạng.

Không có test nào ở đây chạm tới xAI thật hoặc tới file token của bot Discord.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from ai.base import ProviderError
from ai.xai import XAIProvider
from config import XAI_TOKEN_PATH
from xai_auth import TokenBundle, XaiAuth, XaiAuthError, load_tokens, save_tokens


def test_provider_registry_exposes_xai():
    from ai import _PROVIDERS

    assert set(_PROVIDERS) == {"mock", "xai"}


async def test_missing_credentials_becomes_readable_error():
    provider = XAIProvider()
    with pytest.raises(ProviderError) as excinfo:
        await provider._prepare()
    assert "đăng nhập" in str(excinfo.value).casefold()


async def test_auth_mode_reports_none_without_token():
    assert XaiAuth().auth_mode() == "none"


async def test_token_roundtrip_and_expiry():
    bundle = TokenBundle(
        access_token="access-gia",
        refresh_token="refresh-gia",
        expires_at=time.time() + 3600,
    )
    save_tokens(bundle, XAI_TOKEN_PATH)
    try:
        loaded = load_tokens(XAI_TOKEN_PATH)
        assert loaded is not None
        assert loaded.access_token == "access-gia"
        assert not loaded.is_expired()

        auth = XaiAuth()
        assert auth.auth_mode() == "oauth"
        assert await auth.get_access_token() == "access-gia"
    finally:
        XAI_TOKEN_PATH.unlink(missing_ok=True)


async def test_expired_token_without_refresh_endpoint_raises():
    bundle = TokenBundle(
        access_token="het-han",
        refresh_token="refresh-gia",
        expires_at=time.time() - 10,
        token_endpoint="https://khong-phai-xai.example.com/token",
    )
    save_tokens(bundle, XAI_TOKEN_PATH)
    try:
        with pytest.raises(XaiAuthError):
            await XaiAuth().get_access_token()
    finally:
        XAI_TOKEN_PATH.unlink(missing_ok=True)


def test_token_endpoint_host_is_validated():
    from xai_auth import _validate_xai_url

    assert _validate_xai_url("https://auth.x.ai/oauth2/token")
    with pytest.raises(XaiAuthError):
        _validate_xai_url("http://auth.x.ai/oauth2/token")  # không HTTPS
    with pytest.raises(XaiAuthError):
        _validate_xai_url("https://ke-gia-mao.com/token")


def test_web_token_path_is_not_the_discord_bot_file():
    # Chốt chặn cho mục 8 của handoff: không dùng chung file token với bot cũ.
    assert XAI_TOKEN_PATH.name != ".xai_tokens.json"
    assert "Discord-Bot-Music" not in str(XAI_TOKEN_PATH)


def test_cli_prints_vietnamese_on_legacy_console(tmp_path):
    """Console Windows dùng cp1258; CLI phải tự ép UTF-8 chứ không được chết.

    Ép PYTHONIOENCODING về một bảng mã không có dấu tiếng Việt để tái hiện
    đúng tình huống thật, rồi kiểm tra CLI vẫn in được.
    """
    import subprocess
    import sys

    env = {
        **os.environ,
        "PYTHONIOENCODING": "cp1258",
        "PETO_XAI_TOKEN_PATH": str(tmp_path / "tokens.json"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "xai_auth", "status"],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert "UnicodeEncodeError" not in result.stderr
    assert "Chế độ" in result.stdout

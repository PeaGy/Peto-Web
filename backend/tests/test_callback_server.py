"""Kiểm thử server nhận callback OAuth của ``xai_auth``.

Bản đầu dùng ``handle_request`` (một-shot) nên trình duyệt xin ``/favicon.ico``
là tiêu mất lượt phục vụ duy nhất, callback thật bị từ chối và CLI treo cho tới
khi người dùng bấm Ctrl+C. Những test dưới đây chặn đúng lỗi đó.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from threading import Thread

import pytest

from xai_auth import (
    REDIRECT_HOST,
    _CallbackHandler,
    _CallbackServer,
    _parse_manual_redirect,
)


@pytest.fixture
def server():
    """Server trên cổng tự do, tránh đụng cổng thật khi chạy test."""
    instance = _CallbackServer((REDIRECT_HOST, 0), _CallbackHandler)
    Thread(target=instance.serve_forever, daemon=True).start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()


def _get(server: _CallbackServer, path: str) -> int:
    url = f"http://{REDIRECT_HOST}:{server.server_address[1]}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code


def test_callback_is_received(server):
    assert _get(server, "/callback?code=ABC&state=XYZ") == 200
    assert server.done.wait(timeout=5)
    assert server.result == {"code": "ABC", "state": "XYZ"}


def test_stray_request_does_not_kill_server(server):
    # Trình duyệt hay xin favicon trước — không được nuốt mất lượt callback.
    assert _get(server, "/favicon.ico") == 404
    assert not server.done.is_set()

    assert _get(server, "/callback?code=SAU_FAVICON&state=S") == 200
    assert server.done.wait(timeout=5)
    assert server.result["code"] == "SAU_FAVICON"


def test_error_callback_is_captured(server):
    assert _get(server, "/callback?error=access_denied&state=S") == 200
    assert server.done.wait(timeout=5)
    assert server.result["error"] == "access_denied"


def test_port_is_released_after_close():
    """Chạy login nhiều lần liên tiếp không được kẹt cổng."""
    first = _CallbackServer((REDIRECT_HOST, 0), _CallbackHandler)
    port = first.server_address[1]
    first.server_close()

    second = _CallbackServer((REDIRECT_HOST, port), _CallbackHandler)
    second.server_close()


@pytest.mark.parametrize(
    "pasted",
    [
        "http://127.0.0.1:56122/callback?code=abc&state=xyz",
        "?code=abc&state=xyz",
        "code=abc&state=xyz",
    ],
)
def test_manual_redirect_paste_accepts_common_shapes(pasted):
    assert _parse_manual_redirect(pasted) == {"code": "abc", "state": "xyz"}


def test_pasting_the_authorize_link_is_caught():
    """Lỗi rất dễ mắc: dán lại chính link đăng nhập thay vì URL trả về."""
    from xai_auth import XaiAuthError

    authorize = (
        "https://auth.x.ai/oauth2/authorize?response_type=code"
        "&client_id=b1a&code_challenge=xVro&state=CeH"
    )
    with pytest.raises(XaiAuthError) as excinfo:
        _parse_manual_redirect(authorize)
    assert "link đăng nhập" in str(excinfo.value)


def test_missing_code_is_reported_clearly():
    from xai_auth import XaiAuthError

    with pytest.raises(XaiAuthError) as excinfo:
        _parse_manual_redirect("http://127.0.0.1:56122/callback?state=CeH")
    assert "code" in str(excinfo.value)


def test_empty_paste_is_reported():
    from xai_auth import XaiAuthError

    with pytest.raises(XaiAuthError):
        _parse_manual_redirect("   ")


def test_user_cancellation_is_passed_through():
    # Có `error` thì cho qua, để tầng trên báo đúng lý do xAI trả về.
    result = _parse_manual_redirect(
        "http://127.0.0.1:56122/callback?error=access_denied&state=CeH"
    )
    assert result["error"] == "access_denied"


def test_pasting_the_consent_page_is_caught():
    """Trang consent vẫn ở trên x.ai và chưa có code — phải nói rõ."""
    from xai_auth import XaiAuthError

    consent = (
        "https://accounts.x.ai/oauth2/consent?response_type=code"
        "&client_id=b1a&state=kbfO&code_challenge=cZhV"
    )
    with pytest.raises(XaiAuthError) as excinfo:
        _parse_manual_redirect(consent)
    message = str(excinfo.value)
    assert "chưa bấm nút phê duyệt" in message
    assert "Authorize" in message

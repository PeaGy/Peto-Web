"""Kiểm tra chương trình Windows chuyển việc, không gọi mạng hay nạp model."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location('voice_relay', Path(__file__).resolve().parents[2] / 'voice-worker' / 'relay.py')
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


def test_relay_sends_audio_and_keeps_token_off_local_server(monkeypatch):
    monkeypatch.setenv('PETO_VOICE_SERVER_URL', 'https://peto.example')
    monkeypatch.setenv('PETO_VOICE_WORKER_TOKEN', 't' * 40)
    monkeypatch.setattr(relay.threading, 'Thread', Mock())
    calls = []
    class Reply:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return self.body
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            if len(calls) == 4:
                raise KeyboardInterrupt
            if request.full_url.endswith('/worker/next'):
                return Reply(json.dumps({'id': 'abc', 'text': 'Hello', 'voice': 'gentle-2'}).encode())
            if request.full_url.endswith('/speak'):
                assert not request.has_header('Authorization')
                assert request.full_url == 'http://127.0.0.1:7862/speak'
                return Reply(b'WAV-GIA')
            assert request.full_url == 'https://peto.example/api/voice/worker/result/abc'
            assert request.get_header('Authorization') == 'Bearer ' + 't' * 40
            assert request.data == b'WAV-GIA'
            return Reply(b'{}')
    monkeypatch.setattr(relay.urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(KeyboardInterrupt):
        relay.main()
    assert len(calls) == 4


def test_relay_requires_https(monkeypatch):
    monkeypatch.setenv('PETO_VOICE_SERVER_URL', 'http://peto.example')
    with pytest.raises(SystemExit, match='HTTPS'):
        relay.main()

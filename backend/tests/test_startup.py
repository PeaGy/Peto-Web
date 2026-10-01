"""Khởi động server thật với dữ liệu giả để kiểm tra bootstrap và thứ tự router."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx


def test_server_starts_and_serves_chat_docs_and_installer(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    # Server có database/upload/token riêng, không dùng dữ liệu của bài test khác.
    env = {
        **os.environ,
        'PYTHON_DOTENV_DISABLED': '1',
        'PETO_AI_PROVIDER': 'mock',
        'PETO_WEB_DB': str(tmp_path / 'startup.db'),
        'PETO_UPLOAD_DIR': str(tmp_path / 'uploads'),
        'PETO_XAI_TOKEN_PATH': str(tmp_path / 'tokens.json'),
        'PETO_COOLDOWN_SECONDS': '0',
    }
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    log_path = tmp_path / 'startup.log'
    with log_path.open('wb') as output:
        process = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=backend, env=env, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=20, trust_env=False) as client:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        health = client.get('/api/health')
                        if health.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert process.poll() is None, log_path.read_text(encoding='utf-8', errors='replace')
                    assert time.monotonic() < deadline, 'Server không khởi động trong thời gian cho phép.'
                    time.sleep(.1)
                assert health.json() == {'ok': True, 'provider': 'mock'}
                assert client.get('/api/docs').status_code == 200
                assert client.get('/install.ps1').status_code == 200
                assert client.post('/api/auth/guest').status_code == 200
                response = client.post('/api/chat', json={'message': 'Kiểm tra luồng chat'})
                assert response.status_code == 200
                assert response.headers['content-type'].startswith('text/event-stream')
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                assert events[-1]['type'] == 'done'
                conversation = next(event['conversation_id'] for event in events if event['type'] == 'meta')
                messages = client.get(f'/api/conversations/{conversation}/messages').json()['messages']
                assert [message['role'] for message in messages] == ['user', 'assistant']
                assert client.get('/api/route-khong-ton-tai').status_code == 404
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

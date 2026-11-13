"""Header bảo mật (G3.4): bắt buộc nosniff/referrer/chống nhúng khung, CSP chỉ báo cáo có mã băm script nhúng, và
endpoint báo cáo không ghi nội dung."""
import base64
import hashlib
import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from core import security_headers, static_files

THEME = "\n      (function () { document.documentElement.dataset.theme = 'dark'; })();\n    "
INDEX = f"<!doctype html><html><head><script>{THEME}</script><script type=\"module\" src=\"/assets/a.js\"></script>" \
        "</head><body><div id=\"root\"></div></body></html>"


def expected_hash(body):
    return "'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"


@pytest.fixture
def site(tmp_path, monkeypatch):
    async def identity():
        return {'name': 'Peto', 'avatar_url': None}
    monkeypatch.setattr(static_files, 'get_app_identity', identity)
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text(INDEX, encoding='utf-8')
    (tmp_path / '404.html').write_text('<h1>Không có</h1>', encoding='utf-8')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(security_headers.SecurityHeaders, static_dir=tmp_path)
    app.include_router(security_headers.router)

    @app.get('/api/stream')
    async def stream():
        async def body():
            yield 'data: 1\n\n'
            yield 'data: 2\n\n'
        return StreamingResponse(body(), media_type='text/event-stream')

    assert static_files.mount(app, tmp_path)
    security_headers._window.update(start=0.0, count=0, dropped=0)
    return app, tmp_path


@pytest.fixture
async def web(site):
    async with AsyncClient(transport=ASGITransport(app=site[0]), base_url='http://test') as client:
        yield client


@pytest.mark.parametrize('path', ['/', '/chat/abc', '/docs/', '/api/stream', '/khong-co'])
async def test_every_response_gets_the_enforced_headers_and_report_only_csp(web, path):
    response = await web.get(path)
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['referrer-policy'] == 'strict-origin-when-cross-origin'
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers['content-security-policy'] == "frame-ancestors 'none'"
    report_only = response.headers['content-security-policy-report-only']
    assert expected_hash(THEME) in report_only
    assert "'unsafe-inline'" not in report_only.split('script-src', 1)[1].split(';', 1)[0]
    assert 'frame-src https://www.youtube.com' in report_only and 'report-uri /api/csp-report' in report_only
    # Cloudflare Web Analytics tự chèn script này khi trang đi qua proxy (báo cáo thật 13/11/2026).
    assert 'https://static.cloudflareinsights.com' in report_only.split('script-src', 1)[1].split(';', 1)[0]


async def test_streams_still_arrive_in_pieces(web):
    async with web.stream('GET', '/api/stream') as response:
        chunks = [chunk async for chunk in response.aiter_text()]
    assert ''.join(chunks) == 'data: 1\n\ndata: 2\n\n'
    assert response.headers['content-type'].startswith('text/event-stream')


async def test_hashes_follow_a_new_build(web, site):
    _, folder = site
    new = "document.documentElement.dataset.motion = 'full';"
    (folder / 'index.html').write_text(f'<html><head><script>{new}</script></head></html>', encoding='utf-8')
    header = (await web.get('/')).headers['content-security-policy-report-only']
    assert expected_hash(new) in header and expected_hash(THEME) not in header


async def test_report_logs_only_directive_origin_and_page_section(web, caplog):
    caplog.set_level(logging.WARNING, logger='peto_web.csp')
    report = {'csp-report': {'effective-directive': 'script-src-elem',
                             'blocked-uri': 'https://evil.example/x.js?token=SECRET',
                             'document-uri': 'https://peto.example/chat/0123abcd?q=private',
                             'disposition': 'report', 'script-sample': 'alert(SECRET)'}}
    response = await web.post('/api/csp-report', json=report, headers={'content-type': 'application/csp-report'})
    assert response.status_code == 204
    line = caplog.records[-1].getMessage()
    assert line == 'csp_violation directive=script-src-elem blocked=https://evil.example page=/chat mode=report'
    modern = [{'type': 'csp-violation', 'body': {'effectiveDirective': 'img-src', 'blockedURL': 'data',
                                                  'documentURL': 'https://peto.example/docs/abc', 'disposition': 'report'}}]
    assert (await web.post('/api/csp-report', json=modern)).status_code == 204
    assert caplog.records[-1].getMessage() == 'csp_violation directive=img-src blocked=data page=/docs mode=report'
    assert 'SECRET' not in caplog.text and '0123abcd' not in caplog.text and 'private' not in caplog.text


async def test_report_endpoint_rejects_large_or_broken_bodies_and_caps_logs(web, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger='peto_web.csp')
    assert (await web.post('/api/csp-report', content=b'x' * 20_000)).status_code == 413
    assert (await web.post('/api/csp-report', content=b'{not json')).status_code == 400
    monkeypatch.setattr(security_headers, 'MAX_LOGS_PER_MINUTE', 3)
    report = {'csp-report': {'effective-directive': 'img-src', 'blocked-uri': 'https://a.example/x.png',
                             'document-uri': 'https://peto.example/'}}
    for _ in range(5):
        assert (await web.post('/api/csp-report', json=report)).status_code == 204
    assert sum('csp_violation directive' in record.getMessage() for record in caplog.records) == 3


async def test_the_real_app_sends_the_headers_and_accepts_reports(anon_client):
    response = await anon_client.post('/api/csp-report', json={'csp-report': {'effective-directive': 'img-src'}})
    assert response.status_code == 204
    assert response.headers['x-content-type-options'] == 'nosniff'
    health = await anon_client.get('/api/health')
    assert health.headers['content-security-policy'] == "frame-ancestors 'none'"
    assert 'report-uri /api/csp-report' in health.headers['content-security-policy-report-only']

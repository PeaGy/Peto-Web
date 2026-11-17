"""Một tên miền chính (17/11/2026): trang mở bằng tên miền cũ chuyển sang tên miền mới, API thì không."""
import httpx
import pytest

from core.canonical_host import CanonicalHost, parse_origin

HTML = {'accept': 'text/html,application/xhtml+xml,*/*;q=0.8'}


async def inner(scope, receive, send):
    await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'text/plain')]})
    await send({'type': 'http.response.body', 'body': b'ok'})


def client(origin='https://peto.peagy.com', host='peto.pearto.shop'):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=CanonicalHost(inner, origin)), base_url=f'https://{host}')


async def test_a_page_on_the_old_domain_moves_to_the_main_one_with_its_path_and_query():
    async with client() as http:
        response = await http.get('/chat/abc?source=bookmark', headers=HTML)
    assert response.status_code == 302
    assert response.headers['location'] == 'https://peto.peagy.com/chat/abc?source=bookmark'
    assert response.headers['cache-control'] == 'no-store'
    async with client() as http:
        assert (await http.head('/docs/', headers=HTML)).headers['location'] == 'https://peto.peagy.com/docs/'


@pytest.mark.parametrize('path, headers, method', [
    ('/api/auth/me', HTML, 'GET'),                 # API: Peto Agent, Harness, máy giọng nói vẫn dùng tên miền cũ
    ('/api', HTML, 'GET'),
    ('/install.ps1', {'accept': '*/*'}, 'GET'),    # irm … | iex không xin HTML
    ('/chat/abc', HTML, 'POST'),
])
async def test_api_scripts_and_other_methods_stay_on_any_domain(path, headers, method):
    async with client() as http:
        response = await http.request(method, path, headers=headers)
    assert response.status_code == 200 and response.text == 'ok'


@pytest.mark.parametrize('host', ['peto.peagy.com', 'PETO.PEAGY.COM', '127.0.0.1:8001', 'localhost:5173', '[::1]:8001'])
async def test_the_main_domain_and_local_checks_are_served_directly(host):
    async with client(host=host) as http:
        response = await http.get('/', headers=HTML)
    assert response.status_code == 200


@pytest.mark.parametrize('origin', ['', 'peto.peagy.com', 'https://peto.peagy.com/chat', 'ftp://x', 'https://'])
async def test_an_empty_or_broken_setting_redirects_nothing(origin):
    assert parse_origin(origin) is None
    async with client(origin=origin) as http:
        assert (await http.get('/', headers=HTML)).status_code == 200


def test_the_app_registers_the_redirect_inside_the_security_headers():
    from core import security_headers
    from main import app
    kinds = [m.cls for m in app.user_middleware]
    # user_middleware: phần tử đầu là lớp ngoài cùng. Header bảo mật bọc ngoài nên cả phản hồi 302 cũng có header.
    assert kinds.index(security_headers.SecurityHeaders) < kinds.index(CanonicalHost)

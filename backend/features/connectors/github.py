"""GitHub App: cấp quyền theo repo, mã hóa khóa và chỉ đọc API GitHub."""
import asyncio
import base64
import hashlib
import json
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from core.config import FRONTEND_URL
from storage import connectors as store

CLIENT_ID = os.getenv('PETO_GITHUB_CLIENT_ID', '').strip()
CLIENT_SECRET = os.getenv('PETO_GITHUB_CLIENT_SECRET', '').strip()
REDIRECT_URI = os.getenv('PETO_GITHUB_REDIRECT_URI', '').strip()
APP_SLUG = os.getenv('PETO_GITHUB_APP_SLUG', '').strip()
ENCRYPTION_SECRET = os.getenv('PETO_CONNECTOR_SECRET', '').strip()
API = 'https://api.github.com'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_locks = [asyncio.Lock() for _ in range(32)]


class GitHubError(Exception):
    """Lỗi kết nối đã được diễn đạt cho người dùng, không chứa khóa hoặc phản hồi thô."""

    def __init__(self, message, *, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def lock(owner):
    return _locks[int(hashlib.sha256(owner.encode()).hexdigest()[:8], 16) % len(_locks)]


def configured():
    callback = urlsplit(REDIRECT_URI)
    return bool(CLIENT_ID and CLIENT_SECRET and re.fullmatch(r'[a-z0-9-]+', APP_SLUG)
                and len(ENCRYPTION_SECRET) >= 32 and callback.netloc
                and (callback.scheme == 'https' or (callback.scheme == 'http' and callback.hostname in {'localhost', '127.0.0.1'})))


def cipher():
    if len(ENCRYPTION_SECRET) < 32:
        raise GitHubError('Máy chủ chưa cấu hình khóa bảo vệ kết nối.')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(ENCRYPTION_SECRET.encode()).digest()))


def encrypt(value):
    return cipher().encrypt(json.dumps(value).encode()).decode()


def decrypt(value):
    try:
        return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken, ValueError, TypeError):
        raise GitHubError('Kết nối không còn đọc được. Hãy kết nối lại GitHub.') from None


def token_data(data):
    token = data.get('access_token')
    if not isinstance(token, str) or not token or len(token) > 4096:
        raise GitHubError('GitHub chưa cấp quyền truy cập. Hãy kết nối lại.')
    refresh = data.get('refresh_token', '')
    if not isinstance(refresh, str) or len(refresh) > 4096:
        raise GitHubError('GitHub trả về thông tin cấp quyền không hợp lệ.')
    return {'access_token': token, 'refresh_token': refresh,
            'expires_at': time.time() + int(data['expires_in']) if data.get('expires_in') else None,
            'refresh_expires_at': time.time() + int(data['refresh_token_expires_in']) if data.get('refresh_token_expires_in') else None}


async def read_response(response, limit=MAX_RESPONSE_BYTES):
    data = bytearray()
    async for chunk in response.aiter_bytes():
        remaining = limit - len(data)
        data.extend(chunk[:remaining])
        if len(chunk) > remaining:
            raise GitHubError('Dữ liệu GitHub quá lớn cho một lần đọc. Hãy chọn tệp hoặc tác vụ nhỏ hơn.')
    return bytes(data)


async def exchange(fields):
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            async with client.stream('POST', TOKEN_URL, data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, **fields},
                                     headers={'Accept': 'application/json'}) as response:
                if response.status_code != 200:
                    raise GitHubError('Chưa đổi được quyền truy cập GitHub. Hãy thử kết nối lại.')
                return token_data(json.loads(await read_response(response, 32_000)))
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        raise GitHubError('Chưa kết nối được với GitHub. Hãy thử lại.') from None


def check_status(status, *, headers=None, message='', path=''):
    headers = headers or {}
    if status == 401:
        raise GitHubError('GitHub đã hết hạn hoặc bị thu hồi quyền. Mở Cài đặt → Kết nối để kết nối lại.', status_code=status)
    if status == 429 or (status == 403 and (headers.get('x-ratelimit-remaining') == '0'
                                          or headers.get('retry-after') or 'rate limit' in message.lower())):
        raise GitHubError('GitHub đang giới hạn lượt truy cập. Hãy chờ trước khi tra cứu tiếp; đây không phải thông báo thiếu quyền repo.', status_code=status)
    if status == 403:
        if message in {'Resource not accessible by integration', 'Resource not accessible by personal access token'}:
            permission = 'Actions: Read-only' if '/actions/' in path else 'Contents: Read-only' if re.search(r'/contents(?:/|$)', path) else 'quyền đọc cho tác vụ này'
            raise GitHubError(f'GitHub từ chối quyền đọc. Kiểm tra {permission}, repo đã chọn và việc chấp thuận quyền mới của GitHub App.', status_code=status)
        raise GitHubError('GitHub từ chối yêu cầu truy cập. Chưa xác định được là quyền repo hay chính sách tài khoản/tổ chức.', status_code=status)
    if status == 404:
        raise GitHubError('GitHub không tìm thấy dữ liệu được yêu cầu (404). Có thể sai repo, đường dẫn hoặc nhánh; mã này chưa xác nhận thiếu quyền.', status_code=status)
    if status >= 400 or status < 200:
        raise GitHubError('GitHub chưa trả được dữ liệu. Hãy thử lại sau.', status_code=status)


async def api_get(token, path, params=None, *, log=False):
    """Đích API cố định; không gửi Authorization sang địa chỉ tải log."""
    if not path.startswith('/') or path.startswith('//'):
        raise GitHubError('Đường dẫn GitHub không hợp lệ.')
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28'}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            async with client.stream('GET', API + path, params=params, headers=headers) as response:
                if log and response.status_code == 302:
                    location = response.headers.get('location', '')
                    url = urlsplit(location)
                    host = url.hostname or ''
                    if (url.scheme != 'https' or url.username or url.password or url.port not in {None, 443}
                            or not (host.endswith('.blob.core.windows.net') or host.endswith('.actions.githubusercontent.com'))):
                        raise GitHubError('GitHub trả về địa chỉ tải log không được hỗ trợ.')
                    # Không dùng lại headers có khóa GitHub và không đi theo chuyển hướng tiếp theo.
                    async with client.stream('GET', location) as downloaded:
                        check_status(downloaded.status_code, headers=downloaded.headers)
                        if downloaded.status_code != 200:
                            raise GitHubError('Chưa tải được log GitHub.')
                        return (await read_response(downloaded)).decode('utf-8', errors='replace')
                message = ''
                if response.status_code == 403:
                    # Chỉ dùng loại lỗi đã biết để phân biệt quyền và hạn mức; không đưa phản hồi thô ra chat.
                    try:
                        error_data = json.loads(await read_response(response, 32_000))
                        message = error_data.get('message', '') if isinstance(error_data, dict) else ''
                        if not isinstance(message, str):
                            message = ''
                    except (ValueError, GitHubError):
                        pass
                check_status(response.status_code, headers=response.headers, message=message, path=path)
                if response.status_code != 200:
                    raise GitHubError('GitHub trả về chuyển hướng ngoài luồng được hỗ trợ.')
                data = await read_response(response)
                return data.decode('utf-8', errors='replace') if log else json.loads(data)
    except (httpx.HTTPError, ValueError, TypeError):
        raise GitHubError('Chưa đọc được dữ liệu GitHub. Hãy thử lại.') from None


async def access_token(owner):
    if not configured():
        raise GitHubError('Máy chủ chưa cấu hình kết nối GitHub.')
    async with lock(owner):
        account = await store.get_github(owner)
        if not account:
            raise GitHubError('Bạn chưa kết nối GitHub. Mở Cài đặt → Kết nối để bắt đầu.')
        data = decrypt(account['credentials'])
        if data.get('expires_at') and data['expires_at'] <= time.time() + 60:
            if not data.get('refresh_token') or (data.get('refresh_expires_at') and data['refresh_expires_at'] <= time.time()):
                raise GitHubError('Quyền GitHub đã hết hạn. Hãy kết nối lại.')
            data = await exchange({'grant_type': 'refresh_token', 'refresh_token': data['refresh_token']})
            if not await store.refresh_github(owner, account['revision'], encrypt(data)):
                raise GitHubError('Kết nối GitHub đã thay đổi. Hãy thử lại.')
        return data['access_token']


async def status(owner):
    account = await store.get_github(owner)
    state = 'not_connected'
    if account:
        state = 'connected'
        try:
            data = decrypt(account['credentials'])
            if data.get('expires_at') and data['expires_at'] <= time.time() and (
                    not data.get('refresh_token') or (data.get('refresh_expires_at') and data['refresh_expires_at'] <= time.time())):
                state = 'reconnect'
        except GitHubError:
            state = 'reconnect'
    return {'id': 'github', 'name': 'GitHub', 'configured': configured(), 'status': state,
            'login': account['login'] if account else None,
            'updated_at': account['updated_at'] if account else None,
            'install_url': f'https://github.com/apps/{APP_SLUG}/installations/new' if configured() else None}

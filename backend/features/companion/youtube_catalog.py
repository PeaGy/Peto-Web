"""YouTube Data API cho Player: tìm khi gửi form, nhập playlist có giới hạn; không scrape."""
from __future__ import annotations

import asyncio
import html
import json
import re
import time
from collections.abc import Awaitable, Callable

import httpx
from fastapi import HTTPException

from core import config
from core.rate_limit import Admission, AdmissionDenied
from shared.youtube import CONTROL, VIDEO_ID

API_ROOT = 'https://www.googleapis.com/youtube/v3/'
PLAYLIST_ID = re.compile(r'[A-Za-z0-9_-]{10,150}\Z')
PAGE_TOKEN = re.compile(r'[A-Za-z0-9_+=/\-]{0,512}\Z')
MAX_PLAYLIST_ITEMS = 200
MAX_RESPONSE_BYTES = 512_000
CACHE_SECONDS = 300
MAX_CACHE = 128
_cache: dict[tuple, tuple[float, dict]] = {}
# Tách khỏi lượt chat: không giữ slot AI hoặc ngắt micro/giọng đọc.
admission = Admission(max_concurrent=3, max_queue=4, queue_timeout=10, cooldown=1.5)


def _clean(value: object, limit: int) -> str:
    return ' '.join(CONTROL.sub(' ', html.unescape(value)).split())[:limit] if isinstance(value, str) else ''


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=8, follow_redirects=False)


async def _request(client: httpx.AsyncClient, resource: str, **params: object) -> dict:
    # resource chỉ được chọn trong mã bên dưới; không nhận URL hoặc resource của người dùng.
    try:
        async with client.stream('GET', API_ROOT + resource, params=params, headers={'X-Goog-Api-Key': config.YOUTUBE_API_KEY}) as response:
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise HTTPException(502, 'Phản hồi YouTube quá lớn. Hãy thử lại sau.')
            try:
                data = json.loads(content)
            except (ValueError, UnicodeError):
                raise HTTPException(502, 'YouTube chưa trả về dữ liệu hợp lệ.') from None
            if not isinstance(data, dict):
                raise HTTPException(502, 'YouTube chưa trả về dữ liệu hợp lệ.')
            if response.status_code != 200:
                errors = data.get('error', {}).get('errors', []) if isinstance(data.get('error'), dict) else []
                reasons = {item['reason'] for item in errors if isinstance(item, dict) and isinstance(item.get('reason'), str)} if isinstance(errors, list) else set()
                if reasons & {'quotaExceeded', 'dailyLimitExceeded', 'rateLimitExceeded'} or response.status_code == 429:
                    raise HTTPException(503, 'YouTube đã hết hạn mức tạm thời. Bạn vẫn có thể mở bằng link video.')
                if reasons & {'keyInvalid', 'accessNotConfigured', 'ipRefererBlocked'}:
                    raise HTTPException(503, 'Tìm kiếm và playlist chưa sẵn sàng. Bạn vẫn có thể mở bằng link video.')
                if response.status_code == 404 or reasons & {'playlistNotFound', 'playlistItemsNotAccessible', 'playlistOperationUnsupported'}:
                    raise HTTPException(404, 'Không đọc được playlist này. Hãy dùng playlist công khai có thể chia sẻ.')
                if response.status_code == 403:
                    raise HTTPException(503, 'YouTube chưa cho phép truy cập danh sách này. Bạn vẫn có thể mở bằng link video.')
                if response.status_code == 400:
                    raise HTTPException(400, 'YouTube chưa nhận được yêu cầu này. Hãy kiểm tra link hoặc tìm lại.')
                raise HTTPException(502, 'Chưa kết nối được YouTube. Bạn thử lại sau nhé.')
            return data
    except httpx.TimeoutException:
        raise HTTPException(504, 'YouTube phản hồi quá lâu. Bạn thử lại nhé.') from None
    except httpx.HTTPError:
        # Không đưa lỗi upstream hoặc thông tin đăng nhập vào thông báo người dùng.
        raise HTTPException(502, 'Chưa kết nối được YouTube. Bạn thử lại nhé.') from None


async def _cached(key: tuple, owner: str, load: Callable[[], Awaitable[dict]]) -> dict:
    if not config.YOUTUBE_API_KEY:
        raise HTTPException(503, 'Tìm kiếm và playlist chưa được bật. Bạn vẫn có thể mở bằng link video.')
    cached = _cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        async with admission.slot(owner):
            # Các trang/playlist khác nhau vẫn bị giới hạn riêng theo tài khoản và số yêu cầu đồng thời.
            result = await asyncio.wait_for(load(), timeout=30)
    except AdmissionDenied as error:
        raise HTTPException(429, 'Bạn đợi một chút rồi thử lại nhé.', headers={'Retry-After': str(max(1, int(error.retry_after + 1)))}) from None
    except TimeoutError:
        raise HTTPException(504, 'YouTube phản hồi quá lâu. Bạn thử lại nhé.') from None
    if len(_cache) >= MAX_CACHE:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (time.monotonic() + CACHE_SECONDS, result)
    return result


def _items(data: dict) -> list[dict]:
    items = data.get('items')
    if not isinstance(items, list) or len(items) > 50:
        raise HTTPException(502, 'YouTube chưa trả về danh sách hợp lệ.')
    return [item for item in items if isinstance(item, dict)]


def _next_page(data: dict) -> str:
    token = data.get('nextPageToken', '')
    if not isinstance(token, str) or not PAGE_TOKEN.fullmatch(token):
        raise HTTPException(502, 'YouTube chưa trả về trang tiếp theo hợp lệ.')
    return token


def _duration(value: object) -> int:
    match = re.fullmatch(r'P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', value) if isinstance(value, str) and len(value) < 64 else None
    return sum(int(part or 0) * scale for part, scale in zip(match.groups(), (86400, 3600, 60, 1))) if match else 0


async def _videos(client: httpx.AsyncClient, ids: list[str]) -> dict[str, dict]:
    unique = list(dict.fromkeys(ids))
    found = {}
    for start in range(0, len(unique), 50):
        data = await _request(client, 'videos', part='snippet,contentDetails,status', id=','.join(unique[start:start + 50]),
                              fields='items(id,snippet(title,channelTitle),contentDetails(duration),status(embeddable,privacyStatus,uploadStatus))')
        for item in _items(data):
            status = item.get('status', {})
            snippet = item.get('snippet', {})
            video_id = item.get('id', '')
            if (not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id) or not isinstance(status, dict)
                    or not status.get('embeddable') or status.get('privacyStatus') == 'private'
                    or status.get('uploadStatus') in {'deleted', 'failed', 'rejected'} or not isinstance(snippet, dict)):
                continue
            details = item.get('contentDetails', {})
            found[video_id] = {'video_id': video_id, 'title': _clean(snippet.get('title'), 200),
                               'artist': _clean(snippet.get('channelTitle'), 100),
                               'duration': _duration(details.get('duration')) if isinstance(details, dict) else 0}
    return found


async def search(owner: str, query: str, page_token: str = '') -> dict:
    query = _clean(query, 200)
    if not query:
        raise HTTPException(400, 'Nhập tên video để tìm.')

    async def load() -> dict:
        async with _client() as client:
            data = await _request(client, 'search', part='snippet', type='video', q=query, maxResults=20,
                                  videoEmbeddable='true', videoSyndicated='true', pageToken=page_token,
                                  fields='nextPageToken,items(id/videoId)')
            ids = [item['id']['videoId'] for item in _items(data) if isinstance(item.get('id'), dict)
                   and isinstance(item['id'].get('videoId'), str) and VIDEO_ID.fullmatch(item['id']['videoId'])]
            found = await _videos(client, ids)
            return {'tracks': [found[video_id] for video_id in dict.fromkeys(ids) if video_id in found],
                    'next_page_token': _next_page(data)}
    return await _cached(('search', query.casefold(), page_token), owner, load)


async def playlist(owner: str, playlist_id: str, limit: int = MAX_PLAYLIST_ITEMS) -> dict:
    if not PLAYLIST_ID.fullmatch(playlist_id):
        raise HTTPException(400, 'Mã playlist YouTube chưa hợp lệ.')

    async def load() -> dict:
        async with _client() as client:
            ids: list[str] = []
            scanned = 0
            token = ''
            seen_tokens = set()
            # Tối đa 4 trang và 4 batch metadata. Playlist lớn không chiếm mạng/quota vô hạn.
            for _ in range(4):
                data = await _request(client, 'playlistItems', part='snippet', playlistId=playlist_id, maxResults=50,
                                      pageToken=token, fields='nextPageToken,items(snippet/resourceId/videoId)')
                items = _items(data)
                scanned += len(items)
                for item in items:
                    snippet = item.get('snippet', {})
                    resource = snippet.get('resourceId', {}) if isinstance(snippet, dict) else {}
                    video_id = resource.get('videoId') if isinstance(resource, dict) else None
                    if isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id):
                        ids.append(video_id)
                token = _next_page(data)
                if not token:
                    break
                if token in seen_tokens:
                    raise HTTPException(502, 'YouTube trả về trang playlist bị lặp. Chưa thêm bài vào hàng đợi.')
                seen_tokens.add(token)
                if len(ids) >= limit:
                    break
            found = await _videos(client, ids)
            tracks = [found[video_id] for video_id in ids if video_id in found]
            return {'tracks': tracks[:limit], 'skipped': scanned - len(tracks), 'truncated': bool(token) or len(tracks) > limit}
    return await _cached(('playlist', playlist_id, limit), owner, load)

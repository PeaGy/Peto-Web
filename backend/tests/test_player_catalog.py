from __future__ import annotations

import httpx
import pytest

from core import config
from core.rate_limit import Admission
from features.companion import youtube_catalog as catalog

BASE = '/api/companion/player'
PLAYLIST = 'PLabcdefghijk12345'
FIRST, SECOND = 'Soy4jGPHr3g', 'e1xCOsgWG0M'


def video(video_id, *, embeddable=True, private=False):
    return {'id': video_id, 'snippet': {'title': 'Tetris &amp; more', 'channelTitle': 'Kasane Teto SV'},
            'status': {'embeddable': embeddable, 'privacyStatus': 'private' if private else 'public', 'uploadStatus': 'processed'},
            'contentDetails': {'duration': 'PT1H2M3S'}}


@pytest.fixture(autouse=True)
def clean_catalog(monkeypatch):
    catalog._cache.clear()
    monkeypatch.setattr(config, 'YOUTUBE_API_KEY', 'test-key-never-return')
    monkeypatch.setattr(catalog, 'admission', Admission(max_concurrent=3, cooldown=0))
    yield
    catalog._cache.clear()


def network(monkeypatch, handler):
    monkeypatch.setattr(catalog, '_client', lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_catalog_needs_auth_and_key_but_video_links_still_work(anon_client, client, monkeypatch):
    assert (await anon_client.get(BASE + '/search?q=Tetris')).status_code == 401
    assert (await anon_client.get(f'{BASE}/playlists/{PLAYLIST}')).status_code == 401
    monkeypatch.setattr(config, 'YOUTUBE_API_KEY', '')
    response = await client.get(BASE + '/search?q=Tetris')
    assert response.status_code == 503 and 'link video' in response.json()['detail']
    assert (await client.get(f'{BASE}/playlists/{PLAYLIST}')).status_code == 503
    async def missing(_):
        return None
    monkeypatch.setattr('shared.youtube.lookup', missing)
    assert (await client.get(f'{BASE}/videos/{FIRST}')).status_code == 200


async def test_inputs_rejected_before_any_network(client, monkeypatch):
    network(monkeypatch, lambda _: pytest.fail('invalid input must not call YouTube'))
    for path in ['/search?q=', '/search?q=' + 'a' * 201, '/search?q=x&page_token=%0a',
                 '/playlists/short', f'/playlists/{PLAYLIST}?limit=201', f'/playlists/{PLAYLIST}?limit=0']:
        assert (await client.get(BASE + path)).status_code in {400, 422}
    assert (await client.get(BASE + '/search?q=%20%20%20')).status_code == 400


async def test_search_uses_official_video_filter_batches_details_and_caches(client, monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.host == 'www.googleapis.com'
        assert request.headers['X-Goog-Api-Key'] == 'test-key-never-return'
        assert 'key' not in request.url.params and 'test-key-never-return' not in str(request.url)
        if request.url.path.endswith('/search'):
            assert request.url.params['type'] == 'video'
            assert request.url.params['videoEmbeddable'] == 'true'
            return httpx.Response(200, json={'items': [{'id': {'videoId': id}} for id in [FIRST, SECOND]], 'nextPageToken': 'PAGE2'})
        return httpx.Response(200, json={'items': [video(SECOND, embeddable=False), video(FIRST)]})
    network(monkeypatch, handler)
    response = await client.get(BASE + '/search?q=Tetris')
    assert response.status_code == 200
    assert response.json() == {'tracks': [{'video_id': FIRST, 'title': 'Tetris & more', 'artist': 'Kasane Teto SV', 'duration': 3723}], 'next_page_token': 'PAGE2'}
    assert 'test-key-never-return' not in response.text
    await client.get(BASE + '/search?q=tetris')
    assert len(requests) == 2
    await client.get(BASE + '/search?q=Tetris&page_token=PAGE2')
    assert len(requests) == 4 and requests[2].url.params['pageToken'] == 'PAGE2'


async def test_playlist_preserves_order_duplicates_and_skips_private_deleted_disabled(client, monkeypatch):
    calls = []
    ids = [SECOND, FIRST, SECOND, 'aaaaaaaaaaa', 'bbbbbbbbbbb', 'deleted____']
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/playlistItems'):
            token = request.url.params.get('pageToken')
            selected = ids[:2] if not token else ids[2:]
            return httpx.Response(200, json={'items': [{'snippet': {'resourceId': {'videoId': id}}} for id in selected], **({'nextPageToken': 'PAGE2'} if not token else {})})
        return httpx.Response(200, json={'items': [video(FIRST), video(SECOND), video('aaaaaaaaaaa', private=True), video('bbbbbbbbbbb', embeddable=False)]})
    network(monkeypatch, handler)
    data = (await client.get(f'{BASE}/playlists/{PLAYLIST}')).json()
    assert [item['video_id'] for item in data['tracks']] == [SECOND, FIRST, SECOND]
    assert data['skipped'] == 3 and not data['truncated']
    assert len(calls) == 3 and len(calls[-1].url.params['id'].split(',')) == 5


async def test_playlist_import_is_bounded_and_marks_remaining_items(client, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/playlistItems'):
            return httpx.Response(200, json={'items': [{'snippet': {'resourceId': {'videoId': FIRST}}}] * 50, 'nextPageToken': f'PAGE{len(calls)}'})
        return httpx.Response(200, json={'items': [video(FIRST)]})
    network(monkeypatch, handler)
    data = (await client.get(f'{BASE}/playlists/{PLAYLIST}?limit=2')).json()
    assert len(data['tracks']) == 2 and data['truncated'] and len(calls) == 2
    calls.clear()
    data = (await client.get(f'{BASE}/playlists/{PLAYLIST}')).json()
    assert len(data['tracks']) == 200 and data['truncated'] and len(calls) == 5


@pytest.mark.parametrize(('status', 'reason', 'expected'), [(403, 'quotaExceeded', 503), (403, 'forbidden', 503), (404, 'playlistNotFound', 404), (400, 'invalidPageToken', 400), (400, 'keyInvalid', 503), (403, 'accessNotConfigured', 503), (500, 'backendError', 502)])
async def test_google_errors_are_actionable_and_do_not_leak_key(client, monkeypatch, status, reason, expected):
    network(monkeypatch, lambda _: httpx.Response(status, json={'error': {'message': 'secret test-key-never-return', 'errors': [{'reason': reason}]}}))
    response = await client.get(f'{BASE}/playlists/{PLAYLIST}')
    assert response.status_code == expected and 'test-key-never-return' not in response.text
    assert not catalog._cache


async def test_partial_playlist_failure_never_returns_partial_tracks(client, monkeypatch):
    def handler(request):
        if not request.url.params.get('pageToken'):
            return httpx.Response(200, json={'items': [{'snippet': {'resourceId': {'videoId': FIRST}}}], 'nextPageToken': 'PAGE2'})
        raise httpx.ReadTimeout('URL includes secret test-key-never-return', request=request)
    network(monkeypatch, handler)
    response = await client.get(f'{BASE}/playlists/{PLAYLIST}')
    assert response.status_code == 504 and 'tracks' not in response.json() and 'test-key-never-return' not in response.text


async def test_rate_limit_is_separate_from_chat_and_cached_pages_do_not_spend_again(client, monkeypatch):
    monkeypatch.setattr(catalog, 'admission', Admission(cooldown=60))
    def handler(request):
        return httpx.Response(200, json={'items': []})
    network(monkeypatch, handler)
    assert (await client.get(BASE + '/search?q=Tetris')).status_code == 200
    assert (await client.get(BASE + '/search?q=Tetris')).status_code == 200
    response = await client.get(BASE + '/search?q=Vampire')
    assert response.status_code == 429 and int(response.headers['Retry-After']) > 0


@pytest.mark.parametrize('body', [b'not-json', b'[]', b'{"items": null}', b'x' * (catalog.MAX_RESPONSE_BYTES + 1)], ids=['not-json', 'array', 'missing-items', 'oversized'])
async def test_invalid_or_oversized_response_is_handled(client, monkeypatch, body):
    network(monkeypatch, lambda _: httpx.Response(200, content=body))
    assert (await client.get(BASE + '/search?q=Tetris')).status_code == 502

"""Turn-scoped catalogue evidence. Only server-resolved tracks cross the browser bridge."""
from __future__ import annotations

import re
from contextlib import aclosing
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from pydantic import Field, ValidationError, field_validator

from ai.base import StreamChunk
from features.companion import youtube_catalog as catalog
from features.companion.player_tools import Command, Track
from shared import youtube


class Media(Track):
    duration: int = Field(default=0, ge=0, le=604800)
    start_seconds: int = Field(default=0, ge=0, le=604800)

    @field_validator('duration', mode='before')
    @classmethod
    def bound_duration(cls, value):
        return min(value, 604800) if type(value) is int and value >= 0 else value


def source(value: str) -> dict | None:
    """Same allowed hosts/paths as the Player; input is never used as a network destination."""
    if not value or len(value) > 4096 or re.search(r'[\s\x00-\x1f\x7f\\]', value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or url.hostname not in youtube.HOSTS or url.username or url.password or url.port:
            return None
        path = url.path.rstrip('/').split('/')[1:]
        query = parse_qs(url.query, keep_blank_values=True)
        video = ''
        if url.hostname in ('youtu.be', 'www.youtu.be') and len(path) == 1:
            video = path[0]
        elif path == ['watch'] and len(query.get('v', [])) == 1:
            video = query['v'][0]
        elif len(path) == 2 and path[0] in youtube.PATH_PREFIXES:
            video = path[1]
        if not youtube.VIDEO_ID.fullmatch(video):
            video = ''
        playlist = query.get('list', [])
        playlist = playlist[0] if len(playlist) == 1 and (video or path == ['playlist']) and catalog.PLAYLIST_ID.fullmatch(playlist[0]) else ''
        raw_time = (query.get('start') or query.get('t') or parse_qs(url.fragment).get('t') or ['0'])[0]
        parts = re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', raw_time)
        seconds = int(raw_time) if re.fullmatch(r'\d{1,8}', raw_time) else sum(int(part or 0) * scale for part, scale in zip(parts.groups(), (3600, 60, 1))) if parts and len(raw_time) <= 32 else 0
        return {'video_id': video, 'playlist_id': playlist, 'start_seconds': min(seconds, 604800)} if video or playlist else None
    except (ValueError, OverflowError):
        return None


class Discovery:
    def __init__(self, owner: str, user_text: str):
        self.owner = owner
        self.tracks: dict[str, Media] = {}
        self.sources = [parsed for match in youtube.URL.finditer(user_text) if (parsed := source(match.group(0).rstrip('.,;:!?')))]
        self.window_revision: int | None = None

    def observe(self, result: dict):
        if not result.get('ok'):
            return
        data = result.get('data') or {}
        values = [(result.get('state') or {}).get('track'), data.get('target'), *data.get('items', [])]
        for item in values:
            if item:
                previous = self.tracks.get(item['video_id'])
                media = Media.model_validate({**(previous.model_dump() if previous else {}), **{key: item[key] for key in ('video_id', 'title', 'artist')}})
                if len(self.tracks) < 500 or media.video_id in self.tracks:
                    self.tracks[media.video_id] = media

    async def run(self, command: Command, request):
        try:
            # Capture X's generation before catalogue work. Closing during lookup cancels later playback/appends.
            async with aclosing(request(Command(action='status'))) as reading:
                async for item in reading:
                    if isinstance(item, StreamChunk):
                        yield item
                    else:
                        before = item
            state = before.get('state') or {}
            if not before.get('ok') or state.get('window_revision') is None:
                yield {'ok': False, 'error': 'The sending Player did not confirm its current session. No new music was selected.'}
                return
            self.observe(before)
            if self.window_revision is None:
                self.window_revision = state['window_revision']
            if state['window_revision'] != self.window_revision:
                yield {'ok': False, 'error': 'Player was closed during this request. No new music was selected; do not retry automatically.'}
                return

            if command.action == 'search_videos':
                if not command.query.strip():
                    yield {'ok': False, 'error': 'Supply a song, artist or mood to search.'}
                    return
                data = await catalog.search(self.owner, command.query, command.page_token or '')
                found = [Media.model_validate(item) for item in data['tracks'][:20]]
                self.tracks.update((item.video_id, item) for item in found)
                yield {'ok': True, 'data': {'kind': 'search', 'items': [item.model_dump() for item in found],
                                          'next_page_token': data['next_page_token']}}
                return

            if command.action == 'enqueue_playlist':
                parsed = source(command.url)
                playlist = parsed['playlist_id'] if parsed else ''
                if not playlist or not any(item['playlist_id'] == playlist for item in self.sources):
                    yield {'ok': False, 'error': 'Use a valid playlist URL supplied by the user. Nothing was imported.'}
                    return
                capacity = 200 - state['queue_count']
                if capacity <= 0:
                    yield {'ok': False, 'state': state, 'error': 'Queue is full (200 upcoming songs). Nothing was imported.'}
                    return
                data = await catalog.playlist(self.owner, playlist, capacity)
                tracks = [Media.model_validate(item) for item in data['tracks']]
                skipped, truncated = data['skipped'], data['truncated']
            else:
                track = self.tracks.get(command.video_id) if command.video_id else None
                if command.url:
                    parsed = source(command.url)
                    video = parsed['video_id'] if parsed else ''
                    supplied = next((item for item in self.sources if video and item['video_id'] == video), None)
                    if supplied:
                        info = await youtube.lookup(video)
                        if info:
                            track = Media(video_id=video, title=info['title'], artist=info['channel'], start_seconds=supplied['start_seconds'])
                if not track:
                    yield {'ok': False, 'error': 'No verified video selected. Search first or use a valid video URL supplied by the user; never invent an ID or title.'}
                    return
                self.tracks[track.video_id] = track
                tracks, skipped, truncated = [track], 0, False
            if not tracks:
                yield {'ok': False, 'error': 'No playable videos were found. Nothing was added or played.'}
                return

            async with aclosing(request(command, tracks=[item.model_dump() for item in tracks], window_revision=self.window_revision)) as applying:
                async for item in applying:
                    if isinstance(item, StreamChunk):
                        yield item
                    else:
                        result = item
            if result.get('ok'):
                if command.action == 'play_video':
                    observed = result.get('state') or {}
                    if observed.get('status') != 'playing' or (observed.get('track') or {}).get('video_id') != tracks[0].video_id:
                        yield {'ok': False, 'state': observed, 'error': 'The selected video was not confirmed playing. Do not claim it started or retry automatically.'}
                        return
                else:
                    added = (result.get('data') or {}).get('added')
                    if added is None or added > len(tracks):
                        yield {'ok': False, 'state': result.get('state'), 'error': 'Player did not confirm how many songs were added. Do not import again automatically.'}
                        return
                    if command.action == 'enqueue_video' and added and ((result.get('data') or {}).get('target') or {}).get('video_id') != tracks[0].video_id:
                        yield {'ok': False, 'state': result.get('state'), 'error': 'Player did not confirm the selected song was added. Do not add it again automatically.'}
                        return
                    result['data'].update(skipped_unavailable=skipped, truncated=truncated,
                                          not_added_capacity=len(tracks) - added)
                self.observe(result)
            yield result
        except HTTPException as error:
            # Catalogue errors are sanitized at their source; never expose upstream requests or keys.
            yield {'ok': False, 'error': str(error.detail)}
        except ValidationError:
            yield {'ok': False, 'error': 'YouTube returned invalid video metadata. No new playback or import was confirmed.'}

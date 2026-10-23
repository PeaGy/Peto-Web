"""Thông tin video, yêu thích và khám phá YouTube cho Player."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from features.accounts.auth import current_owner
from features.companion import youtube_catalog, player_tools
from shared import youtube
from storage import player as store

router = APIRouter(prefix='/api/companion/player', tags=['companion-player'])


@router.post('/commands/{command_id}/result')
async def player_command_result(command_id: str, body: player_tools.Result, owner: str = Depends(current_owner)):
    if not player_tools.acknowledge(owner, command_id, body):
        raise HTTPException(404, 'Lệnh Player không còn chờ kết quả.')
    return {'accepted': True}


@router.get('/search')
async def search_videos(q: str = Query(min_length=1, max_length=200),
                        page_token: str = Query(default='', max_length=512, pattern=r'^[A-Za-z0-9_+=/\-]*$'),
                        owner: str = Depends(current_owner)) -> dict:
    return await youtube_catalog.search(owner, q, page_token)


@router.get('/playlists/{playlist_id}')
async def import_playlist(playlist_id: str, limit: int = Query(default=200, ge=1, le=200),
                          owner: str = Depends(current_owner)) -> dict:
    return await youtube_catalog.playlist(owner, playlist_id, limit)


def checked_id(video_id: str) -> str:
    if not youtube.VIDEO_ID.fullmatch(video_id):
        raise HTTPException(400, 'Mã video YouTube chưa hợp lệ.')
    return video_id


@router.get('/videos/{video_id}')
async def video_info(video_id: str, owner: str = Depends(current_owner)) -> dict:
    info = await youtube.lookup(checked_id(video_id))
    return {'video_id': video_id, 'title': info['title'] if info else '', 'artist': info['channel'] if info else ''}


@router.get('/favorites')
async def favorites(owner: str = Depends(current_owner)) -> dict:
    return {'favorites': await store.list_favorites(owner)}


@router.post('/favorites/{video_id}')
async def save_favorite(video_id: str, owner: str = Depends(current_owner)) -> dict:
    info = await youtube.lookup(checked_id(video_id))
    if not await store.save_favorite(owner, video_id, info['title'] if info else '', info['channel'] if info else ''):
        raise HTTPException(400, f'Danh sách đã có {store.MAX_FAVORITES} bài yêu thích.')
    return {'favorites': await store.list_favorites(owner)}


@router.delete('/favorites/{video_id}')
async def delete_favorite(video_id: str, owner: str = Depends(current_owner)) -> dict:
    await store.delete_favorite(owner, checked_id(video_id))
    return {'favorites': await store.list_favorites(owner)}

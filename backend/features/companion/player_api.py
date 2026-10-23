"""Thông tin video và tim yêu thích cho Player. Playlist/tìm kiếm chưa thuộc giai đoạn này."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from features.accounts.auth import current_owner
from shared import youtube
from storage import player as store

router = APIRouter(prefix='/api/companion/player', tags=['companion-player'])


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

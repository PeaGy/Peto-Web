"""Per-account opt-out from reading the Discord bot's memory, independent of Peto's own memory settings."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, StrictBool

from core.config import discord_id_from_owner
from features.accounts.auth import current_owner
from features.accounts.discord_memory import discord_memory
from storage import users

router = APIRouter(prefix='/api/account/discord-memory', tags=['account'])


class DiscordMemorySettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: StrictBool


async def _account(owner):
    user = await users.get_user(owner)
    if not user or user['provider'] != 'discord' or not discord_id_from_owner(owner):
        raise HTTPException(403, 'Tùy chọn này chỉ dành cho tài khoản đăng nhập bằng Discord.')
    return user


@router.get('')
async def read_settings(response: Response, owner: str = Depends(current_owner)):
    user = await _account(owner)
    response.headers['Cache-Control'] = 'no-store'
    return {'enabled': bool(user['discord_memory_enabled']), 'available': discord_memory.enabled}


@router.put('')
async def update_settings(body: DiscordMemorySettings, response: Response, owner: str = Depends(current_owner)):
    await _account(owner)
    await users.set_discord_memory_enabled(owner, body.enabled)
    # No gateway request: this preference is also writable while the bot is offline/unconfigured.
    response.headers['Cache-Control'] = 'no-store'
    return {'enabled': body.enabled, 'available': discord_memory.enabled}

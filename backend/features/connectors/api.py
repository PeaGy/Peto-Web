"""Quản lý kết nối GitHub và callback cấp quyền gắn với đúng phiên Peto."""
import base64
import hashlib
import secrets
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from core.config import SESSION_COOKIE
from features.accounts.auth import current_owner
from features.connectors import github
from storage import connectors as store

router = APIRouter(prefix='/api/connectors', tags=['connectors'])


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def returned(result):
    base = github.FRONTEND_URL or '/'
    separator = '&' if '?' in base else '?'
    return RedirectResponse(base + separator + urlencode({'connector_result': result}), status_code=303,
                            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})


@router.get('')
async def list_connectors(owner: str = Depends(current_owner)):
    return {'connectors': [await github.status(owner)]}


@router.post('/github/connect')
async def connect(request: Request, owner: str = Depends(current_owner)):
    if not github.configured():
        raise HTTPException(503, 'Người quản trị cần cấu hình GitHub App trước khi kết nối.')
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    async with github.lock(owner):
        await store.put_state(digest(state), owner, digest(request.cookies[SESSION_COOKIE]), github.encrypt(verifier))
    return {'authorize_url': 'https://github.com/login/oauth/authorize?' + urlencode({
        'client_id': github.CLIENT_ID, 'redirect_uri': github.REDIRECT_URI, 'state': state,
        'code_challenge': challenge, 'code_challenge_method': 'S256'})}


@router.get('/github/callback')
async def callback(request: Request, owner: str = Depends(current_owner)):
    state, code = request.query_params.get('state', ''), request.query_params.get('code', '')
    if not state or len(state) > 200 or len(code) > 512:
        return returned('invalid')
    async with github.lock(owner):
        verifier = await store.take_state(digest(state), owner, digest(request.cookies[SESSION_COOKIE]))
        if not verifier:
            return returned('invalid')
        if request.query_params.get('error') or not code:
            return returned('cancelled')
        try:
            data = await github.exchange({'code': code, 'redirect_uri': github.REDIRECT_URI,
                                          'code_verifier': github.decrypt(verifier)})
            user = await github.api_get(data['access_token'], '/user')
            login = user.get('login', '')
            if not isinstance(login, str) or not login or len(login) > 80:
                raise github.GitHubError('Chưa xác minh được tài khoản GitHub.')
            await store.save_github(owner, login, github.encrypt(data), uuid.uuid4().hex)
        except github.GitHubError:
            return returned('failed')
    return returned('connected')


@router.post('/github/check')
async def check(owner: str = Depends(current_owner)):
    try:
        token = await github.access_token(owner)
        await github.api_get(token, '/user')
        return await github.status(owner)
    except github.GitHubError as err:
        raise HTTPException(400, str(err)) from None


@router.delete('/github')
async def disconnect(owner: str = Depends(current_owner)):
    async with github.lock(owner):
        await store.disconnect_github(owner)
    return {'disconnected': True}

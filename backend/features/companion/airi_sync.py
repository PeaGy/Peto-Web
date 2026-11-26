"""Đồng bộ hội thoại Companion bản AIRI giữa các máy của cùng một tài khoản Peto.

Bộ não AIRI giữ hội thoại trong trình duyệt và tự đồng bộ với máy chủ đám mây của AIRI khi có tài khoản AIRI
(``packages/stage-ui/src/libs/chat-sync`` trong bản fork ``PeaGy/peto-airi``). Bản Peto không có tài khoản AIRI, nên
máy chủ Peto đóng vai máy chủ đó, nói đúng giao thức của nó, dưới tiền tố ``/api/companion/airi-cloud``:

- ``GET /api/companion/sync/session`` (cookie phiên Peto): mã người dùng mờ (không lộ khóa owner) và mã đồng bộ ký bằng
  bí mật phiên, hạn ``TOKEN_MAX_AGE``. Trang AIRI lấy mỗi lần mở.
- REST ``/api/v1/chats`` (liệt kê, tạo, đọc, đổi tên, xóa), xác thực bằng ``Authorization: Bearer <mã đồng bộ>``:
  trình duyệt gọi bằng ``authedFetch`` của AIRI, vốn không gửi cookie.
- WebSocket ``/ws/v2/chat``: khung eventa 1.0 (``deliveryId``, ``eventa``: ``id``, ``invokeType``, ``body``). Khung
  đầu phải là ``chat:authenticate`` với mã đồng bộ trong 15 giây; sau đó ``chat:send-messages`` (ghi tin, báo
  ``chat:new-messages`` cho các kết nối khác của cùng tài khoản) và ``chat:pull-messages`` (kéo tin sau một ``seq``).
  Chỉ dựa vào mã: trang khác không đọc được mã (``/sync/session`` cùng nguồn, không có CORS), nên không mượn được
  cookie để mở kết nối thay người dùng.
- REST ``/api/v1/attachments`` (từ 26/11/2026), bearer như trên: đăng ký ảnh, ``/{id}/finalize`` báo đã tải lên,
  ``/{id}/download`` xin địa chỉ tải về. Byte ảnh đi qua ``/{id}/content?sig=…``: địa chỉ có chữ ký, hạn
  ``LINK_MAX_AGE``, vì trang AIRI đẩy và tải byte bằng ``XMLHttpRequest``/``fetch`` trần, không kèm mã đồng bộ. Chữ ký
  chỉ mang mã người dùng mờ, không mang owner, vì địa chỉ có thể vào log của proxy.

Chỉ bật khi đặt ``PETO_AIRI_DIR``, như cổng model. Nội dung tin không bao giờ vào log; log chỉ có số đếm.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from itsdangerous import BadSignature, SignatureExpired

from core import config
from core.config import SESSION_COOKIE, provider_from_owner
from features.accounts.auth import issued_after_deletion, live_session_owner, signer
from shared.attachments import sniff_image_mime
from storage import airi_chats
from storage.airi_chats import ATTACHMENT_ID, IMAGE_MIMES, MAX_ATTACHMENT_BYTES, MAX_MEDIA_PER_MESSAGE, SHA256_HEX, SyncError

logger = logging.getLogger("peto_web.airi_sync")
router = APIRouter()

PREFIX = "/api/companion/airi-cloud"
TOKEN_MAX_AGE = 30 * 24 * 3600
AUTH_TIMEOUT_SECONDS = 15.0
MAX_AUTH_FRAME_BYTES = 8192
MAX_PRE_AUTH_FRAMES = 4
MAX_REST_BODY_BYTES = 64 * 1024
MAX_ID_CHARS = 64
MAX_TITLE_CHARS = 500
MAX_MEMBERS = 20
MAX_MESSAGES_PER_SEND = 500
MAX_MESSAGE_CHARS = 1_000_000
MAX_SOCKETS_PER_OWNER = 20
MAX_UNAUTHENTICATED_SOCKETS = 100
# Mã đóng của AIRI (``libs/ws-auth.ts`` máy chủ, ``WS_CLOSE_UNAUTHORIZED`` của trình duyệt): nhận 4001 thì trình duyệt
# ngừng tự kết nối lại cho tới khi có mã mới.
CLOSE_UNAUTHORIZED = 4001
CLOSE_TRY_AGAIN_LATER = 1013
SYNC_ROLES = ("user", "assistant")

_tokens = signer("peto-airi-chat-sync")
_attachment_links = signer("peto-airi-attachment")
LINK_MAX_AGE = 15 * 60
MAX_LINK_CHARS = 1024


_user_ids: dict[str, str] = {}


async def sync_user_id(owner: str) -> str:
    """Mã người dùng mà trang AIRI thấy (``storage.airi_chats.sync_user_id``): cố định cho mỗi tài khoản, không đoán
    ngược ra owner hay ID Discord, không đổi khi đổi PETO_SESSION_SECRET. Giữ trong bộ nhớ sau lần đọc đầu."""
    user_id = _user_ids.get(owner)
    if user_id is None:
        user_id = _user_ids[owner] = await airi_chats.sync_user_id(owner)
    return user_id


def issue_token(owner: str) -> str:
    return _tokens.dumps({"owner": owner})


def token_owner(token: object) -> str | None:
    if not isinstance(token, str) or not token or len(token) > 4096:
        return None
    try:
        data = _tokens.loads(token, max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    owner = data.get("owner") if isinstance(data, dict) else None
    return owner if isinstance(owner, str) and provider_from_owner(owner) else None


async def live_token_owner(token: object) -> str | None:
    """Như ``token_owner`` nhưng từ chối mã ký trước khi tài khoản bị xóa (``auth.issued_after_deletion``)."""
    owner = token_owner(token)
    if not owner:
        return None
    _, signed = _tokens.loads(token, max_age=TOKEN_MAX_AGE, return_timestamp=True)
    return owner if await issued_after_deletion(owner, signed.timestamp()) else None


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message, "message": message}, status_code=status, headers={"Cache-Control": "no-store"})


def _enabled() -> bool:
    return config.AIRI_DIR is not None


# --- Mã đồng bộ ---------------------------------------------------------------------------------------------------

@router.get("/api/companion/sync/session")
async def sync_session(request: Request):
    if not _enabled():
        return _error(404, "Đồng bộ Companion AIRI chưa được bật trên máy chủ này.")
    owner = await live_session_owner(request.cookies.get(SESSION_COOKIE))
    if not owner:
        return _error(401, "Chưa đăng nhập Peto.")
    return JSONResponse({"userId": await sync_user_id(owner), "token": issue_token(owner), "expiresIn": TOKEN_MAX_AGE},
                        headers={"Cache-Control": "no-store"})


# --- REST hội thoại ------------------------------------------------------------------------------------------------

async def _bearer_owner(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return await live_token_owner(token.strip()) if scheme.lower() == "bearer" else None


def _text(value: object, limit: int, what: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        raise SyncError(400, f"{what} không hợp lệ.")
    return value


async def _json_body(request: Request) -> dict:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_REST_BODY_BYTES:
        raise SyncError(413, "Yêu cầu quá lớn.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_REST_BODY_BYTES:
            raise SyncError(413, "Yêu cầu quá lớn.")
    try:
        body = json.loads(raw or b"null")
    except (UnicodeDecodeError, ValueError):
        raise SyncError(400, "Thân yêu cầu không phải JSON.") from None
    if not isinstance(body, dict):
        raise SyncError(400, "Thân yêu cầu không hợp lệ.")
    return body


def _title(body: dict) -> str | None:
    title = body.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > MAX_TITLE_CHARS):
        raise SyncError(400, "Tên cuộc trò chuyện không hợp lệ.")
    return title


def _members(raw: object) -> list[dict]:
    """Thành viên không phải người dùng (nhân vật của hội thoại). Người tạo luôn là thành viên người dùng."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_MEMBERS:
        raise SyncError(400, "Danh sách thành viên không hợp lệ.")
    members = []
    for item in raw:
        if not isinstance(item, dict) or item.get("type") not in ("user", *airi_chats.MEMBER_TYPES):
            raise SyncError(400, "Thành viên không hợp lệ.")
        if item["type"] == "user":
            continue
        members.append({"type": item["type"],
                        "characterId": _text(item.get("characterId"), MAX_ID_CHARS, "Mã nhân vật")})
    return members


async def _rest(request: Request, action):
    if not _enabled():
        return _error(404, "Đồng bộ Companion AIRI chưa được bật trên máy chủ này.")
    owner = await _bearer_owner(request)
    if not owner:
        return _error(401, "Mã đồng bộ không hợp lệ hoặc đã hết hạn. Mở lại trang Companion nhé.")
    try:
        status, payload = await action(owner, await sync_user_id(owner))
    except SyncError as error:
        return _error(error.status, error.message)
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})


@router.get(PREFIX + "/api/v1/chats")
async def list_chats(request: Request):
    async def action(owner, user_id):
        return 200, {"chats": await airi_chats.list_chats(owner, user_id)}
    return await _rest(request, action)


@router.post(PREFIX + "/api/v1/chats")
async def create_chat(request: Request):
    async def action(owner, user_id):
        body = await _json_body(request)
        chat_id = _text(body.get("id"), MAX_ID_CHARS, "Mã cuộc trò chuyện", optional=True) or uuid.uuid4().hex[:21]
        chat_type = body.get("type", "group")
        if chat_type not in airi_chats.CHAT_TYPES:
            raise SyncError(400, "Loại cuộc trò chuyện không hợp lệ.")
        chat = await airi_chats.create_chat(owner, user_id, chat_id, chat_type, _title(body), _members(body.get("members")))
        logger.info("airi_sync create_chat members=%d", len(chat["members"]))
        return 201, chat
    return await _rest(request, action)


@router.get(PREFIX + "/api/v1/chats/{chat_id}")
async def get_chat(request: Request, chat_id: str):
    async def action(owner, user_id):
        return 200, await airi_chats.get_chat(owner, user_id, chat_id)
    return await _rest(request, action)


@router.patch(PREFIX + "/api/v1/chats/{chat_id}")
async def update_chat(request: Request, chat_id: str):
    async def action(owner, user_id):
        return 200, await airi_chats.update_chat(owner, user_id, chat_id, _title(await _json_body(request)))
    return await _rest(request, action)


@router.delete(PREFIX + "/api/v1/chats/{chat_id}")
async def delete_chat(request: Request, chat_id: str):
    async def action(owner, user_id):
        chat = await airi_chats.delete_chat(owner, user_id, chat_id)
        logger.info("airi_sync delete_chat")
        return 200, chat
    return await _rest(request, action)


# --- Ảnh ------------------------------------------------------------------------------------------------------------

def _attachment_id(value: object) -> str:
    if not isinstance(value, str) or not ATTACHMENT_ID.fullmatch(value):
        raise SyncError(400, "Mã ảnh không hợp lệ.")
    return value


def _attachment_link(request: Request, user_id: str, attachment_id: str, action: str) -> str:
    signature = _attachment_links.dumps({"u": user_id, "a": attachment_id, "k": action})
    base = str(request.base_url).rstrip("/")
    return f"{base}{PREFIX}/api/v1/attachments/{attachment_id}/content?sig={signature}"


async def _link_owner(request: Request, attachment_id: str, action: str) -> str | None:
    """Tài khoản của một địa chỉ ảnh có chữ ký; ``None`` khi sai, hết hạn, khác ảnh hay khác việc (tải lên/tải về)."""
    signature = request.query_params.get("sig", "")
    if not signature or len(signature) > MAX_LINK_CHARS:
        return None
    try:
        data = _attachment_links.loads(signature, max_age=LINK_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or data.get("a") != attachment_id or data.get("k") != action:
        return None
    user_id = data.get("u")
    return await airi_chats.owner_of_user(user_id) if isinstance(user_id, str) else None


def _image_matches(data: bytes, row: dict) -> bool:
    return (len(data) == row["size"] and hashlib.sha256(data).hexdigest() == row["sha256"]
            and sniff_image_mime(data) == row["mime"])


@router.post(PREFIX + "/api/v1/attachments")
async def create_attachment(request: Request):
    async def action(owner, user_id):
        body = await _json_body(request)
        attachment_id = _attachment_id(body.get("id"))
        mime, sha256, size = body.get("mimeType"), body.get("sha256"), body.get("size")
        if mime not in IMAGE_MIMES:
            raise SyncError(400, "Chỉ đồng bộ được ảnh PNG, JPEG, WebP hoặc GIF.")
        if not isinstance(sha256, str) or not SHA256_HEX.fullmatch(sha256):
            raise SyncError(400, "Mã băm của ảnh không hợp lệ.")
        if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= MAX_ATTACHMENT_BYTES:
            raise SyncError(400, "Ảnh phải nhỏ hơn 3 MB.")
        attachment, needs_upload = await airi_chats.create_attachment(owner, user_id, attachment_id, mime, sha256, size)
        upload = {"url": _attachment_link(request, user_id, attachment_id, "put"), "headers": {}} if needs_upload else None
        logger.info("airi_sync create_attachment bytes=%d upload=%s", size, needs_upload)
        return 201, {"attachment": attachment, "upload": upload}
    return await _rest(request, action)


@router.put(PREFIX + "/api/v1/attachments/{attachment_id}/content")
async def upload_attachment(request: Request, attachment_id: str):
    if not _enabled():
        return _error(404, "Đồng bộ Companion AIRI chưa được bật trên máy chủ này.")
    owner = await _link_owner(request, attachment_id, "put")
    if not owner:
        return _error(403, "Địa chỉ tải ảnh lên không hợp lệ hoặc đã hết hạn.")
    row = await airi_chats.get_attachment(owner, attachment_id)
    if row is None:
        return _error(404, "Không tìm thấy ảnh này.")
    if row["state"] == "ready":
        # Trang AIRI coi 412 là ảnh đã có sẵn (giống S3 với If-None-Match) và đi tiếp tới finalize.
        return _error(412, "Ảnh này đã tải lên rồi.")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) != row["size"]:
        return _error(400, "Ảnh tải lên không khớp kích thước đã đăng ký.")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > row["size"]:
            return _error(400, "Ảnh tải lên không khớp kích thước đã đăng ký.")
    if not _image_matches(bytes(data), row):
        return _error(400, "Ảnh tải lên không khớp ảnh đã đăng ký.")
    path = Path(row["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, path)
    logger.info("airi_sync upload_attachment bytes=%d", len(data))
    return Response(status_code=200)


@router.post(PREFIX + "/api/v1/attachments/{attachment_id}/finalize")
async def finalize_attachment(request: Request, attachment_id: str):
    async def action(owner, user_id):
        row = await airi_chats.get_attachment(owner, attachment_id)
        if row is None:
            raise SyncError(404, "Không tìm thấy ảnh này.")
        if row["state"] != "ready":
            path = Path(row["path"])
            if not path.is_file() or not _image_matches(path.read_bytes(), row):
                raise SyncError(409, "Ảnh chưa tải lên xong.")
            await airi_chats.mark_attachment_ready(owner, attachment_id)
        return 200, airi_chats.public_attachment(row)
    return await _rest(request, action)


@router.get(PREFIX + "/api/v1/attachments/{attachment_id}/download")
async def download_attachment(request: Request, attachment_id: str):
    async def action(owner, user_id):
        row = await airi_chats.get_attachment(owner, attachment_id)
        if row is None or row["state"] != "ready":
            raise SyncError(404, "Không tìm thấy ảnh này.")
        return 200, {"attachment": airi_chats.public_attachment(row), "sha256": row["sha256"],
                     "url": _attachment_link(request, user_id, attachment_id, "get")}
    return await _rest(request, action)


@router.get(PREFIX + "/api/v1/attachments/{attachment_id}/content")
async def attachment_content(request: Request, attachment_id: str):
    if not _enabled():
        return _error(404, "Đồng bộ Companion AIRI chưa được bật trên máy chủ này.")
    owner = await _link_owner(request, attachment_id, "get")
    if not owner:
        return _error(403, "Địa chỉ tải ảnh không hợp lệ hoặc đã hết hạn.")
    row = await airi_chats.get_attachment(owner, attachment_id)
    if row is None or row["state"] != "ready" or not Path(row["path"]).is_file():
        return _error(404, "Không tìm thấy ảnh này.")
    return FileResponse(row["path"], media_type=row["mime"],
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


# --- WebSocket ------------------------------------------------------------------------------------------------------

def frame(event_id: str, body: object, invoke_type: int | None = None) -> str:
    """Một khung eventa 1.0 (kèm các trường cũ ``id``/``type``/``payload`` mà eventa vẫn đọc)."""
    delivery = uuid.uuid4().hex[:16]
    eventa = {"id": event_id, "type": "event", "body": body, "_flowDirection": "outbound"}
    if invoke_type is not None:
        eventa["invokeType"] = invoke_type
    return json.dumps({"deliveryId": delivery, "hopsRemaining": 31, "eventa": eventa, "id": delivery,
                       "type": event_id, "payload": eventa, "timestamp": round(time.time() * 1000)},
                      ensure_ascii=False)


def parse_request(text: str) -> tuple[str, str, object] | None:
    """(tên lời gọi, invokeId, nội dung) của một khung yêu cầu ``<tên>-send``; khung khác trả None."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    eventa = data.get("eventa") or data.get("payload") if isinstance(data, dict) else None
    if not isinstance(eventa, dict):
        return None
    event_id, body = eventa.get("id"), eventa.get("body")
    if not isinstance(event_id, str) or not event_id.endswith("-send") or not isinstance(body, dict):
        return None
    invoke_id = body.get("invokeId")
    if not isinstance(invoke_id, str) or not invoke_id or len(invoke_id) > 128:
        return None
    return event_id[: -len("-send")], invoke_id, body.get("content")


def reply(name: str, invoke_id: str, content: object) -> str:
    return frame(f"{name}-receive-{invoke_id}", {"invokeId": invoke_id, "content": content}, invoke_type=4)


def reply_error(name: str, invoke_id: str, message: str) -> str:
    return frame(f"{name}-receive-error-{invoke_id}",
                 {"invokeId": invoke_id, "content": {"error": {"name": "Error", "message": message}}}, invoke_type=5)


class _Peer:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.lock = asyncio.Lock()

    async def send(self, text: str) -> None:
        async with self.lock:
            await self.websocket.send_text(text)


_peers: dict[str, dict[int, _Peer]] = {}
_unauthenticated = 0


async def _broadcast(owner: str, exclude: _Peer, payload: dict) -> None:
    text = frame("chat:new-messages", payload)
    for peer in list(_peers.get(owner, {}).values()):
        if peer is exclude:
            continue
        try:
            await peer.send(text)
        except Exception:  # noqa: BLE001 - một máy rớt kết nối không làm hỏng lượt ghi
            pass


def _send_request(content: object) -> tuple[str, list[dict]]:
    if not isinstance(content, dict):
        raise SyncError(400, "Yêu cầu gửi tin không hợp lệ.")
    chat_id = _text(content.get("chatId"), MAX_ID_CHARS, "Mã cuộc trò chuyện")
    messages = content.get("messages")
    if not isinstance(messages, list) or len(messages) > MAX_MESSAGES_PER_SEND:
        raise SyncError(400, "Danh sách tin nhắn không hợp lệ.")
    clean = []
    for message in messages:
        if not isinstance(message, dict):
            raise SyncError(400, "Tin nhắn không hợp lệ.")
        if message.get("role") not in SYNC_ROLES:
            raise SyncError(400, "Chỉ đồng bộ được tin của người dùng và tin trả lời.")
        content_text = message.get("content")
        if not isinstance(content_text, str) or len(content_text) > MAX_MESSAGE_CHARS:
            raise SyncError(400, "Nội dung tin nhắn không hợp lệ.")
        media_ids = message.get("mediaIds") or []
        if (not isinstance(media_ids, list) or len(media_ids) > MAX_MEDIA_PER_MESSAGE
                or len(set(map(str, media_ids))) != len(media_ids)):
            raise SyncError(400, f"Mỗi tin kèm tối đa {MAX_MEDIA_PER_MESSAGE} ảnh khác nhau.")
        clean.append({"id": _text(message.get("id"), MAX_ID_CHARS, "Mã tin nhắn"), "role": message["role"],
                      "content": content_text, "mediaIds": [_attachment_id(media_id) for media_id in media_ids],
                      "replyToMessageId": _text(message.get("replyToMessageId"), MAX_ID_CHARS, "Mã tin trả lời",
                                                optional=True)})
    return chat_id, clean


def _pull_request(content: object) -> tuple[str, int, int | None]:
    if not isinstance(content, dict):
        raise SyncError(400, "Yêu cầu kéo tin không hợp lệ.")
    chat_id = _text(content.get("chatId"), MAX_ID_CHARS, "Mã cuộc trò chuyện")
    after, limit = content.get("afterSeq"), content.get("limit")
    if not isinstance(after, int) or isinstance(after, bool) or after < 0:
        raise SyncError(400, "afterSeq không hợp lệ.")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise SyncError(400, "limit không hợp lệ.")
    return chat_id, after, limit


async def _handle(peer: _Peer, owner: str, user_id: str, name: str, invoke_id: str, content: object) -> None:
    try:
        if name == "chat:send-messages":
            chat_id, messages = _send_request(content)
            result = await airi_chats.push_messages(owner, user_id, chat_id, messages)
            logger.info("airi_sync send_messages count=%d", len(messages))
            await peer.send(reply(name, invoke_id, {"seq": result["seq"]}))
            if result["messages"]:
                await _broadcast(owner, peer, {"chatId": chat_id, "messages": result["messages"],
                                               "fromSeq": result["fromSeq"], "toSeq": result["toSeq"]})
        elif name == "chat:pull-messages":
            chat_id, after, limit = _pull_request(content)
            await peer.send(reply(name, invoke_id, await airi_chats.pull_messages(owner, user_id, chat_id, after, limit)))
        elif name == "chat:authenticate":
            # Kết nối đã xác thực: trả lại đúng người dùng như lần đầu.
            if token_owner((content or {}).get("token") if isinstance(content, dict) else None) != owner:
                raise SyncError(401, "Mã đồng bộ không khớp tài khoản của kết nối này.")
            await peer.send(reply(name, invoke_id, {"userId": user_id}))
        else:
            await peer.send(reply_error(name, invoke_id, "Lời gọi này không có trên máy chủ Peto."))
    except SyncError as error:
        await peer.send(reply_error(name, invoke_id, error.message))
    except Exception:  # noqa: BLE001 - lỗi lạ chỉ hỏng lời gọi này, kết nối vẫn chạy
        logger.exception("Lỗi khi xử lý %s của đồng bộ AIRI", name)
        await peer.send(reply_error(name, invoke_id, "Máy chủ Peto gặp lỗi khi đồng bộ. Thử lại sau nhé."))


async def _authenticate(websocket: WebSocket) -> tuple[str, str, str] | int:
    """Đợi lời gọi xác thực trong ``AUTH_TIMEOUT_SECONDS``. Trả (owner, tên lời gọi, invokeId), hoặc mã đóng:
    ``CLOSE_TRY_AGAIN_LATER`` khi quá hạn hay trình duyệt rời đi, ``CLOSE_UNAUTHORIZED`` khi mã sai, khung quá lớn hay
    có lời gọi khác trước.

    Bỏ qua vài khung không phải lời gọi đến trước: eventa gửi sự kiện "đã kết nối" của chính nó khi ngữ cảnh được dựng
    trước lúc socket mở (trình duyệt AIRI dựng sau nên không gửi, một client eventa khác thì có thể)."""
    deadline = asyncio.get_running_loop().time() + AUTH_TIMEOUT_SECONDS
    for _ in range(MAX_PRE_AUTH_FRAMES):
        try:
            async with asyncio.timeout_at(deadline):
                message = await websocket.receive()
        except (TimeoutError, WebSocketDisconnect, RuntimeError):
            # Quá hạn hay trình duyệt rời đi: thử lại được (như máy chủ AIRI). 4001 ở đây làm trình duyệt ngừng hẳn việc
            # tự kết nối lại tới khi tải lại trang, và tin chỉ nằm chờ trên máy đó (chủ web gặp ngày 17–18/11/2026).
            return CLOSE_TRY_AGAIN_LATER
        if message.get("type") == "websocket.disconnect":
            return CLOSE_TRY_AGAIN_LATER
        text = message.get("text")
        if not isinstance(text, str) or len(text) > MAX_AUTH_FRAME_BYTES:
            return CLOSE_UNAUTHORIZED
        request = parse_request(text)
        if request is None:
            continue
        name, invoke_id, content = request
        if name != "chat:authenticate":
            return CLOSE_UNAUTHORIZED
        owner = await live_token_owner(content.get("token") if isinstance(content, dict) else None)
        return (owner, name, invoke_id) if owner else CLOSE_UNAUTHORIZED
    return CLOSE_UNAUTHORIZED


@router.websocket(PREFIX + "/ws/v2/chat")
async def chat_socket(websocket: WebSocket):
    global _unauthenticated
    if not _enabled() or _unauthenticated >= MAX_UNAUTHENTICATED_SOCKETS:
        await websocket.close(code=CLOSE_TRY_AGAIN_LATER if _enabled() else CLOSE_UNAUTHORIZED)
        return
    await websocket.accept()
    _unauthenticated += 1
    try:
        auth = await _authenticate(websocket)
    finally:
        _unauthenticated -= 1
    if isinstance(auth, int):
        await _close(websocket, auth, "unauthorized" if auth == CLOSE_UNAUTHORIZED else "authentication timeout")
        return
    owner, name, invoke_id = auth
    peers = _peers.setdefault(owner, {})
    if len(peers) >= MAX_SOCKETS_PER_OWNER:
        await _close(websocket, CLOSE_TRY_AGAIN_LATER, "too many connections")
        return
    user_id = await sync_user_id(owner)
    peer = _Peer(websocket)
    peers[id(peer)] = peer
    logger.info("airi_sync open sockets=%d", len(peers))
    try:
        await peer.send(reply(name, invoke_id, {"userId": user_id}))
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            text = message.get("text")
            request = parse_request(text) if isinstance(text, str) else None
            if request is not None:
                await _handle(peer, owner, user_id, *request)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        peers.pop(id(peer), None)
        if not peers:
            _peers.pop(owner, None)


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    """Đóng kết nối; trình duyệt đã tự ngắt trước (ví dụ AIRI đóng khi chưa có mã) thì thôi, không ghi lỗi."""
    try:
        await websocket.close(code=code, reason=reason)
    except (RuntimeError, WebSocketDisconnect):
        pass

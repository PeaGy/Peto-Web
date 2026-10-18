"""Peto Agent: đăng nhập CLI bằng mã thiết bị và gọi mô hình từng bước cho CLI trên máy người dùng.

CLI giữ vòng lặp và chạy công cụ ngay trên máy người dùng. Máy chủ chỉ:
- cấp token cho từng máy khi người dùng bấm Cho phép trên web, và chỉ lưu mã băm của token;
- đếm số bước mỗi ngày cho mỗi tài khoản, giới hạn riêng của agent theo yêu cầu chủ web;
- gọi mô hình bằng token xAI của máy chủ, không bao giờ gửi token đó xuống CLI.

Mã thiết bị đang chờ nằm trong RAM như hàng chờ giọng nói, nên backend chạy
một tiến trình; khởi động lại giữa lúc đăng nhập thì CLI phải chạy lại lệnh login.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai import models as ai_models
from features.accounts import auth
import storage as db
from features.agent.install import cli_version
from features.agent.tools import FEATURES, explore_schemas, tool_schemas
from ai.agent import agent_step
from shared.attachments import sniff_image_mime
from ai.base import ProviderError
from shared.time_tools import agent_time_context, resolve_timezone
from core import usage_events
from core.config import AGENT_DAILY_STEPS, AGENT_MODEL, AGENT_MAX_CONCURRENT, AGENT_MAX_QUEUE, AGENT_MAX_REQUEST_BYTES, AGENT_REASONING, AGENT_SLOW_STEP_SECONDS, AGENT_STEP_TIMEOUT_SECONDS, AGENT_TOKEN_IDLE_DAYS, AGENT_WEB_SEARCH, provider_from_owner
from prompts import agent as agent_prompts
from prompts.core import CORE_PROMPT
from prompts.providers import provider_prompt
from core.rate_limit import Admission, AdmissionDenied

logger = logging.getLogger("peto_web.agent")
router = APIRouter(prefix="/api/agent", tags=["agent"])

CODE_NOT_FOUND = "Mã kết nối không đúng hoặc đã hết hạn. Chạy lại peto login để lấy mã mới."
CODE_TTL_SECONDS = 600
POLL_INTERVAL_SECONDS = 3
MAX_PENDING_CODES = 50
MAX_ITEMS = 300
# web_search_call là mục do chính dịch vụ AI sinh ra khi tìm web; CLI gửi lại nguyên văn để hội thoại không hụt mục.
ALLOWED_ITEM_TYPES = {"message", "function_call", "function_call_output", "reasoning", "web_search_call"}
# Ảnh CLI dán kèm tin (Alt+V, kéo thả). CLI giữ 4 ảnh gần nhất và thu nhỏ mỗi ảnh dưới 2 MB; máy chủ nới hơn một chút.
MAX_STEP_IMAGES = 8
MAX_STEP_IMAGE_BYTES = 3 * 1024 * 1024
STEP_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
BAD_IMAGE = "Ảnh gửi kèm không hợp lệ. Peto nhận ảnh PNG, JPEG, GIF hoặc WebP."
# Mức suy nghĩ CLI chọn bằng /effort. Mức cao tốn nhiều token hơn nên tính 2 bước, theo quyết định của chủ web.
STEP_COST = {"none": 1, "low": 1, "medium": 1, "high": 2, "xhigh": 2, "max": 2}
# Bỏ các ký tự dễ đọc nhầm như O/0 và I/1.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Hàng chờ riêng: một tác vụ agent nhiều bước không được chiếm suất chạy của chat.
admission = Admission(max_concurrent=AGENT_MAX_CONCURRENT, max_queue=AGENT_MAX_QUEUE, cooldown=0)
# device_code -> {user_code, name, expires_at, status: pending|approved|denied, owner}
pending_codes: dict[str, dict] = {}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _today() -> str:
    return datetime.now(ZoneInfo(resolve_timezone())).date().isoformat()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _purge_codes() -> None:
    now = time.monotonic()
    for code in [code for code, entry in pending_codes.items() if entry["expires_at"] <= now]:
        del pending_codes[code]


def _new_user_code() -> str:
    while True:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        code = f"{raw[:4]}-{raw[4:]}"
        if all(entry["user_code"] != code for entry in pending_codes.values()):
            return code


def _find_pending(user_code: str) -> dict | None:
    _purge_codes()
    compact = "".join(char for char in user_code.upper() if char.isalnum())
    if len(compact) != 8:
        return None
    code = f"{compact[:4]}-{compact[4:]}"
    return next(
        (entry for entry in pending_codes.values() if entry["user_code"] == code and entry["status"] == "pending"),
        None,
    )


def _clean_name(value: str) -> str:
    name = " ".join("".join(char if char.isprintable() else " " for char in value).split())
    return name[:60] or "Máy chưa đặt tên"


def _account_name(user: dict | None) -> str:
    if not user:
        return "tài khoản của bạn"
    return user.get("display_name") or user.get("username") or "tài khoản của bạn"


async def web_owner(owner: str = Depends(auth.current_owner)) -> str:
    """Dependency cho các thao tác trên web: đã đăng nhập."""
    return owner


async def device_auth(request: Request) -> dict:
    """Dependency cho CLI: token Bearer còn hiệu lực."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Máy này chưa đăng nhập Peto Agent. Chạy peto login.")
    device = await db.find_agent_device(_hash(token), idle_seconds=AGENT_TOKEN_IDLE_DAYS * 86400)
    if not device:
        raise HTTPException(
            status_code=401,
            detail="Phiên Peto Agent đã hết hạn hoặc máy đã bị ngắt kết nối. Chạy peto login để đăng nhập lại.",
        )
    # Token của khóa không còn hợp lệ (tài khoản khách cũ, đã bỏ) coi như đã thu hồi.
    if not provider_from_owner(device["owner"]):
        raise HTTPException(status_code=401, detail="Phiên Peto Agent đã hết hạn. Chạy peto login để đăng nhập lại.")
    # Chỉ ghi lần dùng cuối khi đã cách hơn một phút, đỡ ghi SQLite ở mỗi bước.
    if time.time() - device["last_used_at"] > 60:
        await db.touch_agent_device(device["owner"], device["id"])
    return device


# --- Mã thiết bị -----------------------------------------------------------
# Hai route có đường dẫn cố định phải khai trước /device/{user_code}, không thì "start" và "token" bị hiểu là mã.

class DeviceStart(BaseModel):
    name: str = Field(default="", max_length=200)


class DeviceToken(BaseModel):
    device_code: str = Field(min_length=16, max_length=200)


class DeviceAnswer(BaseModel):
    allow: bool


@router.post("/device/start")
async def device_start(body: DeviceStart) -> dict:
    _purge_codes()
    if len(pending_codes) >= MAX_PENDING_CODES:
        raise HTTPException(status_code=429, detail="Đang có quá nhiều yêu cầu kết nối. Thử lại sau vài phút nhé.")
    device_code = secrets.token_urlsafe(32)
    user_code = _new_user_code()
    pending_codes[device_code] = {
        "user_code": user_code,
        "name": _clean_name(body.name),
        "expires_at": time.monotonic() + CODE_TTL_SECONDS,
        "status": "pending",
        "owner": None,
    }
    # Chỉ trả liên kết khi PETO_FRONTEND_URL là địa chỉ tuyệt đối; không thì CLI tự ghép từ địa chỉ máy chủ.
    link = auth._frontend_url(agent_code=user_code)
    return {
        "device_code": device_code,
        "user_code": user_code,
        "verification_url": link if link.startswith(("http://", "https://")) else None,
        "expires_in": CODE_TTL_SECONDS,
        "interval": POLL_INTERVAL_SECONDS,
    }


@router.post("/device/token")
async def device_token(body: DeviceToken) -> dict:
    _purge_codes()
    entry = pending_codes.get(body.device_code)
    if not entry:
        raise HTTPException(status_code=410, detail="Mã kết nối đã hết hạn. Chạy lại peto login nhé.")
    if entry["status"] == "pending":
        raise HTTPException(status_code=428, detail="Đang chờ bạn bấm Cho phép trên web.")
    # Token chỉ cấp đúng một lần: lấy xong là mã biến mất.
    del pending_codes[body.device_code]
    owner = entry["owner"]
    if entry["status"] != "approved" or not owner:
        raise HTTPException(status_code=403, detail="Kết nối đã bị từ chối trên web.")
    token = "peto_" + secrets.token_urlsafe(32)
    device = await db.create_agent_device(owner=owner, name=entry["name"], token_hash=_hash(token))
    return {
        "token": token,
        "device_id": device["id"],
        "device_name": device["name"],
        "account": _account_name(await db.get_user(owner)),
    }


@router.get("/device/{user_code}")
async def device_info(user_code: str, owner: str = Depends(web_owner)) -> dict:
    entry = _find_pending(user_code)
    if not entry:
        raise HTTPException(status_code=404, detail=CODE_NOT_FOUND)
    return {
        "user_code": entry["user_code"],
        "name": entry["name"],
        "expires_in": max(0, int(entry["expires_at"] - time.monotonic())),
    }


@router.post("/device/{user_code}")
async def device_answer(user_code: str, body: DeviceAnswer, owner: str = Depends(web_owner)) -> dict:
    entry = _find_pending(user_code)
    if not entry:
        raise HTTPException(status_code=404, detail=CODE_NOT_FOUND)
    entry["status"] = "approved" if body.allow else "denied"
    entry["owner"] = owner if body.allow else None
    return {"allowed": body.allow, "name": entry["name"]}


# --- Quản lý máy trên web -------------------------------------------------

@router.get("/devices")
async def list_devices(owner: str = Depends(web_owner)) -> dict:
    return {
        "devices": await db.list_agent_devices(owner),
        "steps_used": await db.get_agent_steps(owner, _today()),
        "steps_limit": AGENT_DAILY_STEPS,
    }


@router.delete("/devices/{device_id}")
async def revoke_device(device_id: str, owner: str = Depends(web_owner)) -> dict:
    if not await db.revoke_agent_device(owner, device_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy máy này.")
    return {"revoked": True}


# --- Dành cho CLI ----------------------------------------------------------

@router.get("/me")
async def me(device: dict = Depends(device_auth)) -> dict:
    owner = device["owner"]
    usage = await db.get_agent_usage(owner, _today())
    return {
        "account": _account_name(await db.get_user(owner)),
        "device_name": device["name"],
        "steps_used": usage["steps"],
        "steps_limit": AGENT_DAILY_STEPS,
        # Tổng token cả ngày, tính cả phần hội thoại gửi lại ở mỗi bước: đúng lượng dịch vụ AI tính.
        "tokens_used": usage["input_tokens"] + usage["output_tokens"],
        # CLI dùng mức này khi người dùng chưa chọn bằng /effort.
        "default_effort": AGENT_REASONING,
        # Bản peto máy chủ đang phát; CLI cũ hơn thì nhắc chạy lại lệnh cài.
        "cli_version": cli_version(),
        # Model tài khoản này chọn được bằng /model, kèm số bước mỗi lần gọi (trước khi nhân mức suy nghĩ).
        "models": ai_models.public(ai_models.usable(owner, "agent")),
        # Khả năng máy chủ hiểu: CLI chỉ khai báo khả năng mới khi máy chủ có trong danh sách, để CLI mới gặp máy chủ
        # chưa cập nhật vẫn chạy như cũ (kết quả công cụ do CLI dựng phải khớp mô tả do máy chủ gửi).
        "agent_features": sorted(FEATURES),
    }


@router.post("/logout")
async def logout(device: dict = Depends(device_auth)) -> dict:
    await db.revoke_agent_device(device["owner"], device["id"])
    return {"revoked": True}


async def _read_body(request: Request) -> bytes:
    too_large = HTTPException(
        status_code=413,
        detail="Bước gửi lên quá lớn. Gõ /new (bản cũ: /moi) để bắt đầu hội thoại mới, hoặc đọc ít tệp và gửi ít ảnh hơn mỗi lần.",
    )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > AGENT_MAX_REQUEST_BYTES:
        raise too_large
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > AGENT_MAX_REQUEST_BYTES:
            raise too_large
    return bytes(body)


def _check_image(part: dict) -> None:
    """Ảnh chỉ nhận dạng data URL đúng loại: không nhận địa chỉ web, để dịch vụ AI không phải tải gì theo lệnh của CLI."""
    url = part.get("image_url")
    if set(part) - {"type", "image_url", "detail"} or part.get("detail", "auto") not in {"auto", "low", "high"}:
        raise HTTPException(status_code=400, detail=BAD_IMAGE)
    if not isinstance(url, str) or not url.startswith("data:"):
        raise HTTPException(status_code=400, detail=BAD_IMAGE)
    header, separator, encoded = url.partition(",")
    mime = header[len("data:"):].removesuffix(";base64")
    if not separator or not header.endswith(";base64") or mime not in STEP_IMAGE_MIMES:
        raise HTTPException(status_code=400, detail=BAD_IMAGE)
    if len(encoded) // 4 * 3 > MAX_STEP_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"Mỗi ảnh gửi kèm tối đa {MAX_STEP_IMAGE_BYTES // 1024 // 1024} MB.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail=BAD_IMAGE) from None
    if sniff_image_mime(data) != mime:
        raise HTTPException(status_code=400, detail=BAD_IMAGE)


def _count_images(content) -> int:
    """Kiểm nội dung tin của người dùng: chữ, hoặc danh sách phần chữ và ảnh. Trả số ảnh."""
    if isinstance(content, str):
        return 0
    if not isinstance(content, list):
        raise HTTPException(status_code=400, detail="Tin của người dùng không đúng định dạng.")
    images = 0
    for part in content:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind == "input_text" and isinstance(part.get("text"), str):
            continue
        if kind != "input_image":
            raise HTTPException(status_code=400, detail="Tin của người dùng chỉ được có chữ và ảnh.")
        _check_image(part)
        images += 1
    return images


def _parse_step(raw: bytes) -> tuple[list[dict], dict, str]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Dữ liệu bước gửi lên không phải JSON hợp lệ.") from None
    items = payload.get("input") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="Bước gửi lên chưa có nội dung.")
    if len(items) > MAX_ITEMS:
        raise HTTPException(status_code=400, detail=f"Hội thoại đã quá {MAX_ITEMS} mục. Gõ /new (bản cũ: /moi) để bắt đầu hội thoại mới nhé.")
    images = 0
    for item in items:
        kind = item.get("type", "message") if isinstance(item, dict) else None
        if kind not in ALLOWED_ITEM_TYPES:
            raise HTTPException(status_code=400, detail="Bước gửi lên có mục không hợp lệ.")
        # Chỉ dẫn hệ thống do máy chủ viết; CLI không được chèn vai system hay developer.
        if kind == "message" and item.get("role") not in {"user", "assistant"}:
            raise HTTPException(status_code=400, detail="Chỉ nhận tin của người dùng hoặc của Peto trong bước gửi lên.")
        if kind == "message" and item.get("role") == "user":
            images += _count_images(item.get("content"))
    if images > MAX_STEP_IMAGES:
        raise HTTPException(status_code=400, detail=f"Mỗi bước gửi kèm tối đa {MAX_STEP_IMAGES} ảnh. Gõ /new (bản cũ: /moi) để bắt đầu "
                                                    "hội thoại mới nhé.")
    # CLI cũ không gửi mức suy nghĩ thì dùng mức mặc định của máy chủ.
    effort = payload.get("effort") or AGENT_REASONING
    if not isinstance(effort, str) or effort not in STEP_COST:
        raise HTTPException(status_code=400, detail="Mức suy nghĩ không hợp lệ.")
    context = payload.get("context")
    # CLI cũ không gửi model thì dùng Peto.
    model = payload.get("model") or ai_models.DEFAULT_MODEL
    return items, context if isinstance(context, dict) else {}, effort, model


def _features(context: dict) -> frozenset[str]:
    """Khả năng CLI khai báo, ví dụ "cwd". CLI cũ không gửi gì nên nhận schema cũ; tên lạ thì bỏ qua."""
    value = context.get("features")
    if not isinstance(value, list) or len(value) > 32:
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str) and item in FEATURES)


def _patch_model(model: str) -> bool:
    """GPT (Luna, Terra, Sol) sửa tệp bằng apply_patch khi CLI hiểu nó, như opencode (CLI 0.21.0)."""
    found = ai_models.MODELS.get(model)
    return found is not None and found.service == "openai"


# Lượt đặc biệt của CLI: tóm tắt hội thoại (purpose "compact"), đặt tên hội thoại cho /resume (purpose "title", CLI
# 0.21.0) và câu hỏi bên lề /btw (purpose "btw", CLI 0.23.0). Cả ba không có công cụ, kể cả tìm web. "wrapup" (CLI
# 0.25.0, theo opencode) là lượt cuối khi yêu cầu đã hết bước: chỉ dẫn như bước thường cộng WRAPUP_PROMPT, cấm gọi
# công cụ (agent_step final).
SPECIAL_PURPOSES = {"compact", "title", "btw", "wrapup"}
NO_TOOL_PURPOSES = {"compact", "title", "btw"}
# AGENTS.md chung của người dùng (khả năng "user_guide"): CLI giới hạn 32.000 ký tự, máy chủ chặn thêm ở đây.
MAX_USER_GUIDANCE_CHARS = 40000


def _guide_text(context: dict, *, scope: bool) -> str:
    """AGENTS.md của dự án do CLI gửi lên, mỗi tệp kèm đường dẫn (và phạm vi). Rỗng khi danh sách không hợp lệ."""
    guidance = context.get("project_guidance", [])
    text = ""
    if isinstance(guidance, list) and len(guidance) <= 64:
        for item in guidance:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                where = str(item.get("path", ""))[:1024]
                if scope:
                    where += f" · scope: {str(item.get('scope', ''))[:1024]}"
                text += f"\nFile: {where}\n{item['text']}\n"
    return text


def _explore_instructions(context: dict, web_search: bool, model: str, *, final: bool) -> str:
    """Agent con explore (CLI 0.27.0): phần lõi Peto, lời nhắc chỉ tìm và đọc, hướng dẫn của dự án và người dùng, giờ.
    Không có chỉ dẫn làm việc của Agent (sửa tệp, chạy lệnh, danh sách việc)."""
    features = _features(context)
    guide_text = _guide_text(context, scope=False)
    if len(guide_text) > 40000:
        guide_text = ""
    parts = [CORE_PROMPT, provider_prompt(model), agent_prompts.EXPLORE_PROMPT,
             agent_prompts.AGENT_EXPLORE_PROMPT if "explore_v2" in features else "",
             agent_prompts.AGENT_SEARCH_PROMPT if web_search else agent_prompts.AGENT_NO_SEARCH_PROMPT,
             f"## User machine\nProject: {str(context.get('project') or '')[:80]}.", _user_guidance(context, features),
             agent_prompts.PROJECT_GUIDANCE_PROMPT + guide_text if guide_text else "",
             agent_prompts.EXPLORE_FINAL_PROMPT if final else "", agent_time_context()]
    return "\n\n".join(part for part in parts if part)


def _btw_instructions(model: str) -> str:
    """/btw: vẫn là Peto (lõi trợ lý, không nêu model phía sau), cộng lời nhắc câu hỏi bên lề và giờ hiện tại."""
    return "\n\n".join(part for part in (CORE_PROMPT, provider_prompt(model),
                                           agent_prompts.BTW_PROMPT, agent_time_context()) if part)


def _user_guidance(context: dict, features: frozenset[str]) -> str:
    """AGENTS.md chung trong hồ sơ người dùng (CLI 0.25.0), bọc riêng để không lẫn với hướng dẫn của dự án."""
    text = context.get("user_guidance")
    if "user_guide" not in features or not isinstance(text, str) or not text.strip():
        return ""
    if len(text) > MAX_USER_GUIDANCE_CHARS:
        return "The user's general guidance is too long; ask them to shorten it."
    return agent_prompts.USER_GUIDANCE_PROMPT + text.strip()


def _check_observations(context: dict, features: frozenset[str]) -> str:
    """Các lần kiểm tra CLI đã ghi nhận; chỉ là dữ liệu, không tự kết luận yêu cầu đã đạt."""
    value = context.get("check_observations")
    if "recall" not in features or not isinstance(value, dict):
        return ""
    cleaned = {}
    if type(value.get("current_revision")) is int and value["current_revision"] >= 0:
        cleaned["current_revision"] = value["current_revision"]
    for key, fields in (("observations", ("tool", "call_id", "revision", "classification", "exit_code")),
                        ("recent_commands", ("command", "exit_code", "classification", "error"))):
        rows = value.get(key)
        if isinstance(rows, list):
            cleaned[key] = [{field: (row[field][:1200] if isinstance(row[field], str) else row[field])
                             for field in fields if field in row and (row[field] is None or
                                 type(row[field]) in {str, int, bool})}
                            for row in rows[-8:] if isinstance(row, dict)]
    if not cleaned.get("observations") and not cleaned.get("recent_commands"):
        return ""
    return ("## Local check observations (historical data, not completion or permission)\n"
            + json.dumps(cleaned, ensure_ascii=False))


def _instructions(context: dict, web_search: bool, model: str = "peto", *, extra: str = "") -> str:
    """Chỉ dẫn của một bước Agent, bằng tiếng Anh với mọi model (chủ web chọn ngày 2026-10-15 để bớt token; câu trả lời
    vẫn theo ngôn ngữ người dùng). ``extra`` (lượt "wrapup") đứng ngay trước mốc thời gian, để phần đầu giống hệt các
    bước trước và prompt cache vẫn dùng lại được."""
    def short(value) -> str:
        return " ".join(str(value or "").split())[:80] or "unknown"

    guide_text = _guide_text(context, scope=True)
    if len(guide_text) > 40000:
        guide_text = "Project guidance is too long; ask the user to shorten it before editing."
    features = _features(context)
    skill_context = ""
    if "skills" in features:
        catalog = context.get("skills")
        if isinstance(catalog, list):
            catalog = [{key: str(item.get(key, ""))[:limit] for key, limit in
                        (("name", 64), ("description", 400), ("path", 256))}
                       for item in catalog[:32] if isinstance(item, dict)]
            skill_context = agent_prompts.SKILLS_PROMPT.format(catalog=json.dumps(catalog, ensure_ascii=False))
    mcp_context = ""
    if "mcp" in features and isinstance(context.get("mcp_servers"), list):
        servers = [{"name": str(item.get("name", ""))[:64]} for item in context["mcp_servers"][:16] if isinstance(item, dict)]
        mcp_context = agent_prompts.MCP_PROMPT.format(servers=json.dumps(servers, ensure_ascii=False))
    tooling = []
    if "explore_v2" in features:
        tooling.append(agent_prompts.AGENT_EXPLORE_PROMPT)
    if "edit_v2" in features:
        tooling.append(agent_prompts.AGENT_EDIT_PROMPT)
    if "patch" in features and _patch_model(model):
        tooling.append(agent_prompts.AGENT_PATCH_PROMPT)
    if "question" in features:
        tooling.append(agent_prompts.AGENT_QUESTION_PROMPT)
    if "output_files" in features:
        tooling.append(agent_prompts.AGENT_OUTPUT_PROMPT)
    if "subagent" in features:
        tooling.append(agent_prompts.AGENT_SUBAGENT_PROMPT)
    if "recall" in features:
        tooling.append(agent_prompts.AGENT_RECALL_PROMPT)
    if inbox := agent_prompts.agent_inbox_prompt(features):
        tooling.append(inbox)
    browsing = ""
    if "browser" in features:
        browsing = agent_prompts.browser_prompt(act="browser_act" in features, outside="browser_outside" in features)
    # Mốc thời gian (làm tròn theo giờ) đứng cuối: phần trước nó giống hệt nhau giữa các bước, nên prompt caching đọc
    # lại được cả phần chỉ dẫn lẫn lịch sử hội thoại thay vì tính tiền đầy đủ mỗi bước.
    return "\n\n".join(part for part in (
        CORE_PROMPT,
        agent_prompts.agent_prompt(plan=not _patch_model(model), read_more="read_more" in features),
        provider_prompt(model), *tooling, browsing,
        skill_context, mcp_context,
        agent_prompts.AGENT_SEARCH_PROMPT if web_search else agent_prompts.AGENT_NO_SEARCH_PROMPT,
        f"## User machine\nProject: {short(context.get('project'))}. OS: {short(context.get('os'))}.",
        _user_guidance(context, features), agent_prompts.PROJECT_GUIDANCE_PROMPT + guide_text,
        _check_observations(context, features), extra,
        agent_time_context(),
    ) if part)


@router.post("/step")
async def step(request: Request, device: dict = Depends(device_auth)):
    items, context, effort, model_key = _parse_step(await _read_body(request))
    owner = device["owner"]
    try:
        model = ai_models.resolve(owner, model_key, "agent")
    except ai_models.ModelUnavailable as err:
        raise HTTPException(status_code=err.status, detail=err.message) from None
    if effort not in ai_models.supported_efforts(model.key):
        raise HTTPException(status_code=400, detail="Model này không hỗ trợ mức suy nghĩ đã chọn.")
    day = _today()
    # Chủ web chọn tính bước theo giá: model đắt tính nhiều bước hơn, nhân với mức suy nghĩ.
    cost = STEP_COST[effort] * model.step_cost
    used = await db.take_agent_step(owner, day, AGENT_DAILY_STEPS, cost)
    if used is None:
        left = max(0, AGENT_DAILY_STEPS - await db.get_agent_steps(owner, day))
        if 0 < left < cost:
            detail = (f"Mỗi bước {model.label} ở mức suy nghĩ này tính {cost} bước, nhưng hôm nay chỉ còn {left} bước. "
                      "Gõ /effort medium hoặc /model peto để dùng nốt.")
        else:
            detail = f"Hôm nay tài khoản của bạn đã dùng hết {AGENT_DAILY_STEPS} bước Peto Agent. Lượt mới bắt đầu lúc 0 giờ."
        raise HTTPException(status_code=429, detail=detail)
    special = context.get("purpose") if context.get("purpose") in SPECIAL_PURPOSES else None
    # Agent con explore (CLI 0.27.0): công cụ chỉ đọc; lượt cuối ("final") không được gọi công cụ.
    exploring = context.get("purpose") == "explore" and "subagent" in _features(context)
    final = special == "wrapup" or (exploring and context.get("final") is True)
    no_tools = special in NO_TOOL_PURPOSES
    # Tóm tắt, đặt tên và /btw không cần công cụ nào, kể cả tìm web: chỉ đọc lại lịch sử rồi viết.
    searching = AGENT_WEB_SEARCH and special is None
    if special == "compact":
        instructions = agent_prompts.COMPACT_PROMPT
    elif special == "title":
        instructions = agent_prompts.TITLE_PROMPT
    elif special == "btw":
        instructions = _btw_instructions(model.key)
    elif exploring:
        instructions = _explore_instructions(context, searching, model.key, final=final)
    elif special == "wrapup":
        # Giữ nguyên phần chỉ dẫn của các bước trước (cả câu về tìm web) để prompt cache dùng lại được; agent_step final
        # mới là chỗ cấm công cụ.
        instructions = _instructions(context, AGENT_WEB_SEARCH, model.key,
                                     extra=agent_prompts.WRAPUP_PROMPT)
    else:
        instructions = _instructions(context, searching, model.key)
    usage_purpose = {"compact": "compact", "title": "side", "btw": "side"}.get(special or "", "agent")

    async def event_stream() -> AsyncIterator[str]:
        failure: str | None = None
        # Lỗi tạm thời mà bước chưa có phản hồi (đã được hoàn lại): CLI 0.25.0 tự thử lại, không tốn bước.
        retryable = False
        produced = False
        completed = False
        outcome = "cancelled"
        started = time.monotonic()
        first_at: float | None = None
        try:
            yield _sse({"type": "meta", "steps_used": used, "steps_limit": AGENT_DAILY_STEPS})
            async with admission.slot(f"agent:{owner}"):
                async with asyncio.timeout(AGENT_STEP_TIMEOUT_SECONDS):
                    async for event in agent_step(instructions=instructions, input_items=items,
                                                  tools=[] if no_tools else
                                                  explore_schemas(_features(context)) if exploring else tool_schemas(
                                                      _features(context), patch_model=_patch_model(model.key)),
                                                  effort=effort, model=model.key, web_search=searching,
                                                  final=final):
                        if not produced:
                            first_at = time.monotonic()
                        produced = True
                        if event.kind == "done":
                            with anyio.CancelScope(shield=True):
                                await db.add_agent_tokens(
                                    owner, day, event.usage.get("input_tokens", 0), event.usage.get("output_tokens", 0)
                                )
                            completed = True
                            outcome = "complete"
                            usage_events.record(
                                "call", service=model.service, model=model.key, slug=model.slug or AGENT_MODEL,
                                surface="agent", purpose=usage_purpose, complete=True,
                                elapsed_ms=round((time.monotonic() - started) * 1000),
                                input_tokens=event.usage.get("input_tokens"), output_tokens=event.usage.get("output_tokens"),
                                cached_tokens=event.usage.get("cached_tokens"),
                                cache_write_tokens=event.usage.get("cache_write_tokens"),
                            )
                            purpose = special or ("explore" if exploring else None)
                            yield _sse({"type": "done", "output": list(event.output), "usage": event.usage,
                                        **({"purpose": purpose} if purpose else {})})
                        else:
                            yield _sse({"type": event.kind, "text": event.text})
                    if not completed:
                        outcome = "empty"
        except AdmissionDenied as denied:
            outcome = denied.reason
            retryable = denied.reason == "queue_full"
            failure = ("Peto Agent đang bận với nhiều người, thử lại sau chút nhé." if denied.reason == "queue_full"
                       else "Đợi lâu quá nên Peto bỏ bước này. Thử lại nhé.")
        except ProviderError as err:
            outcome = "provider_error"
            retryable = err.retryable
            logger.warning("Bước agent lỗi từ nhà cung cấp: %s", err)
            failure = str(err)
        except TimeoutError:
            outcome = "timeout"
            failure = "Bước này chạy quá lâu nên Peto dừng lại. Thử lại nhé."
        except Exception:
            outcome = "internal_error"
            logger.exception("Lỗi không mong đợi ở bước agent")
            failure = "Có lỗi ở phía máy chủ. Thử lại sau nhé."
        finally:
            # Mô hình chưa kịp phản hồi gì thì trả lại bước, người dùng không mất lượt oan.
            if failure and not produced:
                with anyio.CancelScope(shield=True):
                    await db.refund_agent_step(owner, day, cost)
            # Một bước chậm có thể do dịch vụ AI lâu mới trả lời, hoặc do SDK lặng lẽ gửi lại sau lỗi (móc HTTP trong
            # ai/agent.py ghi riêng mã lỗi đó). Tách thời gian chờ chữ đầu ra khỏi tổng thời gian để phân biệt.
            elapsed = time.monotonic() - started
            logger.info("agent_timing model=%s effort=%s mode=agent first_text_ms=%s total_ms=%d complete=%s outcome=%s",
                        model.key, effort, round((first_at - started) * 1000) if first_at is not None else None,
                        round(elapsed * 1000), completed, outcome)
            usage_events.record(
                "turn", service=model.service, model=model.key, slug=model.slug or AGENT_MODEL, surface="agent",
                purpose=usage_purpose, outcome=outcome, complete=completed,
                elapsed_ms=round(elapsed * 1000),
                first_text_ms=round((first_at - started) * 1000) if first_at is not None else None,
            )
            if elapsed >= AGENT_SLOW_STEP_SECONDS:
                logger.warning("Bước agent chậm: model %s · mức %s · %d mục vào · chờ phản hồi đầu %.1fs · tổng "
                               "%.1fs%s", model.key, effort, len(items),
                               (first_at - started) if first_at else elapsed, elapsed,
                               f" · kết thúc bằng lỗi: {failure}" if failure else "")
        if failure:
            yield _sse({"type": "error", "message": failure, **({"retryable": True} if retryable and not produced else {})})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

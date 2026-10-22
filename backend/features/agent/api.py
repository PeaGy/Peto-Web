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
from features.agent import assembly, budget
from ai.agent import agent_step
from shared.attachments import sniff_image_mime
from ai.base import ProviderError
from shared.time_tools import agent_time_context, resolve_timezone
from core import usage_events
from core.config import AGENT_DAILY_STEPS, AGENT_DISABLED_SOURCES, AGENT_MODEL, AGENT_MAX_CONCURRENT, AGENT_MAX_QUEUE, AGENT_MAX_REQUEST_BYTES, AGENT_REASONING, AGENT_SLOW_STEP_SECONDS, AGENT_STEP_TIMEOUT_SECONDS, AGENT_TOKEN_IDLE_DAYS, AGENT_WEB_SEARCH, provider_from_owner
from prompts import agent as agent_prompts  # noqa: F401 - test và module khác lấy qua đây
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
        "models": [{**row, "context_limits": budget.limits(row["key"])}
                   for row in ai_models.public(ai_models.usable(owner, "agent"))],
        # Khả năng máy chủ hiểu: CLI chỉ khai báo khả năng mới khi máy chủ có trong danh sách, để CLI mới gặp máy chủ
        # chưa cập nhật vẫn chạy như cũ (kết quả công cụ do CLI dựng phải khớp mô tả do máy chủ gửi).
        "agent_features": sorted(FEATURES),
        "context_transport": {"max_items": MAX_ITEMS, "max_request_bytes": AGENT_MAX_REQUEST_BYTES},
        # Nguồn trực tiếp chủ web đang tạm tắt (PETO_AGENT_DISABLED_SOURCES); CLI ẩn model của chúng khi mở phiên.
        "disabled_sources": list(AGENT_DISABLED_SOURCES),
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
    return assembly.features(context)


def _service(model: str) -> str:
    return ai_models.MODELS[model].service


def _patch_model(model: str) -> bool:
    """GPT (Luna, Terra, Sol) sửa tệp bằng apply_patch khi CLI hiểu nó, như opencode (CLI 0.21.0)."""
    found = ai_models.MODELS.get(model)
    return found is not None and assembly.patch_service(found.service)


# Ghép chỉ dẫn nằm ở features/agent/assembly.py (thuần, dùng chung với CLI qua peto_agent/bundle). Các hàm dưới chỉ đưa
# vào dịch vụ của model và mốc thời gian của máy chủ.
SPECIAL_PURPOSES = assembly.SPECIAL_PURPOSES
NO_TOOL_PURPOSES = assembly.NO_TOOL_PURPOSES
MAX_USER_GUIDANCE_CHARS = assembly.MAX_USER_GUIDANCE_CHARS
_guide_text = assembly.guide_text
_user_guidance = assembly.user_guidance
_check_observations = assembly.check_observations
_task_state = assembly.task_state


def _explore_instructions(context: dict, web_search: bool, model: str, *, final: bool) -> str:
    return assembly.explore_instructions(context, web_search, _service(model), final=final, clock=agent_time_context())


def _btw_instructions(model: str) -> str:
    return assembly.btw_instructions(_service(model), clock=agent_time_context())


def _instructions(context: dict, web_search: bool, model: str = "peto", *, extra: str = "") -> str:
    return assembly.work_instructions(context, web_search, _service(model), clock=agent_time_context(), extra=extra)


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
    prepared = assembly.prepare(context, service=model.service, web_search=AGENT_WEB_SEARCH,
                                clock=agent_time_context())
    special, exploring, final = prepared.special, prepared.exploring, prepared.final
    searching, instructions, step_tools = prepared.searching, prepared.instructions, prepared.tools
    usage_purpose = {"compact": "compact", "title": "side", "btw": "side"}.get(special or "", "agent")
    budgeting = "context_budget" in _features(context)

    async def event_stream() -> AsyncIterator[str]:
        failure: str | None = None
        # Lỗi tạm thời mà bước chưa có phản hồi (đã được hoàn lại): CLI 0.25.0 tự thử lại, không tốn bước.
        retryable = False
        error_code = None
        produced = False
        completed = False
        outcome = "cancelled"
        started = time.monotonic()
        first_at: float | None = None
        try:
            window = budget.request_budget(model.key, instructions, step_tools, items, compact=special == "compact",
                                           web_search=searching and not final) if budgeting else None
            yield _sse({"type": "meta", "steps_used": used, "steps_limit": AGENT_DAILY_STEPS,
                        **({"context_budget": window} if window else {})})
            if window and (window["max_output_tokens"] < 1024 or
                           (special is None and window["request_tokens"] >= window["ceiling"])):
                raise ProviderError("Ngữ cảnh đã tới ngân sách model; cần tóm tắt trước khi tiếp tục.", code="context_overflow")
            async with admission.slot(f"agent:{owner}"):
                async with asyncio.timeout(AGENT_STEP_TIMEOUT_SECONDS):
                    async for event in agent_step(instructions=instructions, input_items=items,
                                                  tools=step_tools,
                                                  effort=effort, model=model.key, web_search=searching,
                                                  final=final, **({"max_output_tokens": window["max_output_tokens"]} if window else {})):
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
                            # Chi phí là số liệu của chủ web, không gửi xuống CLI.
                            cost_ticks = event.usage.pop("cost_ticks", None)
                            usage_events.record(
                                "call", service=model.service, model=model.key, slug=model.slug or AGENT_MODEL,
                                surface="agent", purpose=usage_purpose, complete=True,
                                elapsed_ms=round((time.monotonic() - started) * 1000),
                                input_tokens=event.usage.get("input_tokens"), output_tokens=event.usage.get("output_tokens"),
                                cached_tokens=event.usage.get("cached_tokens"),
                                cache_write_tokens=event.usage.get("cache_write_tokens"), cost_ticks=cost_ticks,
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
            error_code = err.code
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
            yield _sse({"type": "error", "message": failure, **({"retryable": True} if retryable and not produced else {}),
                        **({"code": error_code} if budgeting and error_code and not produced else {})})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

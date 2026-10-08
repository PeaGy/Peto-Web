"""HTTP API cho Peto tạo ảnh — tách khỏi /api/chat."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import io
import logging
import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.routing import APIRoute
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

import storage as db
from ai.base import ProviderError
from ai.imagine import (
    ASPECT_RATIOS,
    QUALITIES,
    RESOLUTIONS,
    GeneratedImage,
    ImagineResultUncertain,
    generate_images,
)
from shared.attachments import IMAGE_MIMES, sniff_image_mime
from features.accounts.auth import current_owner
from core.config import IMAGINE_TIMEOUT_SECONDS, MAX_IMAGINE_N, MAX_IMAGINE_PROMPT_CHARS, MAX_IMAGINE_SOURCE_BYTES, UPLOAD_DIR
from core.rate_limit import AdmissionDenied, admission

MAX_SOURCE_TOTAL_BYTES = 16 * 1024 * 1024
MAX_REQUEST_BYTES = 24 * 1024 * 1024  # 16 MiB ảnh sau base64, cùng JSON và mô tả.


class ImagineRoute(APIRoute):
    """Chặn thân yêu cầu quá lớn trước khi FastAPI giải mã JSON/base64."""
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def limited(request: Request):
            if request.method == "POST" and self.path == "/api/imagine":
                declared = request.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
                    raise HTTPException(413, "Ảnh gửi lên quá lớn. Tổng ảnh tham chiếu tối đa 16 MB.")
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                        raise HTTPException(413, "Ảnh gửi lên quá lớn. Tổng ảnh tham chiếu tối đa 16 MB.")
                    body.extend(chunk)
                # Request.body() của Starlette dùng bộ đệm này; giữ nguyên kiểm tra Pydantic/OpenAPI.
                request._body = bytes(body)
            return await handler(request)

        return limited


router = APIRouter(tags=["imagine"], route_class=ImagineRoute)


class SourceImageUpload(BaseModel):
    data: str = Field(min_length=1, max_length=4 * ((MAX_IMAGINE_SOURCE_BYTES + 2) // 3))


class SourceImageReference(BaseModel):
    data: str | None = Field(default=None, min_length=1, max_length=4 * ((MAX_IMAGINE_SOURCE_BYTES + 2) // 3))
    image_id: str | None = Field(default=None, min_length=1, max_length=64)


class ImagineRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_IMAGINE_PROMPT_CHARS)
    quality: str = "low"
    resolution: str = "1k"
    aspect_ratio: str = "auto"
    n: int = Field(default=1, ge=1, le=MAX_IMAGINE_N)
    source_image: SourceImageUpload | None = None
    source_image_id: str | None = Field(default=None, min_length=1, max_length=64)
    source_images: list[SourceImageReference] | None = Field(default=None, min_length=1, max_length=5)
    background: bool = False
    request_id: str | None = Field(default=None, min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


def _check_source(data: bytes) -> GeneratedImage:
    if not data or len(data) > MAX_IMAGINE_SOURCE_BYTES:
        raise HTTPException(400, f"Ảnh gốc phải nhỏ hơn hoặc bằng {MAX_IMAGINE_SOURCE_BYTES / 1024 / 1024:g} MB.")
    mime = sniff_image_mime(data)
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(400, "Ảnh gốc không hợp lệ. Peto nhận ảnh PNG, JPEG hoặc WebP để chỉnh sửa.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 40_000_000:
                raise HTTPException(400, "Ảnh tham chiếu không được vượt quá 40 triệu điểm ảnh.")
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, "Ảnh bị hỏng hoặc không đọc được. Bạn chọn lại ảnh nhé.") from None
    return GeneratedImage(data=data, mime=mime)


async def _source_image(request: ImagineRequest, owner: str) -> GeneratedImage | None:
    if request.source_image is not None and request.source_image_id is not None:
        raise HTTPException(400, "Chỉ chọn một ảnh gốc cho mỗi lượt sửa.")
    if request.source_image is not None:
        try:
            data = base64.b64decode(request.source_image.data, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, "Không đọc được ảnh gốc. Bạn thử chọn lại ảnh nhé.") from None
        return _check_source(data)
    if request.source_image_id is not None:
        record = await db.get_imagine_image(owner, request.source_image_id)
        if not record:
            raise HTTPException(404, "Không tìm thấy ảnh gốc. Bạn chọn lại ảnh nhé.")
        try:
            # Giới hạn cả ảnh có sẵn; không đọc toàn bộ tệp quá lớn vào bộ nhớ.
            with Path(record["path"]).open("rb") as file:
                data = file.read(MAX_IMAGINE_SOURCE_BYTES + 1)
        except FileNotFoundError:
            raise HTTPException(404, "Ảnh gốc đã bị xóa. Bạn chọn lại ảnh nhé.") from None
        return _check_source(data)
    return None


async def _sources(request: ImagineRequest, owner: str) -> tuple[list[GeneratedImage], list[dict | None]]:
    if request.source_images is not None and (request.source_image is not None or request.source_image_id is not None):
        raise HTTPException(400, "Không trộn danh sách ảnh với trường ảnh gốc cũ.")
    refs = request.source_images
    if refs is None:
        refs = [SourceImageReference(data=request.source_image.data if request.source_image else None, image_id=request.source_image_id)] if request.source_image or request.source_image_id else []
    images, parents = [], []
    for ref in refs:
        if (ref.data is None) == (ref.image_id is None):
            raise HTTPException(400, "Mỗi ảnh cần dữ liệu ảnh hoặc mã ảnh trong thư viện.")
        image = await _source_image(ImagineRequest(prompt=request.prompt, source_image=SourceImageUpload(data=ref.data) if ref.data else None, source_image_id=ref.image_id), owner)
        images.append(image)
        parents.append(await db.get_imagine_image(owner, ref.image_id) if ref.image_id else None)
        if sum(len(image.data) for image in images) > MAX_SOURCE_TOTAL_BYTES:
            raise HTTPException(400, "Tổng ảnh tham chiếu không được vượt quá 16 MB.")
    return images, parents


def _public_job(row: dict) -> dict:
    all_images = row.get("images") or []
    source = next((image for image in all_images if image.get("kind") == "source"), None)
    def public_source(image: dict) -> dict:
        return {"id": image["id"], "mime": image["mime"], "url": f"/api/imagine/images/{image['id']}", "parent_image_id": image.get("parent_image_id"), "parent_job_id": image.get("parent_job_id")}
    return {
        "id": row["id"],
        "prompt": row["prompt"],
        "quality": row["quality"],
        "resolution": row["resolution"],
        "aspect_ratio": row["aspect_ratio"],
        "created_at": row["created_at"],
        "status": row.get("status", "complete"), "error": row.get("error"), "n": row.get("n", 1),
        "updated_at": row.get("updated_at"), "request_id": row.get("request_id"),
        "source_image": public_source(source) if source else None,
        "source_images": [public_source(image) for image in all_images if image.get("kind") == "source"],
        "images": [
            {
                "id": image["id"],
                "mime": image["mime"],
                "url": f"/api/imagine/images/{image['id']}",
                "liked": bool(image.get("liked")),
            }
            for image in all_images if image.get("kind", "output") == "output" and row.get("status", "complete") == "complete"
        ],
    }


def _validate(request: ImagineRequest) -> tuple[str, str, str, str, int]:
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Bạn chưa nhập mô tả ảnh.")
    quality = request.quality.strip().lower()
    resolution = request.resolution.strip().lower()
    aspect = request.aspect_ratio.strip()
    if quality not in QUALITIES:
        raise HTTPException(status_code=400, detail="Chọn chế độ Nhanh hoặc Chi tiết để tạo ảnh.")
    if resolution not in RESOLUTIONS:
        raise HTTPException(status_code=400, detail="Độ phân giải phải là 1k hoặc 2k")
    if aspect not in ASPECT_RATIOS:
        raise HTTPException(status_code=400, detail="Tỉ lệ khung hình không hợp lệ")
    return prompt, quality, resolution, aspect, int(request.n)


@router.get("/api/imagine")
async def list_jobs(owner: str = Depends(current_owner), before: str | None = Query(default=None, max_length=64)) -> dict:
    rows = await db.list_imagine_jobs(owner, before=before)
    return {"jobs": [_public_job(row) for row in rows]}


_tasks: set[asyncio.Task] = set()
_accept_lock = asyncio.Lock()
logger = logging.getLogger("peto_web.imagine")


async def shutdown_jobs() -> None:
    for task in list(_tasks):
        task.cancel()
    if _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


async def _save_images(owner: str, job_id: str, images: list[GeneratedImage], kind: str, parents: list[dict | None] | None = None) -> None:
    folder = UPLOAD_DIR / "imagine" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    for position, image in enumerate(images):
        image_id = uuid.uuid4().hex
        path = folder / f"{image_id}{IMAGE_MIMES.get(image.mime, '.jpg')}"
        parent = parents[position] if parents else None
        try:
            path.write_bytes(image.data)
            await db.add_imagine_image(image_id=image_id, job_id=job_id, owner=owner, mime=image.mime,
                                       path=str(path), kind=kind, position=position,
                                       parent_image_id=parent["id"] if parent else None,
                                       parent_job_id=parent["job_id"] if parent else None)
        except BaseException:
            path.unlink(missing_ok=True)
            raise


async def _generate(request: ImagineRequest, owner: str, sources: list[GeneratedImage]) -> list[GeneratedImage]:
    prompt, quality, resolution, aspect, n = _validate(request)
    kwargs = {"source_images": sources} if len(sources) > 1 else {"source_image": sources[0] if sources else None}
    async with admission.slot(f"imagine:{owner}"):
        async with asyncio.timeout(IMAGINE_TIMEOUT_SECONDS):
            return await generate_images(prompt=prompt, quality=quality, resolution=resolution, aspect_ratio=aspect, n=n, **kwargs)


async def _run_job(request: ImagineRequest, owner: str, job_id: str, sources: list[GeneratedImage]) -> None:
    try:
        # Đang xếp hàng cho tới khi admission cho phép gọi nhà cung cấp.
        prompt, quality, resolution, aspect, n = _validate(request)
        kwargs = {"source_images": sources} if len(sources) > 1 else {"source_image": sources[0] if sources else None}
        async with admission.slot(f"imagine:{owner}"):
            await db.update_imagine_job(owner, job_id, "running")
            async with asyncio.timeout(IMAGINE_TIMEOUT_SECONDS):
                images = await generate_images(prompt=prompt, quality=quality, resolution=resolution, aspect_ratio=aspect, n=n, **kwargs)
        await _save_images(owner, job_id, images, "output")
        await db.update_imagine_job(owner, job_id, "complete")
    except AdmissionDenied as err:
        await db.update_imagine_job(owner, job_id, "failed", err.message)
    except ImagineResultUncertain as err:
        await db.update_imagine_job(owner, job_id, "unknown", str(err))
    except ProviderError as err:
        await db.update_imagine_job(owner, job_id, "failed", str(err))
    except (TimeoutError, asyncio.CancelledError):
        await db.discard_imagine_outputs(owner, job_id)
        await db.update_imagine_job(owner, job_id, "unknown", "Chưa xác nhận được kết quả từ dịch vụ tạo ảnh. Peto không tự gửi lại lượt này.")
    except Exception:
        logger.exception("Không lưu được kết quả tạo ảnh")
        await db.discard_imagine_outputs(owner, job_id)
        await db.update_imagine_job(owner, job_id, "unknown", "Chưa lưu được kết quả. Peto không tự gửi lại lượt này để tránh tạo trùng.")


@router.post("/api/imagine")
async def create_job(request: ImagineRequest, owner: str = Depends(current_owner)):
    prompt, quality, resolution, aspect, n = _validate(request)
    if request.background:
        if not request.request_id:
            raise HTTPException(400, "Thiếu mã yêu cầu tạo ảnh.")
        fingerprint = hashlib.sha256(request.model_dump_json(exclude={"request_id", "background"}).encode()).hexdigest()
        async with _accept_lock:
            previous = await db.get_imagine_request(owner, request.request_id)
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise HTTPException(409, "Mã yêu cầu đã được dùng cho một lượt khác.")
                row = await db.get_imagine_job(owner, previous["job_id"])
                if not row:
                    raise HTTPException(410, "Lượt ảnh này đã bị xóa; yêu cầu cũ không được gửi lại.")
                return {"job": _public_job(row)}
            sources, parents = await _sources(request, owner)
            try:
                job_id = await db.create_imagine_job(owner=owner, prompt=prompt, quality=quality, resolution=resolution,
                    aspect_ratio=aspect, status="queued", n=n, request_id=request.request_id, fingerprint=fingerprint)
            except (ValueError, sqlite3.IntegrityError) as err:
                raise HTTPException(429, "Bạn đã có lượt ảnh đang chạy hoặc hàng đợi đang đầy. Đợi lượt đó xong nhé.") from err
            try:
                await _save_images(owner, job_id, sources, "source", parents)
            except Exception:
                await db.delete_imagine_job(owner, job_id)
                raise
            row = await db.get_imagine_job(owner, job_id)
            options = request.model_copy(update={"source_images": None, "source_image": None, "source_image_id": None})
            task = asyncio.create_task(_run_job(options, owner, job_id, sources))
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)
            return JSONResponse(status_code=202, content={"job": _public_job(row)})

    # Tương thích với bản frontend cũ: trả kết quả trong cùng request.
    sources, parents = await _sources(request, owner)
    try:
        images = await _generate(request, owner, sources)
    except AdmissionDenied as err:
        raise HTTPException(429, err.message) from err
    except ProviderError as err:
        raise HTTPException(502, str(err)) from err
    except TimeoutError as err:
        raise HTTPException(504, "Peto tạo ảnh lâu quá nên đã dừng lượt này. Bạn có thể thử lại.") from err
    job_id = await db.create_imagine_job(owner=owner, prompt=prompt, quality=quality, resolution=resolution, aspect_ratio=aspect, n=n)
    try:
        await _save_images(owner, job_id, sources, "source", parents)
        await _save_images(owner, job_id, images, "output")
    except Exception:
        await db.delete_imagine_job(owner, job_id)
        raise
    return {"job": _public_job(await db.get_imagine_job(owner, job_id))}


@router.get("/api/imagine/requests/{request_id}")
async def get_request(request_id: str, owner: str = Depends(current_owner)):
    # Đợi lượt POST đang lưu ảnh tham chiếu, tránh báo chưa nhận khi lưu chưa xong.
    async with _accept_lock:
        previous = await db.get_imagine_request(owner, request_id)
    if not previous:
        raise HTTPException(404, "Máy chủ chưa nhận lượt tạo ảnh này.")
    row = await db.get_imagine_job(owner, previous["job_id"])
    if not row:
        raise HTTPException(410, "Lượt ảnh này đã bị xóa.")
    return {"job": _public_job(row)}


@router.get("/api/imagine/{job_id}")
async def get_job(job_id: str, owner: str = Depends(current_owner)):
    row = await db.get_imagine_job(owner, job_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy lượt ảnh.")
    result = _public_job(row)
    if row["status"] != "complete":
        result["images"] = []
    return {"job": result}


@router.get("/api/imagine/images/{image_id}")
async def get_image(
    image_id: str,
    owner: str = Depends(current_owner),
    download: int = Query(default=0),
):
    record = await db.get_imagine_image(owner, image_id)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    path = Path(record["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    ext = path.suffix or ".jpg"
    return FileResponse(
        path,
        media_type=record["mime"],
        filename=f"peto-{image_id}{ext}",
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, max-age=3600"},
    )


class LikeRequest(BaseModel):
    liked: bool


@router.delete("/api/imagine/images/{image_id}")
async def delete_image(image_id: str, owner: str = Depends(current_owner)) -> dict:
    """Xóa một ảnh trong thư viện; lượt không còn ảnh nào thì bị xóa theo."""
    result = await db.delete_imagine_image(owner, image_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    return {"deleted": True, "job_deleted": result == "job"}


@router.put("/api/imagine/images/{image_id}/like")
async def like_image(image_id: str, request: LikeRequest, owner: str = Depends(current_owner)) -> dict:
    if not await db.set_imagine_image_liked(owner, image_id, request.liked):
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    return {"liked": request.liked}


@router.delete("/api/imagine/{job_id}")
async def delete_job(job_id: str, owner: str = Depends(current_owner)) -> dict:
    row = await db.get_imagine_job(owner, job_id)
    if row and row["status"] in {"queued", "running"}:
        raise HTTPException(409, "Đợi lượt tạo ảnh kết thúc trước khi xóa nhé.")
    if not await db.delete_imagine_job(owner, job_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    return {"deleted": True}

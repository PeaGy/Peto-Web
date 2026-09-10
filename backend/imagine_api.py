"""HTTP API cho Peto tạo ảnh — tách khỏi /api/chat."""

from __future__ import annotations

import asyncio
import base64
import binascii
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import db
from ai.base import ProviderError
from ai.imagine import (
    ASPECT_RATIOS,
    QUALITIES,
    RESOLUTIONS,
    GeneratedImage,
    generate_images,
)
from attachments import IMAGE_MIMES, delete_files, sniff_image_mime
from auth import current_owner
from config import (
    IMAGINE_TIMEOUT_SECONDS,
    MAX_IMAGINE_N,
    MAX_IMAGINE_PROMPT_CHARS,
    MAX_IMAGINE_SOURCE_BYTES,
    UPLOAD_DIR,
)
from rate_limit import AdmissionDenied, admission

router = APIRouter(tags=["imagine"])


class SourceImageUpload(BaseModel):
    data: str = Field(min_length=1, max_length=4 * ((MAX_IMAGINE_SOURCE_BYTES + 2) // 3))


class ImagineRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_IMAGINE_PROMPT_CHARS)
    quality: str = "low"
    resolution: str = "1k"
    aspect_ratio: str = "auto"
    n: int = Field(default=1, ge=1, le=MAX_IMAGINE_N)
    source_image: SourceImageUpload | None = None
    source_image_id: str | None = Field(default=None, min_length=1, max_length=64)


def _check_source(data: bytes) -> GeneratedImage:
    if not data or len(data) > MAX_IMAGINE_SOURCE_BYTES:
        raise HTTPException(400, f"Ảnh gốc phải nhỏ hơn hoặc bằng {MAX_IMAGINE_SOURCE_BYTES / 1024 / 1024:g} MB.")
    mime = sniff_image_mime(data)
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(400, "Ảnh gốc không hợp lệ. Peto nhận ảnh PNG, JPEG hoặc WebP để chỉnh sửa.")
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


def _public_job(row: dict) -> dict:
    all_images = row.get("images") or []
    source = next((image for image in all_images if image.get("kind") == "source"), None)
    return {
        "id": row["id"],
        "prompt": row["prompt"],
        "quality": row["quality"],
        "resolution": row["resolution"],
        "aspect_ratio": row["aspect_ratio"],
        "created_at": row["created_at"],
        "source_image": {"id": source["id"], "mime": source["mime"], "url": f"/api/imagine/images/{source['id']}"} if source else None,
        "images": [
            {
                "id": image["id"],
                "mime": image["mime"],
                "url": f"/api/imagine/images/{image['id']}",
            }
            for image in all_images if image.get("kind", "output") == "output"
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
async def list_jobs(owner: str = Depends(current_owner)) -> dict:
    rows = await db.list_imagine_jobs(owner)
    return {"jobs": [_public_job(row) for row in rows]}


@router.post("/api/imagine")
async def create_job(request: ImagineRequest, owner: str = Depends(current_owner)):
    prompt, quality, resolution, aspect, n = _validate(request)
    source_image = await _source_image(request, owner)

    try:
        async with admission.slot(f"imagine:{owner}"):
            async with asyncio.timeout(IMAGINE_TIMEOUT_SECONDS):
                images = await generate_images(
                    prompt=prompt,
                    quality=quality,
                    resolution=resolution,
                    aspect_ratio=aspect,
                    n=n,
                    source_image=source_image,
                )
    except AdmissionDenied as denied:
        raise HTTPException(status_code=429, detail=denied.message) from denied
    except ProviderError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    except TimeoutError as err:
        raise HTTPException(
            status_code=504,
            detail="Peto tạo ảnh lâu quá nên đã dừng lượt này. Bạn có thể thử lại.",
        ) from err

    job_id = await db.create_imagine_job(
        owner=owner,
        prompt=prompt,
        quality=quality,
        resolution=resolution,
        aspect_ratio=aspect,
    )
    saved: list[Path] = []
    try:
        folder = UPLOAD_DIR / "imagine" / job_id
        folder.mkdir(parents=True, exist_ok=True)
        public_images = []
        public_source = None
        images_to_save = [("output", image) for image in images]
        if source_image is not None:
            images_to_save.insert(0, ("source", source_image))
        for kind, image in images_to_save:
            image_id = uuid.uuid4().hex
            ext = IMAGE_MIMES.get(image.mime, ".jpg")
            path = folder / f"{image_id}{ext}"
            path.write_bytes(image.data)
            saved.append(path)
            await db.add_imagine_image(
                image_id=image_id,
                job_id=job_id,
                owner=owner,
                mime=image.mime,
                path=str(path),
                kind=kind,
            )
            public_image = {"id": image_id, "mime": image.mime, "url": f"/api/imagine/images/{image_id}"}
            if kind == "source":
                public_source = public_image
            else:
                public_images.append(public_image)
    except Exception:
        delete_files(saved)
        await db.delete_imagine_job(owner, job_id)
        raise

    return {
        "job": {
            "id": job_id,
            "prompt": prompt,
            "quality": quality,
            "resolution": resolution,
            "aspect_ratio": aspect,
            "created_at": time.time(),
            "images": public_images,
            "source_image": public_source,
        }
    }


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


@router.delete("/api/imagine/{job_id}")
async def delete_job(job_id: str, owner: str = Depends(current_owner)) -> dict:
    if not await db.delete_imagine_job(owner, job_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    return {"deleted": True}

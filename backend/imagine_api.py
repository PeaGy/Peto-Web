"""HTTP API cho tab Imagine — tách khỏi /api/chat."""

from __future__ import annotations

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
    generate_images,
)
from attachments import IMAGE_MIMES, delete_files
from auth import current_owner
from config import (
    IMAGINE_TIMEOUT_SECONDS,
    MAX_IMAGINE_N,
    MAX_IMAGINE_PROMPT_CHARS,
    UPLOAD_DIR,
)
from rate_limit import AdmissionDenied, admission

router = APIRouter(tags=["imagine"])


class ImagineRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_IMAGINE_PROMPT_CHARS)
    quality: str = "low"
    resolution: str = "1k"
    aspect_ratio: str = "auto"
    n: int = Field(default=1, ge=1, le=MAX_IMAGINE_N)


def _public_job(row: dict) -> dict:
    return {
        "id": row["id"],
        "prompt": row["prompt"],
        "quality": row["quality"],
        "resolution": row["resolution"],
        "aspect_ratio": row["aspect_ratio"],
        "created_at": row["created_at"],
        "images": [
            {
                "id": image["id"],
                "mime": image["mime"],
                "url": f"/api/imagine/images/{image['id']}",
            }
            for image in row.get("images") or []
        ],
    }


def _validate(request: ImagineRequest) -> tuple[str, str, str, str, int]:
    prompt = " ".join(request.prompt.split())
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt trống")
    quality = request.quality.strip().lower()
    resolution = request.resolution.strip().lower()
    aspect = request.aspect_ratio.strip()
    if quality not in QUALITIES:
        raise HTTPException(status_code=400, detail="Chất lượng phải là low (Nhanh) hoặc medium (Chất lượng)")
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

    try:
        async with admission.slot(f"imagine:{owner}"):
            images = await generate_images(
                prompt=prompt,
                quality=quality,
                resolution=resolution,
                aspect_ratio=aspect,
                n=n,
            )
    except AdmissionDenied as denied:
        raise HTTPException(status_code=429, detail=denied.message) from denied
    except ProviderError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    except TimeoutError as err:
        raise HTTPException(
            status_code=504,
            detail=f"Tạo ảnh quá {IMAGINE_TIMEOUT_SECONDS:.0f}s nên bỏ lượt này.",
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
        for image in images:
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
            )
            public_images.append(
                {
                    "id": image_id,
                    "mime": image.mime,
                    "url": f"/api/imagine/images/{image_id}",
                }
            )
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
        filename=f"imagine-{image_id}{ext}",
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/api/imagine/{job_id}")
async def delete_job(job_id: str, owner: str = Depends(current_owner)) -> dict:
    if not await db.delete_imagine_job(owner, job_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    return {"deleted": True}

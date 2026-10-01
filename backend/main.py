"""Khởi tạo ứng dụng và gắn các router; chạy bằng uvicorn main:app."""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from features.agent import api as agent_api
from features.agent import install as agent_install
from features.accounts import auth
from features.documents import api as document_api
from features.imagine import api as imagine_api
from features.companion import memory_api
from features.accounts import profile as profile_api
from features.voice import api as voice_api
from core import static_files
from ai import get_provider
from core.identity import get_app_identity
from core.config import ALLOWED_ORIGINS, STATIC_DIR
from features.docs import api as docs_api
from core.lifespan import lifespan
from features.chat import api as chat_api
from features.companion import api as companion_api
from features.projects import api as project_api

# Tắt trang tài liệu API tự sinh của FastAPI (/docs, /redoc, /openapi.json): /docs là trang hướng dẫn cho người dùng
# (docs_api, static_files), mà trang Swagger mặc định lại giành mất /docs không có dấu "/" cuối. Sơ đồ API cũng không
# cần công khai.
app = FastAPI(title="Peto Web", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(auth.router)
app.include_router(imagine_api.router)
app.include_router(profile_api.router)
app.include_router(memory_api.router)
app.include_router(voice_api.router)
app.include_router(document_api.router)
app.include_router(agent_api.router)
# /install.ps1 nằm ngoài /api: phải đăng ký trước static_files.mount ở cuối tệp.
app.include_router(agent_install.router)
app.include_router(docs_api.router)

app.include_router(chat_api.router)
app.include_router(project_api.router)
app.include_router(companion_api.router)

@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"ok": True, "provider": get_provider().name}



@app.get("/api/app-info")
async def app_info() -> dict:
    """Tên và avatar của Peto, lấy từ chính Discord application.

    Không yêu cầu đăng nhập vì màn hình đăng nhập cũng cần hiển thị, và nội
    dung trả về vốn đã là thông tin công khai của application.
    """
    return await get_app_identity()



# Phải gắn SAU mọi route API, vì nó bắt mọi đường dẫn còn lại.
static_files.mount(app, STATIC_DIR)

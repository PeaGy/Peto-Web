"""Kiểm thử phần phục vụ frontend đã build."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import static_files

SITE_INDEX = (
    "<!doctype html><html><head><title>Peto</title></head>"
    "<body><h1>Peto</h1></body></html>"
)
AVATAR = "https://cdn.discordapp.com/app-icons/1/abc.png?size=256"


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    """Trang chủ hỏi avatar của bot để làm ảnh xem trước link.

    Trong test thì trả giá trị giả: conftest có đặt DISCORD_CLIENT_ID, để hàm
    thật chạy là nó gọi ra discord.com.
    """
    value: dict[str, str | None] = {"name": "Peto", "avatar_url": None}

    async def fake_identity() -> dict[str, str | None]:
        return dict(value)

    monkeypatch.setattr(static_files, "get_app_identity", fake_identity)
    return value


@pytest.fixture
def site(tmp_path):
    """Một bản build giả, đủ giống thứ Vite sinh ra."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(SITE_INDEX, encoding="utf-8")
    (tmp_path / "404.html").write_text("<h1>Ở đây không có gì cả.</h1>", encoding="utf-8")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.ico").write_text("x", encoding="utf-8")

    # File bí mật NGOÀI thư mục build, dùng để thử path traversal.
    (tmp_path.parent / "bi-mat.txt").write_text("TOKEN_THAT", encoding="utf-8")

    app = FastAPI()

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    assert static_files.mount(app, tmp_path)
    return app


@pytest.fixture
async def site_client(site):
    async with AsyncClient(
        transport=ASGITransport(app=site), base_url="http://test"
    ) as client:
        yield client


async def test_serves_index(site_client):
    response = await site_client.get("/")
    assert response.status_code == 200
    assert "Peto" in response.text


async def test_serves_hashed_asset_with_long_cache(site_client):
    response = await site_client.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


async def test_index_is_not_cached(site_client):
    response = await site_client.get("/")
    assert response.headers["cache-control"] == "no-cache"


async def test_unknown_path_serves_custom_404(site_client):
    """Giao diện chuyển tab bằng hash nên không có route theo đường dẫn.

    Trước đây chỗ này trả index.html kèm status 200, khiến mọi đường dẫn gõ sai
    hiện ra y như trang chủ.
    """
    response = await site_client.get("/hoi-thoai/abc")
    assert response.status_code == 404
    assert "Ở đây không có gì cả." in response.text


async def test_custom_404_is_not_cached(site_client):
    response = await site_client.get("/khong-co-that")
    assert response.headers["cache-control"] == "no-cache"


async def test_unknown_path_is_404_even_without_a_custom_page(tmp_path):
    """Bản build thiếu 404.html vẫn không được trả trang chủ kèm status 200."""
    (tmp_path / "index.html").write_text("<h1>Peto</h1>", encoding="utf-8")
    app = FastAPI()
    assert static_files.mount(app, tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/khong-co-that")
    assert response.status_code == 404
    assert "Peto" not in response.text


async def test_api_routes_are_not_shadowed(site_client):
    assert (await site_client.get("/api/health")).json() == {"ok": True}


async def test_unknown_api_path_is_404_not_html(site_client):
    """API sai đường dẫn phải ra 404, không được trả về trang web."""
    response = await site_client.get("/api/khong-co-that")
    assert response.status_code == 404
    assert "Peto" not in response.text


@pytest.mark.parametrize(
    "attack",
    [
        "../bi-mat.txt",
        "..%2Fbi-mat.txt",
        "assets/../../bi-mat.txt",
        "....//bi-mat.txt",
    ],
)
async def test_path_traversal_cannot_escape_build_dir(site_client, attack):
    response = await site_client.get(f"/{attack}")
    assert "TOKEN_THAT" not in response.text


def test_mount_is_skipped_without_a_build(tmp_path):
    app = FastAPI()
    assert static_files.mount(app, tmp_path / "khong-ton-tai") is False


async def test_head_is_supported(site_client):
    """`curl -I` và công cụ giám sát uptime dùng HEAD.

    FastAPI không tự thêm HEAD cho route GET, nên phải khai báo rõ — thiếu là
    kiểm tra deploy bằng `curl -sI` sẽ ra 405 và làm người ta tưởng hỏng.
    """
    response = await site_client.head("/")
    assert response.status_code == 200


async def test_head_on_unknown_path_is_also_404(site_client):
    assert (await site_client.head("/hoi-thoai/abc")).status_code == 404


@pytest.mark.parametrize("path", ["/", "/index.html"])
async def test_index_carries_link_preview_image(site_client, identity, path):
    """Discord đọc og:image trong HTML chứ không chạy JS.

    Thiếu thẻ này thì link dán vào Discord không có ảnh thu nhỏ.
    """
    identity["avatar_url"] = AVATAR
    page = (await site_client.get(path)).text
    tag = f'<meta property="og:image" content="{AVATAR}" />'
    assert tag in page
    assert page.index(tag) < page.index("</head>")
    assert '<meta property="og:image:alt" content="Ảnh đại diện của Peto" />' in page


async def test_preview_image_url_cannot_break_out_of_the_tag(site_client, identity):
    identity["avatar_url"] = 'https://x.test/a.png?a=1&b="><script>alert(1)</script>'
    page = (await site_client.get("/")).text
    assert "<script>alert(1)" not in page
    assert 'content="https://x.test/a.png?a=1&amp;b=&quot;&gt;&lt;script&gt;' in page


@pytest.mark.parametrize("avatar", [None, "", "javascript:alert(1)", "/tuong-doi.png"])
async def test_without_usable_avatar_index_is_unchanged(site_client, identity, avatar):
    """Không có ảnh dùng được thì bỏ og:image, trang vẫn phục vụ nguyên vẹn."""
    identity["avatar_url"] = avatar
    response = await site_client.get("/")
    assert response.status_code == 200
    assert response.text == SITE_INDEX


def test_page_without_head_is_left_alone():
    page = "<h1>Peto</h1>"
    assert static_files._with_preview_image(page, AVATAR, "Peto") == page

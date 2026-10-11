"""Ảnh riêng phải giữ qua đăng nhập, khôi phục được và không lộ sang tài khoản khác."""
from io import BytesIO

import pytest
from PIL import Image, PngImagePlugin

import storage as db
from storage import avatars
from features.accounts import profile
from conftest import sign_in


def picture(fmt="PNG", size=(80, 40)):
    output = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("ghi_chu", "Không giữ thông tin riêng trong ảnh đại diện")
    Image.new("RGB", size, "red").save(output, fmt, **({"pnginfo": metadata} if fmt == "PNG" else {}))
    return output.getvalue()


async def test_luu_anh_dang_nhap_lai_va_khoi_phuc(client):
    owner = await sign_in(client)
    original = "https://example.test/avatar.png"
    await db.upsert_user(owner=owner, provider="github", username="test", display_name="Test", avatar_url=original)
    saved = await client.put("/api/profile/avatar", content=picture(), headers={"Content-Type": "image/png"})
    assert saved.status_code == 200
    avatar = saved.json()
    assert avatar["custom_avatar"] is True
    assert avatar["avatar_url"].startswith("/api/profile/avatar?v=")
    response = await client.get(avatar["avatar_url"])
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-store"
    with Image.open(BytesIO(response.content)) as image:
        assert image.size == (512, 512)
        assert "ghi_chu" not in image.info
    # Đăng nhập lại chỉ cập nhật ảnh gốc; ảnh tải lên vẫn được ưu tiên.
    latest = "https://example.test/new-avatar.png"
    await db.upsert_user(owner=owner, provider="github", username="test", display_name="Test", avatar_url=latest)
    assert (await client.get("/api/auth/me")).json()["user"]["avatar_url"] == avatar["avatar_url"]
    assert (await client.get("/api/profile")).json()["avatar"] == avatar
    replacement = await client.put("/api/profile/avatar", content=picture("JPEG"), headers={"Content-Type": "image/jpeg"})
    assert replacement.json()["avatar_url"] != avatar["avatar_url"]
    reset = await client.delete("/api/profile/avatar")
    assert reset.json() == {"avatar_url": latest, "custom_avatar": False}
    assert (await client.get("/api/profile/avatar")).status_code == 404
    assert await avatars.get(owner) is None


async def test_anh_rieng_khong_doc_hoac_xoa_duoc_tu_tai_khoan_khac(client, anon_client):
    owner = await sign_in(client)
    saved = await client.put("/api/profile/avatar", content=picture(), headers={"Content-Type": "image/png"})
    await sign_in(anon_client)
    # URL của người khác vẫn chỉ trả ảnh của chính phiên đăng nhập hiện tại.
    assert (await anon_client.get(saved.json()["avatar_url"])).status_code == 404
    await anon_client.delete("/api/profile/avatar")
    assert await avatars.get(owner) is not None
    await avatars.reset(owner)


@pytest.mark.parametrize("data,mime", [(b"not an image", "image/png"), (picture(), "image/jpeg"), (b"<svg/>", "image/svg+xml"), (picture("GIF"), "image/gif")])
async def test_anh_sai_khong_ghi_de_anh_hien_tai(client, data, mime):
    owner = await sign_in(client)
    saved = await client.put("/api/profile/avatar", content=picture(), headers={"Content-Type": "image/png"})
    assert (await client.put("/api/profile/avatar", content=data, headers={"Content-Type": mime})).status_code == 400
    assert (await client.get("/api/profile")).json()["avatar"] == saved.json()
    await avatars.reset(owner)


async def test_chan_dung_luong_va_do_phan_giai(client, monkeypatch):
    owner = await sign_in(client)
    monkeypatch.setattr(profile, "MAX_AVATAR_BYTES", 32)
    assert (await client.put("/api/profile/avatar", content=picture(), headers={"Content-Type": "image/png"})).status_code == 413
    monkeypatch.setattr(profile, "MAX_AVATAR_BYTES", 1024 * 1024)
    monkeypatch.setattr(profile, "MAX_AVATAR_PIXELS", 100)
    assert (await client.put("/api/profile/avatar", content=picture(), headers={"Content-Type": "image/png"})).status_code == 400
    assert await avatars.get(owner) is None


async def test_anh_dai_dien_can_dang_nhap(anon_client):
    assert (await anon_client.get("/api/profile/avatar")).status_code == 401
    assert (await anon_client.put("/api/profile/avatar", content=picture(), headers={"Content-Type": "image/png"})).status_code == 401
    assert (await anon_client.delete("/api/profile/avatar")).status_code == 401

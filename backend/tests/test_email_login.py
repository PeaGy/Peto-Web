"""Đăng nhập bằng email như AIRI (thư có nút đăng nhập, trang đang chờ tự tiếp tục, kể cả khi mở thư trên máy khác) và gộp
tài khoản Google/GitHub/email theo email đã xác minh. Không gọi mạng thật."""

from __future__ import annotations

import re
import sqlite3
import uuid
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

import storage as db
from core import config
from core.config import DB_PATH, SESSION_COOKIE, discord_id_from_owner, owner_key
from features.accounts import auth, email_login
from features.accounts.email_login import deliver as real_deliver
from main import app
from storage import email_login as email_store

EMAIL = "Tran.An+peto@Gmail.com"
REAL_CLIENT = httpx.AsyncClient
WINDOWS_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


@pytest.fixture(autouse=True)
def unique_email(monkeypatch) -> str:
    """Mỗi test một hộp thư riêng: database dùng chung cả lượt test, thư và thời gian chờ của test trước còn đó."""
    address = f"Tran.An{uuid.uuid4().hex[:8]}+peto@Gmail.com"
    monkeypatch.setitem(globals(), "EMAIL", address)
    return address


@pytest.fixture
async def phone() -> AsyncClient:
    """Một trình duyệt khác (điện thoại mở thư), không chung cookie với ``anon_client``."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def send(client, email: str | None = None, **headers):
    return await client.post("/api/auth/email/send", json={"email": EMAIL if email is None else email},
                             headers=headers or None)


def link_of(mail: dict) -> str:
    return re.search(r"(https?://[^\s\"<]+/#email_token=[A-Za-z0-9_-]+)", mail["text"]).group(1)


def token_of(mail: dict) -> str:
    return link_of(mail).split("#email_token=", 1)[1]


async def open_link(client, token: str, **extra):
    return await client.post("/api/auth/email/link", json={"token": token, **extra})


async def status(client):
    return await client.post("/api/auth/email/status")


def session_of(response) -> str | None:
    return auth.read_session(response.cookies.get(SESSION_COOKIE))


# --- Gửi thư -------------------------------------------------------------------------------------------------------


async def test_thu_dang_nhap_co_nut_khong_co_ma(anon_client, sent_emails):
    response = await send(anon_client)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "resend_after": 60, "expires_in": 600}
    assert response.cookies.get(email_login.REQUEST_COOKIE)
    mail = sent_emails[0]
    # Gửi tới đúng địa chỉ đã gõ (viết thường), không phải dạng chuẩn hóa.
    assert mail["to"] == EMAIL.lower()
    assert mail["subject"] == "Đăng nhập vào Peto"
    link = link_of(mail)
    # Token nằm sau dấu #, nên không tới máy chủ lúc trình duyệt tải trang; nút trong HTML trỏ đúng đường dẫn đó.
    assert link.startswith("http://localhost:5173/#email_token=")
    assert f'href="{link}"' in mail["html"]
    assert not re.search(r"\b\d{6}\b", mail["subject"] + mail["text"])


async def test_tra_loi_giong_nhau_du_email_da_co_tai_khoan_hay_chua(anon_client, sent_emails, monkeypatch):
    tag = EMAIL[7:15]
    await send(anon_client, f"cu{tag}@example.com")
    await open_link(anon_client, token_of(sent_emails[-1]))
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    old = await send(anon_client, f"cu{tag}@example.com")
    new = await send(anon_client, f"moi{tag}@example.com")
    assert old.status_code == new.status_code == 200
    assert old.json() == new.json()


async def test_khong_luu_dia_chi_email_hay_token(anon_client, sent_emails):
    secret = f"bi.mat.{EMAIL[7:15]}@example.com"
    await send(anon_client, secret, **{"User-Agent": WINDOWS_CHROME})
    token = token_of(sent_emails[-1])
    await open_link(anon_client, token)
    with sqlite3.connect(DB_PATH) as con:
        tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            for row in con.execute(f'SELECT * FROM "{table}"'):
                for value in row:
                    if isinstance(value, str):
                        assert "bi.mat" not in value and token not in value and "Mozilla" not in value, table


@pytest.mark.parametrize("email", ["", "khong-co-a-cong", "a@b", "a b@example.com", "x@example.com\r\nBcc: y@z.com"])
async def test_email_sai_dang(anon_client, sent_emails, email):
    response = await send(anon_client, email)
    assert response.status_code == 400
    assert sent_emails == []


async def test_gioi_han_gui_theo_email(anon_client, sent_emails, monkeypatch):
    assert (await send(anon_client)).status_code == 200
    soon = await send(anon_client)
    assert soon.status_code == 429
    assert int(soon.headers["retry-after"]) > 0
    assert "Đợi" in soon.json()["detail"]
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    for _ in range(4):
        assert (await send(anon_client)).status_code == 200
    limited = await send(anon_client)
    assert limited.status_code == 429
    assert "nhiều thư đăng nhập quá" in limited.json()["detail"]
    assert len(sent_emails) == 5


async def test_gioi_han_gui_theo_ip(anon_client, sent_emails):
    for index in range(email_login.SENDS_PER_IP_HOUR):
        assert (await send(anon_client, f"nguoi{index}{EMAIL[7:15]}@example.com")).status_code == 200
    assert (await send(anon_client, "them@example.com")).status_code == 429
    assert len(sent_emails) == email_login.SENDS_PER_IP_HOUR


async def test_gioi_han_mo_duong_dan_theo_ip(anon_client, monkeypatch):
    monkeypatch.setattr(email_login, "LINKS_PER_IP_HOUR", 3)
    for _ in range(3):
        await open_link(anon_client, "x" * 43)
    assert (await open_link(anon_client, "x" * 43)).status_code == 429


def test_ip_chi_tin_cf_connecting_ip_khi_qua_tunnel():
    def request(host: str, header: str = "203.0.113.9"):
        return SimpleNamespace(client=SimpleNamespace(host=host), headers={"cf-connecting-ip": header})

    assert email_login.client_ip(request("127.0.0.1")) == "203.0.113.9"
    assert email_login.client_ip(request("::1")) == "203.0.113.9"
    assert email_login.client_ip(request("198.51.100.4")) == "198.51.100.4"


def test_ten_thiet_bi():
    assert email_login.device_label(WINDOWS_CHROME) == "Chrome trên Windows"
    assert email_login.device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1") == "Safari trên iPhone"
    assert email_login.device_label("Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Edg/130.0") == "Edge trên Windows"
    assert email_login.device_label("") == "Trình duyệt"


async def test_chua_cau_hinh_resend(anon_client, monkeypatch):
    monkeypatch.setattr(config, "RESEND_API_KEY", "")
    assert (await send(anon_client)).status_code == 503
    assert (await open_link(anon_client, "x" * 43)).status_code == 503
    assert auth.available_providers()["email"] is False


async def test_gui_thu_loi_thi_bao_502_va_bo_thu(anon_client, monkeypatch, sent_emails):
    async def broken(*args, **kwargs):
        raise email_login.EmailError

    monkeypatch.setattr(email_login, "deliver", broken)
    response = await send(anon_client)
    assert response.status_code == 502
    assert response.json()["detail"] == "Chưa gửi được thư. Thử lại sau ít phút nhé."
    assert not response.cookies.get(email_login.REQUEST_COOKIE)


async def test_deliver_goi_resend_dung_dang(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["key"] = request.headers["idempotency-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "abc"})

    real = httpx.AsyncClient
    monkeypatch.setattr(email_login.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(config, "EMAIL_REPLY_TO", "hotro@peto.test")
    await real_deliver("an@example.com", "Chủ đề", "chữ", "<p>chữ</p>", "k-1")
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["auth"] == "Bearer test-resend-key"
    assert seen["key"] == "k-1"
    assert seen["body"]["to"] == ["an@example.com"]
    assert seen["body"]["from"] == "Peto <no-reply@peto.test>"
    assert seen["body"]["reply_to"] == "hotro@peto.test"

    monkeypatch.setattr(email_login.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(422)), **kw))
    with pytest.raises(email_login.EmailError):
        await real_deliver("an@example.com", "Chủ đề", "chữ", "<p>chữ</p>", "k-2")


async def test_goc_duong_dan_khong_lay_tu_header_gia(anon_client, sent_emails, monkeypatch):
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    # Host/Origin giả không được thành gốc của đường dẫn: token sẽ lộ cho máy của kẻ gửi yêu cầu.
    await send(anon_client, **{"Origin": "https://ke-gia-mao.example", "Host": "ke-gia-mao.example"})
    assert link_of(sent_emails[-1]).startswith("http://localhost:5173/")
    monkeypatch.setattr(config, "CANONICAL_ORIGIN", "https://peto.peagy.com")
    await send(anon_client)
    assert link_of(sent_emails[-1]).startswith("https://peto.peagy.com/#email_token=")
    await send(anon_client, **{"Origin": "http://localhost:5173"})
    assert link_of(sent_emails[-1]).startswith("http://localhost:5173/#email_token=")


async def test_khong_co_ten_mien_nao_thi_khong_gui(anon_client, sent_emails, monkeypatch):
    for name in ("CANONICAL_ORIGIN", "FRONTEND_URL", "DISCORD_REDIRECT_URI", "GOOGLE_REDIRECT_URI",
                 "GITHUB_LOGIN_REDIRECT_URI"):
        monkeypatch.setattr(config, name, "")
    assert (await send(anon_client)).status_code == 503
    assert sent_emails == []


# --- Bấm nút trong thư -------------------------------------------------------------------------------------------


async def test_cung_trinh_duyet_bam_nut_la_dang_nhap_tab_dang_cho_cung_vao(anon_client, sent_emails):
    await send(anon_client)
    assert (await status(anon_client)).json() == {"state": "waiting"}
    response = await open_link(anon_client, token_of(sent_emails[-1]))
    assert response.json() == {"state": "signed_in", "same_browser": True}
    owner = session_of(response)
    assert owner.startswith("email:") and len(owner) == len("email:") + 32
    assert discord_id_from_owner(owner) == ""

    # Tab "Kiểm tra hộp thư" hỏi lại: nhận phiên đúng một lần.
    waiting = await status(anon_client)
    assert waiting.json() == {"state": "signed_in"}
    assert session_of(waiting) == owner
    assert (await status(anon_client)).json() == {"state": "expired"}

    me = (await anon_client.get("/api/auth/me")).json()
    assert me["user"]["provider"] == "email"
    assert me["user"]["display_name"] == f"{EMAIL.lower()[:2]}•••@gmail.com"
    assert me["user"]["username"] == ""


async def test_mo_thu_tren_dien_thoai_xac_nhan_thi_may_tinh_vao(anon_client, phone, sent_emails):
    await send(anon_client, **{"User-Agent": WINDOWS_CHROME})
    token = token_of(sent_emails[-1])

    # Điện thoại không có cookie yêu cầu: chưa đăng nhập ai cả, chỉ hỏi lại cho đúng thiết bị.
    asked = await open_link(phone, token)
    body = asked.json()
    assert body["state"] == "confirm"
    assert body["device"] == "Chrome trên Windows"
    assert isinstance(body["requested_at"], float)
    assert not asked.cookies.get(SESSION_COOKIE)
    assert (await status(anon_client)).json() == {"state": "waiting"}

    confirmed = await open_link(phone, token, confirm=True)
    assert confirmed.json() == {"state": "signed_in", "same_browser": False}
    owner = session_of(confirmed)
    assert owner.startswith("email:")

    # Máy tính đang chờ nhận phiên của chính tài khoản đó.
    waiting = await status(anon_client)
    assert waiting.json() == {"state": "signed_in"}
    assert session_of(waiting) == owner
    assert (await open_link(phone, token, confirm=True)).status_code == 400


async def test_khong_phai_minh_thi_tu_choi(anon_client, phone, sent_emails):
    await send(anon_client)
    token = token_of(sent_emails[-1])
    denied = await open_link(phone, token, deny=True)
    assert denied.json() == {"state": "denied"}
    assert not denied.cookies.get(SESSION_COOKIE)
    response = await status(anon_client)
    assert response.json() == {"state": "denied"}
    assert not response.cookies.get(SESSION_COOKIE)
    assert (await open_link(phone, token, confirm=True)).status_code == 400


async def test_trinh_duyet_khac_khong_lay_duoc_phien_cua_nguoi_khac(anon_client, phone, sent_emails):
    """Kẻ gõ email của nạn nhân rồi chờ: nạn nhân bấm nút cũng chỉ ra trang xác nhận, không ai được đăng nhập."""
    await send(phone)
    await open_link(anon_client, token_of(sent_emails[-1]))
    assert (await status(phone)).json() == {"state": "waiting"}
    # Trình duyệt không có cookie yêu cầu hỏi trạng thái: không có gì.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger:
        response = await status(stranger)
        assert response.json() == {"state": "expired"}
        assert not response.cookies.get(SESSION_COOKIE)


async def test_duong_dan_dung_mot_lan_va_thu_moi_lam_thu_cu_het_hieu_luc(anon_client, sent_emails, monkeypatch):
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    await send(anon_client)
    first = token_of(sent_emails[-1])
    await send(anon_client)
    second = token_of(sent_emails[-1])
    assert (await open_link(anon_client, first)).status_code == 400
    assert (await open_link(anon_client, second)).status_code == 200
    used = await open_link(anon_client, second)
    assert used.status_code == 400
    assert "đã hết hạn hoặc đã được dùng" in used.json()["detail"]


async def test_duong_dan_het_han_hoac_sai(anon_client, sent_emails, monkeypatch):
    monkeypatch.setattr(email_login, "LINK_TTL", 0)
    await send(anon_client)
    assert (await open_link(anon_client, token_of(sent_emails[-1]))).status_code == 400
    assert (await status(anon_client)).json() == {"state": "expired"}
    for token in ("", "ngan", "x" * 43, "a" * 500):
        response = await open_link(anon_client, token)
        assert response.status_code == 400
        assert not response.cookies.get(SESSION_COOKIE)


async def test_cung_hop_thu_gmail_la_cung_tai_khoan(anon_client, sent_emails, monkeypatch):
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    owners = []
    tag = EMAIL[7:15]
    for address in (f"tran.an{tag}@gmail.com", f"TranAn{tag}+khac@googlemail.com"):
        await send(anon_client, address)
        owners.append(session_of(await open_link(anon_client, token_of(sent_emails[-1]))))
    assert owners[0] == owners[1]
    assert email_login.normalize("a+b@example.com") == "a+b@example.com"
    assert email_login.normalize("a.b+c@outlook.com") == "a.b@outlook.com"


# --- Gộp tài khoản theo email đã xác minh ------------------------------------------------------------------------


def fake_google(monkeypatch, profile: dict):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "test-token"})
        return httpx.Response(200, json=profile)

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handle), **kw))


async def google_sign_in(client, monkeypatch, profile: dict) -> str | None:
    fake_google(monkeypatch, profile)
    client.cookies.set(auth.GOOGLE_STATE_COOKIE, "state-g", path="/api/auth")
    response = await client.get("/api/auth/google/callback", params={"code": "c", "state": "state-g"})
    return session_of(response)


async def email_sign_in(client, sent_emails, address: str) -> str | None:
    await send(client, address)
    return session_of(await open_link(client, token_of(sent_emails[-1])))


async def test_dang_nhap_email_truoc_roi_google_cung_email_vao_cung_tai_khoan(anon_client, phone, sent_emails, monkeypatch):
    address = EMAIL.lower()
    by_email = await email_sign_in(anon_client, sent_emails, address)
    by_google = await google_sign_in(phone, monkeypatch, {
        "sub": f"g-{uuid.uuid4().hex}", "name": "An Trần", "email": address, "email_verified": True})
    assert by_google == by_email


async def test_google_truoc_roi_email_vao_tai_khoan_google_giu_ten(anon_client, phone, sent_emails, monkeypatch):
    address = f"google.first.{uuid.uuid4().hex[:6]}@example.com"
    by_google = await google_sign_in(phone, monkeypatch, {
        "sub": f"g-{uuid.uuid4().hex}", "name": "Người Google", "email": address, "email_verified": True})
    assert by_google.startswith("google:")
    by_email = await email_sign_in(anon_client, sent_emails, address)
    assert by_email == by_google
    me = (await anon_client.get("/api/auth/me")).json()
    assert me["user"]["display_name"] == "Người Google"


async def test_doi_email_ben_google_khong_tach_tai_khoan(phone, monkeypatch):
    sub = f"g-{uuid.uuid4().hex}"
    first = await google_sign_in(phone, monkeypatch, {"sub": sub, "name": "A", "email": f"a{sub}@example.com",
                                                      "email_verified": True})
    second = await google_sign_in(phone, monkeypatch, {"sub": sub, "name": "A", "email": f"b{sub}@example.com",
                                                       "email_verified": True})
    assert first == second


async def test_email_chua_xac_minh_khong_gop(anon_client, phone, sent_emails, monkeypatch):
    address = EMAIL.lower()
    by_email = await email_sign_in(anon_client, sent_emails, address)
    by_google = await google_sign_in(phone, monkeypatch, {
        "sub": f"g-{uuid.uuid4().hex}", "name": "Kẻ lạ", "email": address, "email_verified": False})
    assert by_google != by_email
    assert by_google.startswith("google:")


async def test_tai_khoan_co_tu_truoc_khong_bi_gop_mat_du_lieu(anon_client, phone, sent_emails, monkeypatch):
    """Tài khoản Google đã dùng từ trước khi có gộp thì giữ nguyên, dù email của nó đã thuộc tài khoản email khác."""
    address = EMAIL.lower()
    by_email = await email_sign_in(anon_client, sent_emails, address)
    sub = f"g-{uuid.uuid4().hex}"
    old_owner = owner_key("google", sub)
    await db.upsert_user(owner=old_owner, provider="google", username="Cũ", display_name="Cũ", avatar_url="")
    by_google = await google_sign_in(phone, monkeypatch, {"sub": sub, "name": "Cũ", "email": address,
                                                          "email_verified": True})
    assert by_google == old_owner != by_email


async def test_github_gop_theo_email_chinh_da_xac_minh(anon_client, phone, sent_emails, monkeypatch):
    address = EMAIL.lower()
    by_email = await email_sign_in(anon_client, sent_emails, address)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "gho_test"})
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": int(uuid.uuid4().int % 10**9), "login": "an", "name": "An"})
        if request.url.path == "/user/emails":
            return httpx.Response(200, json=[
                {"email": "phu@example.com", "primary": False, "verified": True},
                {"email": address, "primary": True, "verified": True},
            ])
        return httpx.Response(204)

    real = httpx.AsyncClient
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    phone.cookies.set(auth.GITHUB_STATE_COOKIE, "state-1", path="/api/auth")
    response = await phone.get("/api/auth/github/callback", params={"code": "abc", "state": "state-1"})
    assert session_of(response) == by_email


async def test_discord_khong_bao_gio_duoc_gan_email():
    with pytest.raises(ValueError):
        await email_store.claim_email("a" * 64, owner_key("discord", "111"))

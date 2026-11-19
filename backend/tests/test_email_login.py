"""Đăng nhập bằng email: mã 6 số gửi qua Resend. Không gọi mạng thật."""

from __future__ import annotations

import re
import sqlite3
from types import SimpleNamespace

import httpx
import pytest

from core import config
from core.config import DB_PATH, SESSION_COOKIE, discord_id_from_owner
from features.accounts import auth, email_login
from features.accounts.email_login import deliver as real_deliver

EMAIL = "Tran.An+peto@Gmail.com"


@pytest.fixture(autouse=True)
def unique_email(monkeypatch) -> str:
    """Mỗi test một hộp thư riêng: database dùng chung cả lượt test, mã và thời gian chờ của test trước còn đó."""
    import uuid
    address = f"Tran.An{uuid.uuid4().hex[:8]}+peto@Gmail.com"
    monkeypatch.setitem(globals(), "EMAIL", address)
    return address


def code_of(mail: dict) -> str:
    return re.search(r"\b(\d{6})\b", mail["subject"]).group(1)


async def send(client, email: str | None = None):
    return await client.post("/api/auth/email/send", json={"email": EMAIL if email is None else email})


async def verify(client, code: str, email: str | None = None):
    return await client.post("/api/auth/email/verify", json={"email": EMAIL if email is None else email, "code": code})



async def test_gui_ma_roi_dang_nhap_tao_tai_khoan_email(anon_client, sent_emails):
    response = await send(anon_client)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "resend_after": 60, "expires_in": 600}
    assert len(sent_emails) == 1
    mail = sent_emails[0]
    # Gửi tới đúng địa chỉ đã gõ (viết thường), không phải dạng chuẩn hóa.
    assert mail["to"] == EMAIL.lower()
    code = code_of(mail)
    assert code in mail["text"] and code in mail["html"]

    response = await verify(anon_client, code)
    assert response.status_code == 200
    assert response.cookies.get(SESSION_COOKIE)
    owner = auth.read_session(response.cookies.get(SESSION_COOKIE))
    assert owner.startswith("email:") and len(owner) == len("email:") + 32
    # Tài khoản email không bao giờ trỏ tới Discord ID, nên không chạm được trí nhớ của bot.
    assert discord_id_from_owner(owner) == ""

    anon_client.cookies.set(SESSION_COOKIE, response.cookies.get(SESSION_COOKIE))
    me = (await anon_client.get("/api/auth/me")).json()
    assert me["authenticated"] is True
    assert me["user"]["provider"] == "email"
    # Không lưu email: chỉ hai ký tự đầu và tên miền, đủ để người dùng nhận ra tài khoản.
    assert me["user"]["display_name"] == "tr•••@gmail.com"
    assert me["user"]["username"] == ""


async def test_cung_hop_thu_gmail_la_cung_tai_khoan(anon_client, sent_emails, monkeypatch):
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    owners = []
    tag = EMAIL[7:15]
    for address in (f"tran.an{tag}@gmail.com", f"TranAn{tag}+khac@googlemail.com"):
        await send(anon_client, address)
        response = await verify(anon_client, code_of(sent_emails[-1]), address)
        owners.append(auth.read_session(response.cookies.get(SESSION_COOKIE)))
    assert owners[0] == owners[1]
    # Nơi khác "+nhãn" có thể là hộp thư khác: không gộp.
    assert email_login.normalize("a+b@example.com") == "a+b@example.com"
    assert email_login.normalize("a.b+c@outlook.com") == "a.b@outlook.com"


async def test_tra_loi_giong_nhau_du_email_da_co_tai_khoan_hay_chua(anon_client, sent_emails, monkeypatch):
    tag = EMAIL[7:15]
    await send(anon_client, f"cu{tag}@example.com")
    await verify(anon_client, code_of(sent_emails[-1]), f"cu{tag}@example.com")
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    old = await send(anon_client, f"cu{tag}@example.com")
    new = await send(anon_client, f"moi{tag}@example.com")
    assert old.status_code == new.status_code == 200
    assert old.json() == new.json()


async def test_khong_luu_dia_chi_email_o_dau_ca(anon_client, sent_emails):
    secret = f"bi.mat.{EMAIL[7:15]}@example.com"
    await send(anon_client, secret)
    await verify(anon_client, code_of(sent_emails[-1]), secret)
    with sqlite3.connect(DB_PATH) as con:
        tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            for row in con.execute(f'SELECT * FROM "{table}"'):
                for value in row:
                    assert not (isinstance(value, str) and "bi.mat" in value), table


async def test_ma_sai_dem_lui_roi_huy_ma(anon_client, sent_emails):
    await send(anon_client)
    code = code_of(sent_emails[-1])
    wrong = "000000" if code != "000000" else "111111"
    for left in (4, 3, 2, 1):
        response = await verify(anon_client, wrong)
        assert response.status_code == 400
        assert response.json()["detail"] == f"Mã không đúng. Còn {left} lần thử."
    response = await verify(anon_client, wrong)
    assert "đã bị hủy" in response.json()["detail"]
    # Mã đúng cũng không dùng được nữa.
    response = await verify(anon_client, code)
    assert response.status_code == 400
    assert not response.cookies.get(SESSION_COOKIE)


async def test_ma_chi_dung_mot_lan_va_chi_ma_moi_nhat(anon_client, sent_emails, monkeypatch):
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    await send(anon_client)
    first = code_of(sent_emails[-1])
    await send(anon_client)
    second = code_of(sent_emails[-1])
    if first != second:
        assert (await verify(anon_client, first)).status_code == 400
    assert (await verify(anon_client, second)).status_code == 200
    again = await verify(anon_client, second)
    assert again.status_code == 400
    assert "hết hạn" in again.json()["detail"]


async def test_ma_het_han(anon_client, sent_emails, monkeypatch):
    monkeypatch.setattr(email_login, "CODE_TTL", 0)
    await send(anon_client)
    response = await verify(anon_client, code_of(sent_emails[-1]))
    assert response.status_code == 400
    assert "hết hạn" in response.json()["detail"]


async def test_gioi_han_gui_theo_email(anon_client, sent_emails, monkeypatch):
    assert (await send(anon_client)).status_code == 200
    soon = await send(anon_client)
    assert soon.status_code == 429
    assert int(soon.headers["retry-after"]) > 0
    assert "Đợi" in soon.json()["detail"]
    # Bỏ thời gian chờ giữa hai lần: vẫn chỉ được 5 mã mỗi giờ cho một email.
    monkeypatch.setattr(email_login, "RESEND_COOLDOWN", 0)
    for _ in range(4):
        assert (await send(anon_client)).status_code == 200
    limited = await send(anon_client)
    assert limited.status_code == 429
    assert "nhiều mã quá" in limited.json()["detail"]
    assert len(sent_emails) == 5


async def test_gioi_han_gui_theo_ip(anon_client, sent_emails):
    for index in range(email_login.SENDS_PER_IP_HOUR):
        assert (await send(anon_client, f"nguoi{index}{EMAIL[7:15]}@example.com")).status_code == 200
    response = await send(anon_client, "them@example.com")
    assert response.status_code == 429
    assert len(sent_emails) == email_login.SENDS_PER_IP_HOUR


async def test_gioi_han_thu_ma_theo_ip(anon_client, sent_emails, monkeypatch):
    monkeypatch.setattr(email_login, "VERIFY_PER_IP_HOUR", 3)
    for _ in range(3):
        await verify(anon_client, "123456")
    response = await verify(anon_client, "123456")
    assert response.status_code == 429


def test_ip_chi_tin_cf_connecting_ip_khi_qua_tunnel():
    def request(host: str, header: str = "203.0.113.9"):
        return SimpleNamespace(client=SimpleNamespace(host=host), headers={"cf-connecting-ip": header})

    assert email_login.client_ip(request("127.0.0.1")) == "203.0.113.9"
    assert email_login.client_ip(request("::1")) == "203.0.113.9"
    # Kết nối thẳng từ ngoài thì header do người gửi tự đặt, không tin.
    assert email_login.client_ip(request("198.51.100.4")) == "198.51.100.4"


@pytest.mark.parametrize("email", ["", "khong-co-a-cong", "a@b", "a b@example.com", "x@example.com\r\nBcc: y@z.com"])
async def test_email_sai_dang(anon_client, sent_emails, email):
    response = await send(anon_client, email)
    assert response.status_code == 400
    assert sent_emails == []


@pytest.mark.parametrize("code", ["12345", "abcdef", "1234567", ""])
async def test_ma_sai_dang(anon_client, code):
    response = await verify(anon_client, code)
    assert response.status_code == 400
    assert response.json()["detail"] == "Mã gồm đúng 6 chữ số."


async def test_chua_cau_hinh_resend(anon_client, monkeypatch):
    monkeypatch.setattr(config, "RESEND_API_KEY", "")
    assert (await send(anon_client)).status_code == 503
    assert (await verify(anon_client, "123456")).status_code == 503
    assert auth.available_providers()["email"] is False


async def test_gui_thu_loi_thi_bao_502_va_bo_ma(anon_client, monkeypatch):
    async def broken(*args, **kwargs):
        raise email_login.EmailError

    monkeypatch.setattr(email_login, "deliver", broken)
    response = await send(anon_client)
    assert response.status_code == 502
    assert response.json()["detail"] == "Chưa gửi được thư. Thử lại sau ít phút nhé."
    assert await email_login.store.current_code(email_login.email_hash(EMAIL.lower())) is None


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

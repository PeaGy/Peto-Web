"""Dọn dữ liệu tài khoản khách cũ (ops.purge_guests) sau khi bỏ đăng nhập khách ngày 6/10/2026."""
import sqlite3

import storage as db
from core.config import DB_PATH, UPLOAD_DIR
from conftest import TEST_OWNER
from ops import purge_guests

GUEST = "guest:" + "c" * 32


async def seed(owner: str, name: str):
    conversation = await db.create_conversation(owner)
    message = await db.add_message(conversation, "user", "chào")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload = UPLOAD_DIR / f"{name}.txt"
    upload.write_text("x", encoding="utf-8")
    await db.add_attachment(attachment_id=f"{name}-a", owner=owner, conversation_id=conversation, message_id=message,
                            filename="a.txt", mime="text/plain", kind="file", size=1, path=str(upload))
    job = await db.create_imagine_job(owner=owner, prompt="mèo", quality="fast", resolution="1k", aspect_ratio="1:1")
    image = UPLOAD_DIR / f"{name}.png"
    image.write_bytes(b"png")
    await db.add_imagine_image(image_id=f"{name}-i", job_id=job, owner=owner, mime="image/png", path=str(image))
    await db.upsert_user(owner=owner, provider=owner.split(":")[0], username=name, display_name=name, avatar_url="")
    return conversation, upload, image


def rows(sql: str, *params):
    with sqlite3.connect(DB_PATH) as connection:
        return connection.execute(sql, params).fetchall()


async def test_dry_run_counts_then_yes_removes_only_guest_rows_and_their_files(client, tmp_path, capsys, monkeypatch):
    guest_chat, guest_upload, guest_image = await seed(GUEST, "khach")
    kept_chat, kept_upload, kept_image = await seed(TEST_OWNER, "giu")
    # Tệp khách nằm ngoài thư mục tải lên thì không bao giờ bị xóa.
    outside = tmp_path / "ngoai.txt"
    outside.write_text("giữ", encoding="utf-8")
    rows_before = rows("SELECT COUNT(*) FROM messages WHERE conversation_id=?", guest_chat)[0][0]
    assert rows_before == 1
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("UPDATE attachments SET path=? WHERE id='khach-a'", (str(outside),))

    monkeypatch.setattr("sys.argv", ["purge_guests"])
    assert purge_guests.main() == 0
    assert "Chạy thử" in capsys.readouterr().out
    assert rows("SELECT COUNT(*) FROM users WHERE owner=?", GUEST)[0][0] == 1, "chạy thử không xóa gì"

    monkeypatch.setattr("sys.argv", ["purge_guests", "--yes"])
    assert purge_guests.main() == 0
    for table in ("users", "conversations", "attachments", "imagine_jobs", "imagine_images"):
        assert rows(f"SELECT COUNT(*) FROM {table} WHERE owner LIKE 'guest:%'")[0][0] == 0, table
    assert rows("SELECT COUNT(*) FROM messages WHERE conversation_id=?", guest_chat)[0][0] == 0, "tin nhắn theo khóa ngoại"
    assert not guest_image.exists() and outside.exists() and guest_upload.exists()
    assert kept_upload.exists() and kept_image.exists()
    assert rows("SELECT COUNT(*) FROM messages WHERE conversation_id=?", kept_chat)[0][0] == 1
    assert "Bỏ qua 1 tệp" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["purge_guests"])
    assert purge_guests.main() == 0
    assert "Không còn dữ liệu khách nào." in capsys.readouterr().out

"""Khởi tạo và nâng cấp schema; giữ dữ liệu từ các phiên bản cũ."""

from __future__ import annotations
import aiosqlite
from storage.documents import init_tables as init_document_tables
from storage.projects import init_tables as init_project_tables
from storage import connection as db_connection


async def init_db() -> None:
    db_connection.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with db_connection.connect() as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_owner "
            "ON conversations(owner, updated_at DESC)"
        )
        conversation_columns = await (await db.execute("PRAGMA table_info(conversations)")).fetchall()
        for name, definition in [('pinned', 'INTEGER NOT NULL DEFAULT 0'), ('archived', 'INTEGER NOT NULL DEFAULT 0'), ('branch_group', "TEXT NOT NULL DEFAULT ''")]:
            if name not in {column[1] for column in conversation_columns}:
                await db.execute(f'ALTER TABLE conversations ADD COLUMN {name} {definition}')
        if "title_state" not in {column[1] for column in conversation_columns}:
            # Existing names have unknown provenance: do not overwrite them.
            await db.execute("ALTER TABLE conversations ADD COLUMN title_state TEXT NOT NULL DEFAULT 'locked'")
            await db.execute("ALTER TABLE conversations ADD COLUMN title_attempts INTEGER NOT NULL DEFAULT 0")
        await db.execute("UPDATE conversations SET title_state='temporary' WHERE title_state='pending'")
        if "mode" not in {column[1] for column in conversation_columns}:
            # Tab Companion có mạch trò chuyện riêng; hội thoại có từ trước đều thuộc tab Trò chuyện.
            await db.execute("ALTER TABLE conversations ADD COLUMN mode TEXT NOT NULL DEFAULT 'chat'")
        if "persona" not in {column[1] for column in conversation_columns}:
            # "assistant" hoặc "roleplay", chọn lúc bắt đầu hội thoại; hội thoại cũ đều là trợ lý.
            await db.execute("ALTER TABLE conversations ADD COLUMN persona TEXT NOT NULL DEFAULT 'assistant'")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_conversations_archive ON conversations(owner, mode, archived, pinned DESC, updated_at DESC, id DESC)")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation "
            "ON messages(conversation_id, id)"
        )
        # Migration bổ sung, giữ nguyên tin nhắn trong database hiện có.
        columns = await (await db.execute("PRAGMA table_info(messages)")).fetchall()
        if "status" not in {column[1] for column in columns}:
            await db.execute(
                "ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'complete'"
            )
        if "sources" not in {column[1] for column in columns}:
            await db.execute("ALTER TABLE messages ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'")
        if 'artifacts' not in {column[1] for column in columns}:
            await db.execute("ALTER TABLE messages ADD COLUMN artifacts TEXT NOT NULL DEFAULT '[]'")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                mime TEXT NOT NULL,
                kind TEXT NOT NULL,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_attachments_message "
            "ON attachments(message_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_attachments_conversation "
            "ON attachments(conversation_id)"
        )

        attachment_columns = await (await db.execute("PRAGMA table_info(attachments)")).fetchall()
        if "document" not in {column[1] for column in attachment_columns}:
            await db.execute("ALTER TABLE attachments ADD COLUMN document TEXT NOT NULL DEFAULT ''")

        # Danh tính đã được máy chủ xác minh qua OAuth Discord. Đây là chỗ
        # duy nhất ánh xạ người dùng web sang Discord user ID — và là nền cho
        # việc liên kết trí nhớ sau này, NẾU được duyệt. Không bao giờ nhận
        # discord_id do trình duyệt gửi lên.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                owner TEXT PRIMARY KEY,
                provider TEXT NOT NULL DEFAULT 'discord',
                discord_id TEXT UNIQUE,
                username TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                first_login_at REAL NOT NULL,
                last_login_at REAL NOT NULL
            )
            """
        )
        # Bảng cũ có `discord_id NOT NULL UNIQUE`, không chứa nổi tài khoản
        # Google hay khách. Nới NOT NULL thì SQLite bắt dựng lại bảng chứ không
        # ALTER được — nhiều NULL vẫn hợp lệ với UNIQUE nên ràng buộc "một tài
        # khoản Discord một dòng" giữ nguyên. Chỉ chạy khi thiếu cột `provider`.
        user_columns = await (await db.execute("PRAGMA table_info(users)")).fetchall()
        if "provider" not in {column[1] for column in user_columns}:
            await db.execute(
                """
                CREATE TABLE users_moi (
                    owner TEXT PRIMARY KEY,
                    provider TEXT NOT NULL DEFAULT 'discord',
                    discord_id TEXT UNIQUE,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT NOT NULL DEFAULT '',
                    first_login_at REAL NOT NULL,
                    last_login_at REAL NOT NULL
                )
                """
            )
            await db.execute(
                """
                INSERT INTO users_moi (owner, provider, discord_id, username,
                                       display_name, avatar_url,
                                       first_login_at, last_login_at)
                     SELECT owner, 'discord', discord_id, username,
                            display_name, avatar_url,
                            first_login_at, last_login_at
                       FROM users
                """
            )
            await db.execute("DROP TABLE users")
            await db.execute("ALTER TABLE users_moi RENAME TO users")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS imagine_jobs (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                prompt TEXT NOT NULL,
                quality TEXT NOT NULL,
                resolution TEXT NOT NULL,
                aspect_ratio TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_imagine_jobs_owner "
            "ON imagine_jobs(owner, created_at DESC)"
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS imagine_images (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                owner TEXT NOT NULL,
                mime TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (job_id) REFERENCES imagine_jobs(id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_imagine_images_job "
            "ON imagine_images(job_id)"
        )
        # Ảnh cũ luôn là kết quả; ảnh gốc của lượt sửa được lưu riêng trong cùng bảng.
        image_columns = await (await db.execute("PRAGMA table_info(imagine_images)")).fetchall()
        image_column_names = {column[1] for column in image_columns}
        if "kind" not in image_column_names:
            await db.execute("ALTER TABLE imagine_images ADD COLUMN kind TEXT NOT NULL DEFAULT 'output'")
        # Ảnh đã thích trong thư viện. Lưu ở máy chủ để mọi thiết bị của tài khoản đều thấy.
        if "liked" not in image_column_names:
            await db.execute("ALTER TABLE imagine_images ADD COLUMN liked INTEGER NOT NULL DEFAULT 0")
        # Hồ sơ người dùng tự điền trong Cài đặt. Tách khỏi `users` vì bảng đó bị
        # ghi đè bằng dữ liệu Discord/Google mỗi lần đăng nhập, còn hồ sơ là của họ.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                owner TEXT PRIMARY KEY,
                full_name TEXT NOT NULL DEFAULT '',
                nickname TEXT NOT NULL DEFAULT '',
                occupation TEXT NOT NULL DEFAULT '',
                instructions TEXT NOT NULL DEFAULT '',
                updated_at REAL NOT NULL
            )
            """
        )
        # Peto Agent: mỗi máy chạy CLI có một token riêng; chỉ lưu mã băm, không lưu token.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_devices (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                last_used_at REAL NOT NULL,
                revoked_at REAL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_devices_owner "
            "ON agent_devices(owner, last_used_at DESC)"
        )
        # Số bước agent đã dùng theo ngày (giờ PETO_DEFAULT_TIMEZONE) cho mỗi tài khoản.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_usage (
                owner TEXT NOT NULL,
                day TEXT NOT NULL,
                steps INTEGER NOT NULL DEFAULT 0,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (owner, day)
            )
            """
        )
        # Số ký tự Giọng Peto (nguồn giọng chính thức) đã dùng theo tháng (giờ PETO_DEFAULT_TIMEZONE) cho mỗi tài khoản.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_usage (
                owner TEXT NOT NULL,
                month TEXT NOT NULL,
                chars INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (owner, month)
            )
            """
        )
        # Tài khoản đã xác nhận đủ 18 tuổi để bật chế độ nhập vai. Tách khỏi `users` (bị ghi đè mỗi lần đăng nhập).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS roleplay_consents (
                owner TEXT PRIMARY KEY,
                confirmed_at REAL NOT NULL
            )
            """
        )
        # Trí nhớ Companion: điều Peto tự rút ra từ lời người dùng kể trong tab Companion (companion_memory.py). Tách khỏi
        # hồ sơ tự điền, và không liên quan trí nhớ của bot Discord (chỉ đọc, không bao giờ ghi ngược).
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS companion_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_companion_memories_owner ON companion_memories(owner, id)"
        )
        # Bật/tắt theo người dùng, tin nhắn Companion cuối cùng đã đọc để ghi nhớ (id tin nhắn tăng dần), và `since`:
        # tin có id từ đó trở xuống (có từ trước khi có trí nhớ, hay nói lúc đang tắt) không bao giờ được tóm tắt.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS companion_memory_state (
                owner TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                cursor INTEGER NOT NULL DEFAULT 0,
                since INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            )
            """
        )
        state_columns = await (await db.execute("PRAGMA table_info(companion_memory_state)")).fetchall()
        if "since" not in {column[1] for column in state_columns}:
            await db.execute("ALTER TABLE companion_memory_state ADD COLUMN since INTEGER NOT NULL DEFAULT 0")
            # Tin đã đọc để ghi nhớ thì coi như đã qua; không tóm tắt ngược lịch sử cũ.
            await db.execute("UPDATE companion_memory_state SET since = cursor")
        # Tóm tắt phần trò chuyện Companion đã trôi khỏi lịch sử gửi kèm, theo từng mạch: xóa mạch ("Bắt đầu lại") là
        # xóa luôn bản tóm tắt. `upto` là id tin cuối cùng đã tóm tắt hoặc đã bỏ qua.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS companion_summaries (
                conversation_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                upto INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        await init_document_tables(db)
        await init_project_tables(db)
        await db.commit()

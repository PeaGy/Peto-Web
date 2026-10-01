"""Sao lưu dữ liệu giả, phục hồi độc lập và tổng hợp log không lộ dữ liệu người dùng."""
from contextlib import closing
import io
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import zipfile

import pytest

from ops import backup, report


@pytest.fixture
def dataset(tmp_path):
    uploads = tmp_path / "data/uploads"
    uploads.mkdir(parents=True)
    attachment = uploads / "chat/file.txt"
    attachment.parent.mkdir()
    attachment.write_text("Tài liệu của người dùng", encoding="utf-8")
    image = uploads / "imagine/job/image.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"anh-gia")
    database = tmp_path / "data/peto_web.db"
    with closing(sqlite3.connect(database)) as db:
        db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE conversations(id TEXT, owner TEXT, title TEXT);
            CREATE TABLE messages(content TEXT, status TEXT);
            CREATE TABLE attachments(path TEXT);
            CREATE TABLE imagine_images(path TEXT);
            CREATE TABLE document_assets(docx BLOB, pdf BLOB);
            CREATE TABLE agent_usage(owner TEXT, day TEXT, steps INTEGER, input_tokens INTEGER, output_tokens INTEGER);
            CREATE TABLE voice_usage(owner TEXT, month TEXT, chars INTEGER);
            CREATE TABLE speech_budget(month TEXT, micros INTEGER);
            INSERT INTO conversations VALUES ('chat', 'discord:private', 'Tên riêng');
            INSERT INTO messages VALUES ('Nội dung riêng', 'incomplete');
            INSERT INTO document_assets VALUES (X'010203', X'0405');
            INSERT INTO agent_usage VALUES ('discord:private', '2026-10-01', 3, 100, 10);
            INSERT INTO agent_usage VALUES ('google:private', '2026-10-01', 2, 50, 5);
            INSERT INTO voice_usage VALUES ('discord:private', '2026-10', 300);
            INSERT INTO speech_budget VALUES ('2026-10', 500000);
        """)
        db.execute("INSERT INTO attachments VALUES (?)", (str(attachment),))
        db.execute("INSERT INTO imagine_images VALUES (?)", (str(image),))
        db.commit()
    (database.parent / "xai_tokens.json").write_text("SECRET-TOKEN")
    (tmp_path / ".env").write_text("SECRET-KEY")
    return database, uploads, tmp_path / "backups"


def test_backup_restore_preserves_data_and_rebases_only_restored_files(dataset, tmp_path):
    database, uploads, output = dataset
    original = database.read_bytes()
    archive = backup.create_backup(database, uploads, output, offline=True)
    manifest = backup.verify_backup(archive)
    assert manifest["tables"]["messages"] == 1
    with zipfile.ZipFile(archive) as saved:
        assert set(saved.namelist()) == {"manifest.json", "database/peto_web.db", "uploads/chat/file.txt", "uploads/imagine/job/image.png"}
        assert "SECRET" not in saved.read("manifest.json").decode()
    restored = tmp_path / "restore-drill"
    backup.restore_backup(archive, restored)
    with closing(backup.readonly(restored / "database/peto_web.db")) as db:
        assert db.execute("SELECT content, status FROM messages").fetchone() == ("Nội dung riêng", "incomplete")
        assert db.execute("SELECT docx, pdf FROM document_assets").fetchone() == (b"\1\2\3", b"\4\5")
        assert Path(db.execute("SELECT path FROM attachments").fetchone()[0]).read_text(encoding="utf-8") == "Tài liệu của người dùng"
        assert Path(db.execute("SELECT path FROM imagine_images").fetchone()[0]).is_relative_to(restored)
    assert database.read_bytes() == original
    with pytest.raises(ValueError, match="không ghi đè"):
        backup.restore_backup(archive, restored)


def test_sqlite_backup_captures_uncheckpointed_wal(dataset):
    database, uploads, output = dataset
    with closing(sqlite3.connect(database)) as writer:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO messages VALUES ('Trong WAL', 'complete')")
        writer.commit()
        assert Path(str(database) + "-wal").stat().st_size > 0
        archive = backup.create_backup(database, uploads, output, offline=True)
        assert backup.verify_backup(archive)["tables"]["messages"] == 2


def test_backup_refuses_offline_missing_db_nested_output_and_missing_files(dataset):
    database, uploads, output = dataset
    with pytest.raises(ValueError, match="offline"):
        backup.create_backup(database, uploads, output, offline=False)
    with pytest.raises(ValueError, match="Không tìm thấy"):
        backup.create_backup(database.with_name("missing.db"), uploads, output, offline=True)
    with pytest.raises(ValueError, match="bên ngoài"):
        backup.create_backup(database, uploads, uploads / "backups", offline=True)
    (uploads / "chat/file.txt").unlink()
    with pytest.raises(ValueError, match="bị thiếu"):
        backup.create_backup(database, uploads, output, offline=True)
    assert not list(output.glob("*.zip"))
    assert not (output / ".peto-backup-lock").exists()


def test_backup_rejects_reference_outside_uploads(dataset, tmp_path):
    database, uploads, output = dataset
    with closing(sqlite3.connect(database)) as db:
        db.execute("UPDATE attachments SET path=?", (str(tmp_path / ".env"),))
        db.commit()
    with pytest.raises(ValueError, match="ngoài thư mục"):
        backup.create_backup(database, uploads, output, offline=True)


def test_retention_only_after_success_and_keeps_unrelated_files(dataset):
    database, uploads, output = dataset
    first = backup.create_backup(database, uploads, output, offline=True, keep=2)
    second = backup.create_backup(database, uploads, output, offline=True, keep=2)
    unrelated = output / "important.zip"
    unrelated.write_text("Không xóa")
    third = backup.create_backup(database, uploads, output, offline=True, keep=2)
    assert not first.exists() and second.exists() and third.exists() and unrelated.exists()
    (uploads / "chat/file.txt").unlink()
    with pytest.raises(ValueError):
        backup.create_backup(database, uploads, output, offline=True, keep=1)
    assert second.exists() and third.exists()


def rewrite_zip(source, destination, edit):
    with zipfile.ZipFile(source) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    edit(entries)
    with zipfile.ZipFile(destination, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


@pytest.mark.parametrize("damage", ["hash", "missing", "traversal", "absolute", "backslash", "case_collision"])
def test_verify_rejects_damaged_or_unsafe_archives(dataset, tmp_path, damage):
    database, uploads, output = dataset
    original = backup.create_backup(database, uploads, output, offline=True)
    damaged = tmp_path / "damaged.zip"
    def edit(entries):
        if damage == "hash":
            entries["uploads/chat/file.txt"] = b"x" * len(entries["uploads/chat/file.txt"])
        elif damage == "missing":
            del entries["uploads/chat/file.txt"]
        else:
            name = {"traversal": "uploads/../../escape", "absolute": "/escape", "backslash": "uploads/..\\escape", "case_collision": "uploads/chat/FILE.txt"}[damage]
            entries[name] = entries["uploads/chat/file.txt"]
            manifest = json.loads(entries["manifest.json"])
            manifest["files"][name] = manifest["files"]["uploads/chat/file.txt"]
            entries["manifest.json"] = json.dumps(manifest).encode()
    rewrite_zip(original, damaged, edit)
    target = tmp_path / "unsafe-restore"
    with pytest.raises(ValueError):
        backup.restore_backup(damaged, target)
    assert not target.exists() and not (tmp_path / "escape").exists()


def test_concurrent_lock_refuses_and_keeps_existing_lock(dataset):
    database, uploads, output = dataset
    output.mkdir()
    lock = output / ".peto-backup-lock"
    lock.mkdir()
    with pytest.raises(ValueError, match="khóa"):
        backup.create_backup(database, uploads, output, offline=True)
    assert lock.exists()


def test_report_groups_percentiles_and_missing_usage_without_private_data():
    lines = [
        "Nội dung riêng discord:private SECRET-KEY",
        "INFO chat_timing model=peto effort=low mode=chat queue_ms=2 prepare_ms=3 first_text_ms=100 total_ms=500 search=False complete=True outcome=complete",
        "INFO chat_timing model=peto effort=low mode=chat queue_ms=None prepare_ms=None first_text_ms=None total_ms=1000 search=False complete=False outcome=timeout",
        "INFO agent_timing model=sol effort=high mode=agent first_text_ms=20 total_ms=100 complete=True outcome=complete",
        "INFO model_usage service=OpenAI model=test-model purpose=chat round=1 elapsed_ms=100 complete=True input_tokens=100 output_tokens=10 cached_tokens=20 reasoning_tokens=5 search_calls_seen=1",
        "INFO model_usage service=OpenAI model=test-model purpose=chat round=2 elapsed_ms=200 complete=False input_tokens=None output_tokens=None cached_tokens=None reasoning_tokens=None search_calls_seen=0",
        "INFO chat_timing model=bad effort=low mode=chat total_ms=oops complete=False",
    ]
    stats = report.summarize(lines, {"test-model": {"input": 2, "cached_input": 1, "output": 5}})
    chat = next(row for row in stats["timings"] if row["mode"] == "chat")
    assert chat["latency"]["total_ms"] == {"samples": 2, "p50_ms": 500, "p95_ms": 1000}
    assert chat["latency"]["first_text_ms"]["samples"] == 1
    assert chat["outcomes"] == {"complete": 1, "timeout": 1}
    usage = stats["model_usage"][0]
    assert usage["priced_calls"] == 1 and usage["missing_usage"] == 1
    assert usage["estimated_token_usd"] == .00023
    assert stats["malformed_records"] == 1
    rendered = report.format_report(stats)
    assert not any(secret in rendered for secret in ("discord:private", "SECRET-KEY", "Nội dung riêng"))
    assert report.summarize(lines)["model_usage"][0]["estimated_token_usd"] is None


@pytest.mark.parametrize("prices", [{"model": {"input": -1, "cached_input": 0, "output": 1}},
                                   {"model": {"input": float("inf"), "cached_input": 0, "output": 1}},
                                   {"model": {"input": True, "cached_input": 0, "output": 1}}, {"model": {"input": 1}}])
def test_report_rejects_bad_rates(prices):
    with pytest.raises(ValueError):
        report.summarize([], prices)


def test_stored_usage_is_readonly_aggregate_and_not_invoice(dataset, tmp_path):
    database, _, _ = dataset
    before = database.read_bytes()
    totals = report.stored_usage(database)
    assert totals["agent_daily"] == [{"day": "2026-10-01", "steps": 5, "input_tokens": 150, "output_tokens": 15}]
    assert totals["speech_reserved"] == [{"month": "2026-10", "reserved_usd": .5}]
    assert "private" not in json.dumps(totals)
    assert database.read_bytes() == before
    missing = tmp_path / "no.db"
    with pytest.raises(sqlite3.Error):
        report.stored_usage(missing)
    assert not missing.exists()


def test_logging_configuration_is_idempotent_and_emits_once():
    from core.operational_logging import configure_operational_logging
    logger = logging.getLogger("peto_web")
    old_handlers, old_level, old_propagate = logger.handlers[:], logger.level, logger.propagate
    try:
        logger.handlers = []
        configure_operational_logging()
        configure_operational_logging()
        assert len(logger.handlers) == 1
        stream = io.StringIO()
        logger.handlers[0].setStream(stream)
        logging.getLogger("peto_web.xai").info("model_usage model=test")
        assert stream.getvalue().count("model_usage") == 1
    finally:
        logger.handlers, logger.level, logger.propagate = old_handlers, old_level, old_propagate


async def test_backup_of_current_schema_restores_and_serves_history(tmp_path, monkeypatch):
    from storage import connection, schema
    import storage
    database = tmp_path / "real-schema.db"
    monkeypatch.setattr(connection, "DB_PATH", database)
    await schema.init_db()
    conversation = await storage.create_conversation("discord:test")
    await storage.add_message(conversation, "user", "Lịch sử được giữ nguyên")
    archive = backup.create_backup(database, tmp_path / "uploads", tmp_path / "backups", offline=True)
    restored = tmp_path / "restored"
    backup.restore_backup(archive, restored)
    monkeypatch.setattr(connection, "DB_PATH", restored / "database/peto_web.db")
    await schema.init_db()
    rows = await storage.get_messages("discord:test", conversation)
    assert rows[0]["content"] == "Lịch sử được giữ nguyên"
    assert await storage.get_messages("discord:other", conversation) == []


@pytest.mark.parametrize("outcome", ["complete", "provider_error", "timeout"])
async def test_chat_logs_categorical_outcome_without_message_content(client, monkeypatch, caplog, outcome):
    from features.chat import service
    from ai.base import StreamChunk, ProviderError

    class Provider:
        async def stream(self, **kwargs):
            yield StreamChunk("text", "Đáp án riêng tư")
            if outcome == "provider_error":
                raise ProviderError("Dịch vụ thử bị lỗi")
            if outcome == "timeout":
                raise TimeoutError

    monkeypatch.setattr(service, "get_provider", lambda model="peto": Provider())
    with caplog.at_level(logging.INFO, logger="peto_web"):
        response = await client.post("/api/chat", json={"message": "Câu hỏi riêng tư", "mode": "companion"})
    assert response.status_code == 200
    records = [record.getMessage() for record in caplog.records if record.getMessage().startswith("chat_timing ")]
    assert len(records) == 1 and f"outcome={outcome}" in records[0]
    assert "riêng tư" not in records[0] and "owner=" not in records[0]
    stats = report.summarize(records)
    assert stats["timings"][0]["outcomes"] == {outcome: 1}


@pytest.fixture
def backup_script(tmp_path):
    bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
    if not Path(bash).is_file():
        pytest.skip("Máy kiểm tra chưa có bash để thử script VPS.")
    root = Path(__file__).resolve().parents[2]
    source = (root / "deploy/backup-peto.sh").read_text(encoding="utf-8")
    project = tmp_path / "project"
    (project / "backend").mkdir(parents=True)
    marker = tmp_path / "restart-marker"
    trace = tmp_path / "trace.txt"
    source = source.replace("project=/home/ubuntu/peto-web", f"project='{project.as_posix()}'")
    source = source.replace("output=/home/ubuntu/peto-backups", f"output='{(tmp_path / 'backups').as_posix()}'")
    source = source.replace("marker=/run/peto-backup-restart", f"marker='{marker.as_posix()}'")
    script = tmp_path / "backup.sh"
    script.write_text(source, encoding="utf-8", newline="\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    commands = {
        "systemctl": '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$PETO_TEST_TRACE"\nif [[ "$1" == "is-active" ]]; then exit "$PETO_TEST_ACTIVE"; fi\n',
        "runuser": '#!/usr/bin/env bash\necho backup >> "$PETO_TEST_TRACE"\nexit "$PETO_TEST_BACKUP_EXIT"\n',
    }
    for name, content in commands.items():
        command = bin_dir / name
        command.write_text(content, encoding="utf-8", newline="\n")
        command.chmod(0o700)
    env = {**os.environ, "PETO_TEST_TRACE": trace.as_posix(), "PETO_TEST_ACTIVE": "0", "PETO_TEST_BACKUP_EXIT": "0"}
    # Bash trên Windows dùng dấu hai chấm và đường dẫn /c/... trong PATH.
    bin_path = bin_dir.as_posix()
    if os.name == "nt":
        bin_path = "/" + bin_path[0].lower() + bin_path[2:]
    invoke = 'export PATH="$PETO_TEST_BIN:$PATH"; exec bash "$@"'
    env["PETO_TEST_BIN"] = bin_path
    return bash, invoke, script, marker, trace, env


@pytest.mark.parametrize("active, failed", [(True, False), (True, True), (False, False), (False, True)])
def test_backup_service_resumes_only_previously_running_web(backup_script, active, failed):
    bash, invoke, script, marker, trace, env = backup_script
    env["PETO_TEST_ACTIVE"] = "0" if active else "1"
    env["PETO_TEST_BACKUP_EXIT"] = "1" if failed else "0"
    result = subprocess.run([bash, "-c", invoke, "test", script.as_posix()], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == int(failed), result.stderr
    calls = trace.read_text().splitlines()
    assert calls[:3] == ["is-active --quiet peto-web.service", "stop peto-web.service", "backup"]
    assert ("start peto-web.service" in calls) == active
    assert not marker.exists()


def test_stop_post_recovers_abnormal_exit_marker(backup_script):
    bash, invoke, script, marker, trace, env = backup_script
    marker.touch()
    result = subprocess.run([bash, "-c", invoke, "test", script.as_posix(), "--resume"], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert trace.read_text().splitlines() == ["start peto-web.service"]
    assert not marker.exists()

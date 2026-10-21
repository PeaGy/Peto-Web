"""Phát hành nhiều nguồn, mốc M6: sao lưu hồ sơ khi đổi bản peto, công tắc tắt nguồn trực tiếp (máy chủ và config.json)
mà không mất kết nối hay hội thoại, và không ghi đè dữ liệu bản này chưa hiểu."""

from __future__ import annotations

import json

import pytest
from conftest import FakeUI
from test_direct_source import KEY, serve
from test_loop_client import Handler as PetoHandler

from peto_agent import __main__ as cli
from peto_agent import config, connections, credentials, migration
from peto_agent import model_catalog as catalog

needs_dpapi = pytest.mark.skipif(not credentials.available(), reason="Kho khóa DPAPI chỉ có trên Windows.")


def test_profile_is_backed_up_once_per_version_change(agent_home):
    config.save({"server": "https://peto.example", "model": "sol"})
    (agent_home / "connections.json").write_text('{"version": 1, "connections": []}', encoding="utf-8")
    first = migration.backup_on_change("0.33.3")
    assert first is not None and first.name.endswith("-cu-to-0.33.3")
    assert json.loads((first / "config.json").read_text(encoding="utf-8")) == {"server": "https://peto.example",
                                                                               "model": "sol"}
    assert (first / "connections.json").is_file() and not (first / "credentials").exists(), "không nhân bản bí mật"
    assert config.load()["cli_version"] == "0.33.3" and config.load()["config_schema"] == migration.SCHEMA
    assert migration.backup_on_change("0.33.3") is None, "cùng bản thì không sao lưu lại"
    for number in range(4, 12):
        assert migration.backup_on_change(f"0.33.{number}") is not None
    assert len(list(migration.backups_dir().iterdir())) == migration.KEEP


def test_main_backs_up_before_anything_writes(agent_home, capsys):
    config.save({"server": "https://peto.example"})
    assert cli.main(["models", "--json"]) == 1, "không có nguồn nào"
    assert config.load()["cli_version"] == cli.__version__
    assert len(list(migration.backups_dir().iterdir())) == 1


def test_unknown_connection_rows_survive_and_newer_files_are_not_overwritten(agent_home):
    future = {"id": "anthropic-1", "provider": "anthropic", "label": "Claude", "endpoint": "https://api.anthropic.com",
              "created_at": 1, "models": ["x"], "extra": {"note": "của bản mới hơn"}}
    agent_home.mkdir(parents=True, exist_ok=True)
    (agent_home / "connections.json").write_text(json.dumps({"version": 1, "connections": [future]}), encoding="utf-8")
    assert connections.load_all() == [], "bản này bỏ qua dòng không hiểu"
    connections.update_models("khong-co", ())
    rows = json.loads((agent_home / "connections.json").read_text(encoding="utf-8"))["connections"]
    assert rows == [future], "ghi lại vẫn giữ nguyên dòng không hiểu"

    (agent_home / "connections.json").write_text(json.dumps({"version": 2, "items": []}), encoding="utf-8")
    with pytest.raises(connections.ConnectionError_):
        connections._write([])
    assert json.loads((agent_home / "connections.json").read_text(encoding="utf-8"))["version"] == 2


@needs_dpapi
def test_a_locally_disabled_source_hides_its_models_and_keeps_the_connection(agent_home):
    item = connections.add("openai", KEY, endpoint="https://api.openai.com/v1", models=("gpt-6-luna",))
    assert [row["key"] for row in catalog.direct_models()] == ["gpt-6-luna"]
    config.save({**config.load(), "disabled_sources": ["openai-key"]})
    assert catalog.direct_models() == [] and connections.get(item.id) is not None
    ui = FakeUI()
    assert cli.connect(ui, "openai", read_secret=lambda prompt: KEY) == 1 and "tạm tắt" in ui.text


@needs_dpapi
def test_the_server_can_turn_off_a_direct_source_without_losing_the_default(project, monkeypatch):
    me = {"account": "Bình", "steps_used": 1, "steps_limit": 200, "agent_features": [],
          "models": [{"key": "peto", "label": "Peto", "step_cost": 1}], "disabled_sources": ["openai-key"]}
    peto = serve(PetoHandler, reply=lambda path, body: (200, me) if path == "/api/agent/me" else (404, "Không có"))
    try:
        item = connections.add("openai", KEY, endpoint="https://api.openai.com/v1", models=("gpt-6-luna",))
        selection = {"source": "openai-key", "connection": item.id, "model": "gpt-6-luna"}
        config.save({"server": peto.url, "token": "peto_token_thu", "selection": selection})
        monkeypatch.chdir(project)
        ui = FakeUI(answers=["/model gpt-6-luna", "/exit"])
        assert cli.session(ui) == 0
        assert "Nguồn OpenAI đang tạm tắt từ máy chủ Peto nên phiên này dùng Peto" in ui.text
        assert "Tài khoản này không dùng được model đó" in ui.text, "model của nguồn tắt không chọn được"
        assert config.load()["selection"] == selection, "bật lại thì mặc định cũ dùng được ngay"
        me["disabled_sources"] = []
        again = FakeUI(answers=["/exit"])
        assert cli.session(again) == 0 and "GPT-6 Luna" in again.text and "tạm tắt" not in again.text
    finally:
        peto.shutdown()
        peto.server_close()

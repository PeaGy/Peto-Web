"""Bộ cài một dòng của lệnh peto: script PowerShell và gói wheel máy chủ tự đóng."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import subprocess
import sys
import tomllib
import zipfile

import pytest

from features.agent import install as agent_install

ORIGIN = "https://peto.example"


def script_value(script: str, name: str) -> str:
    match = re.search(rf"^\s*\${name} = '([^']*)'", script, re.MULTILINE)
    assert match, name
    return match.group(1)


async def test_script_is_filled_for_the_address_the_user_called(anon_client):
    response = await anon_client.get(f"{ORIGIN}/install.ps1")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    script = response.text
    assert "__PETO_" not in script and "Cài peto từ" in script
    assert script_value(script, "PetoServer") == ORIGIN
    name = script_value(script, "WheelName")
    assert script_value(script, "WheelUrl") == f"{ORIGIN}/api/agent/download/{name}"

    download = await anon_client.get(f"{ORIGIN}/api/agent/download/{name}")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/octet-stream"
    assert hashlib.sha256(download.content).hexdigest() == script_value(script, "WheelSha256")


async def test_plain_http_is_refused_unless_the_server_runs_on_this_machine(anon_client):
    remote = await anon_client.get("http://peto.example/install.ps1")
    assert remote.status_code == 200 and "HTTPS" in remote.text and "WheelUrl" not in remote.text
    wheel = agent_install.build_wheel("http://peto.example")
    assert (await anon_client.get(f"http://peto.example/api/agent/download/{wheel.filename}")).status_code == 404

    local = (await anon_client.get("http://127.0.0.1:8000/install.ps1")).text
    assert script_value(local, "PetoServer") == "http://127.0.0.1:8000"
    forged = await anon_client.get(f"{ORIGIN}/install.ps1", headers={"Host": "peto.example'; Remove-Item x"})
    assert "WheelUrl" not in forged.text


async def test_only_the_current_package_can_be_downloaded(anon_client):
    assert (await anon_client.get(f"{ORIGIN}/api/agent/download/peto-9.9.9-py3-none-any.whl")).status_code == 404
    assert (await anon_client.get(f"{ORIGIN}/api/agent/download/..%2Fconfig.py")).status_code == 404


def test_wheel_is_reproducible_and_matches_its_record():
    first, second = agent_install.build_wheel(ORIGIN), agent_install.build_wheel(ORIGIN)
    assert first.data == second.data and first.sha256 == second.sha256
    project = tomllib.loads((agent_install.CLI_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    init = (agent_install.CLI_DIR / "peto_agent" / "__init__.py").read_text(encoding="utf-8")
    assert f'__version__ = "{version}"' in init
    assert first.filename == f"peto-{version}-py3-none-any.whl"

    with zipfile.ZipFile(io.BytesIO(first.data)) as archive:
        names = archive.namelist()
        files = {name: archive.read(name) for name in names}
    dist_info = f"peto-{version}.dist-info"
    assert names[-1] == f"{dist_info}/RECORD"
    assert "peto_agent/__main__.py" in files
    # Gói con giao diện terminal (0.16.0) vào wheel đúng một lần dù pyproject ghi cả gói cha lẫn gói con.
    assert "peto_agent/tui/view.py" in files and len(names) == len(set(names))
    assert files['peto_agent/command_catalog.json'] == (agent_install.CLI_DIR / 'peto_agent/command_catalog.json').read_bytes()
    assert not any("__pycache__" in name or name.startswith("tests/") for name in names)
    assert files["peto_agent/default_server.txt"].decode() == f"{ORIGIN}\n"
    assert "peto = peto_agent.__main__:main" in files[f"{dist_info}/entry_points.txt"].decode()
    # CLI phát hành theo MIT (chủ dự án chọn ngày 2026-10-20), kèm thông báo license của phần chuyển từ opencode.
    assert "License: MIT" in files[f"{dist_info}/METADATA"].decode().splitlines()
    licence = files[f"{dist_info}/LICENSE"].decode()
    assert licence.startswith("MIT License") and "Copyright (c) 2025 opencode" in licence
    assert "peto_agent/providers/gateway.py" in files
    # Nguồn trực tiếp (M3) dựng lời nhắc và schema trên máy từ bản chép của máy chủ: wheel phải mang đủ bản chép đó.
    for name in ("__init__", "assembly", "agent_prompts", "core_prompt", "provider_prompts", "tool_schemas"):
        assert f"peto_agent/bundle/{name}.py" in files
    assert "peto_agent/providers/openai_key.py" in files and "peto_agent/credentials.py" in files
    # Phát hành nhiều nguồn (M6): mọi mô-đun của CLI đều vào wheel, kể cả mô-đun mới (đăng nhập ChatGPT, khung nổi…).
    source = {path.relative_to(agent_install.CLI_DIR).as_posix()
              for path in (agent_install.CLI_DIR / "peto_agent").rglob("*.py") if "__pycache__" not in path.parts}
    assert source <= set(files), sorted(source - set(files))
    for line in files[f"{dist_info}/RECORD"].decode().splitlines():
        path, digest, size = line.split(",")
        if path == f"{dist_info}/RECORD":
            continue
        expected = base64.urlsafe_b64encode(hashlib.sha256(files[path]).digest()).rstrip(b"=").decode()
        assert digest == f"sha256={expected}" and int(size) == len(files[path])


def test_pip_installs_the_wheel_and_the_cli_knows_its_server(tmp_path):
    if subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode != 0:
        pytest.skip("Môi trường test không có pip.")
    wheel = agent_install.build_wheel(ORIGIN)
    (tmp_path / wheel.filename).write_bytes(wheel.data)
    target = tmp_path / "target"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--no-index",
         "--no-deps", "--target", str(target), str(tmp_path / wheel.filename)],
        check=True, capture_output=True,
    )
    assert any((target / "bin").glob("peto*"))
    probe = ("from peto_agent import config; import peto_agent.tui.view, peto_agent.providers.gateway; "
             "from peto_agent.bundle import assembly; "
             "assert assembly.prepare({'features': ['explore_v2']}, service='openai', web_search=False, "
             "clock='').tools; print(config.default_server())")
    result = subprocess.run([sys.executable, "-c", probe], cwd=tmp_path, capture_output=True, text=True, check=True,
                            env={**os.environ, "PYTHONPATH": str(target)})
    assert result.stdout.strip() == ORIGIN
    # Chạy lệnh thật từ gói đã cài: thiếu một mô-đun trong gói thì lỗi ngay ở đây.
    version = subprocess.run([sys.executable, "-m", "peto_agent", "--version"], cwd=tmp_path, capture_output=True,
                             text=True, check=True, env={**os.environ, "PYTHONPATH": str(target)})
    assert version.stdout.strip() == f"peto {wheel.filename.split('-')[1]}"
    # Nạp mọi mô-đun của gói đã cài (thiếu tệp hay tài nguyên thì lỗi ở đây), rồi chạy một lệnh đọc cấu hình trong hồ sơ
    # trống: không có nguồn nào thì báo lỗi bình thường, không văng traceback.
    every = ("import importlib, pkgutil, peto_agent; "
             "[importlib.import_module(m.name) for m in pkgutil.walk_packages(peto_agent.__path__, 'peto_agent.')]; "
             "print('ok')")
    loaded = subprocess.run([sys.executable, "-c", every], cwd=tmp_path, capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": str(target)})
    assert loaded.returncode == 0 and loaded.stdout.strip() == "ok", loaded.stderr[-2000:]
    home = tmp_path / "home"
    listed = subprocess.run([sys.executable, "-m", "peto_agent", "models", "--json"], cwd=tmp_path, capture_output=True,
                            text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONPATH": str(target), "PETO_AGENT_HOME": str(home)})
    assert listed.returncode == 1 and "Traceback" not in listed.stderr, listed.stderr[-2000:]

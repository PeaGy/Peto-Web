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

import agent_install

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
    assert not any("__pycache__" in name or name.startswith("tests/") for name in names)
    assert files["peto_agent/default_server.txt"].decode() == f"{ORIGIN}\n"
    assert "peto = peto_agent.__main__:main" in files[f"{dist_info}/entry_points.txt"].decode()
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
    probe = "from peto_agent import config; print(config.default_server())"
    result = subprocess.run([sys.executable, "-c", probe], cwd=tmp_path, capture_output=True, text=True, check=True,
                            env={**os.environ, "PYTHONPATH": str(target)})
    assert result.stdout.strip() == ORIGIN
    # Chạy lệnh thật từ gói đã cài: thiếu một mô-đun trong gói thì lỗi ngay ở đây.
    version = subprocess.run([sys.executable, "-m", "peto_agent", "--version"], cwd=tmp_path, capture_output=True,
                             text=True, check=True, env={**os.environ, "PYTHONPATH": str(target)})
    assert version.stdout.strip() == f"peto {wheel.filename.split('-')[1]}"

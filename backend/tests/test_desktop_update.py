"""Nguồn cập nhật tự động của ứng dụng Peto Agent: đọc stable.yml của bản phát hành mới nhất (GitHub giả bằng
httpx.MockTransport, không gọi mạng)."""

from __future__ import annotations

import httpx
import pytest
import yaml

from core import config
from features.agent import desktop_release, desktop_update

REPO = "PeaGy/peto-harness"
SHA = "A" * 86 + "=="
SIZE = 215_000_000


def setup_name(version: str) -> str:
    return f"Peto-Agent-Setup-{version}-x64.exe"


def metadata(version: str, *, name: str | None = None, size: int = SIZE, sha: str = SHA) -> bytes:
    name = name or setup_name(version)
    return (f"version: {version}\nfiles:\n  - url: {name}\n    sha512: {sha}\n    size: {size}\npath: {name}\n"
            f"sha512: {sha}\nreleaseDate: '2026-11-07T01:00:00.000Z'\n").encode()


def release(version: str, *, yml: bool = True, size: int = SIZE, **extra) -> dict:
    base = f"https://github.com/{REPO}/releases/download/v{version}"
    assets = [{"name": setup_name(version), "browser_download_url": f"{base}/{setup_name(version)}", "size": size,
               "state": "uploaded"},
              {"name": f"{setup_name(version)}.blockmap", "browser_download_url": f"{base}/{setup_name(version)}.blockmap",
               "size": 200_000, "state": "uploaded"}]
    if yml:
        assets.append({"name": "stable.yml", "browser_download_url": f"{base}/stable.yml", "size": 400,
                       "state": "uploaded"})
    return {"tag_name": f"v{version}", "draft": False, "prerelease": True, "published_at": "2026-11-07T02:00:00Z",
            "html_url": f"https://github.com/{REPO}/releases/tag/v{version}", "assets": assets, **extra}


@pytest.fixture
def github(monkeypatch):
    """GitHub giả: API danh sách phát hành, link tải chuyển hướng sang máy tải như thật."""
    state: dict = {"calls": [], "releases": [release("0.2.2-rc.1.20261107.1")], "files": {}, "redirect": None}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"].append(request)
        url = request.url
        if url.host == "api.github.com":
            return httpx.Response(200, json=state["releases"])
        if url.host == "github.com" and url.path.endswith("/stable.yml"):
            tag = url.path.split("/")[-2]
            target = state["redirect"] or f"https://release-assets.githubusercontent.com/{tag}/stable.yml?sig=x"
            return httpx.Response(302, headers={"Location": target})
        if url.host == "release-assets.githubusercontent.com":
            tag = url.path.split("/")[1]
            body = state["files"].get(tag, metadata(tag[1:]))
            return httpx.Response(200, content=body)
        return httpx.Response(404)

    monkeypatch.setattr(config, "DESKTOP_RELEASES_REPO", REPO)
    monkeypatch.setattr(config, "DESKTOP_UPDATES", True)
    monkeypatch.setattr(desktop_release, "_TRANSPORT", httpx.MockTransport(handler))
    desktop_update._cache.clear()
    yield state
    desktop_update._cache.clear()


@pytest.mark.parametrize("channel", ["stable", "nightly"])
async def test_feed_points_at_the_github_installer(anon_client, github, channel):
    response = await anon_client.get(f"/api/agent/desktop/update/win-x64/{channel}.yml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/yaml")
    assert response.headers["cache-control"] == "public, max-age=60"
    feed = yaml.safe_load(response.text)
    url = f"https://github.com/{REPO}/releases/download/v0.2.2-rc.1.20261107.1/{setup_name('0.2.2-rc.1.20261107.1')}"
    assert feed == {"version": "0.2.2-rc.1.20261107.1", "files": [{"url": url, "sha512": SHA, "size": SIZE}],
                    "path": url, "sha512": SHA, "releaseDate": "2026-11-07T02:00:00Z"}
    hosts = [call.url.host for call in github["calls"]]
    assert hosts == ["api.github.com", "github.com", "release-assets.githubusercontent.com"]
    assert all("authorization" not in call.headers for call in github["calls"])


async def test_result_is_cached(anon_client, github):
    await anon_client.get("/api/agent/desktop/update/win-x64/stable.yml")
    await anon_client.get("/api/agent/desktop/update/win-x64/nightly.yml")
    assert len(github["calls"]) == 3


async def test_switch_off_unknown_targets_and_no_repo_give_404_without_calling_github(anon_client, github, monkeypatch):
    for path in ["mac-arm64/stable-mac.yml", "win-x64/latest.yml", "win-x64/stable.json"]:
        assert (await anon_client.get(f"/api/agent/desktop/update/{path}")).status_code == 404
    monkeypatch.setattr(config, "DESKTOP_UPDATES", False)
    response = await anon_client.get("/api/agent/desktop/update/win-x64/stable.yml")
    assert response.status_code == 404
    assert response.json()["detail"] == "Chưa có bản cập nhật Peto Agent nào."
    monkeypatch.setattr(config, "DESKTOP_UPDATES", True)
    monkeypatch.setattr(config, "DESKTOP_RELEASES_REPO", "")
    assert (await anon_client.get("/api/agent/desktop/update/win-x64/stable.yml")).status_code == 404
    assert github["calls"] == []


async def test_skips_drafts_and_releases_without_metadata(github):
    github["releases"] = [release("0.2.3", draft=True), release("0.2.2-rc.1.20261107.2", yml=False),
                          release("0.2.2-rc.1.20261107.1")]
    feed = yaml.safe_load(await desktop_update.current_feed())
    assert feed["version"] == "0.2.2-rc.1.20261107.1"


@pytest.mark.parametrize("broken", [
    metadata("0.2.2-rc.1.20261106.9"),                       # phiên bản khác thẻ
    metadata("0.2.2-rc.1.20261107.2", size=SIZE + 1),        # kích thước khác bộ cài thật
    metadata("0.2.2-rc.1.20261107.2", name="other.exe"),     # bộ cài không có trong bản phát hành
    metadata("0.2.2-rc.1.20261107.2", sha="not-a-hash"),
    b"version: [\n",                                          # YAML hỏng
    b"x" * (desktop_update.MAX_METADATA_BYTES + 1),
], ids=["version", "size", "name", "sha512", "yaml", "oversized"])
async def test_a_bad_newest_metadata_falls_back_to_the_previous_release(github, broken):
    github["releases"] = [release("0.2.2-rc.1.20261107.2"), release("0.2.2-rc.1.20261107.1")]
    github["files"]["v0.2.2-rc.1.20261107.2"] = broken
    feed = yaml.safe_load(await desktop_update.current_feed())
    assert feed["version"] == "0.2.2-rc.1.20261107.1"


async def test_redirect_outside_github_is_refused(github):
    github["redirect"] = "https://evil.example.com/stable.yml"
    assert await desktop_update.current_feed() is None
    assert all(call.url.host != "evil.example.com" for call in github["calls"])


async def test_github_failure_gives_no_feed(anon_client, github):
    github["releases"] = {"message": "rate limited"}
    assert (await anon_client.get("/api/agent/desktop/update/win-x64/stable.yml")).status_code == 404

"""Trang tải Peto Agent: đọc bản phát hành mới nhất từ GitHub Releases (giả bằng httpx.MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from core import config
from features.agent import desktop_release

REPO = "PeaGy/peto-harness"
BASE = f"https://github.com/{REPO}/releases/download"
DIGEST = "a" * 64


def asset(name: str, size: int = 312_000_000, **extra) -> dict:
    return {"name": name, "browser_download_url": f"{BASE}/v0.2.2-peto.1/{name}", "size": size, "state": "uploaded",
            "digest": f"sha256:{DIGEST}", **extra}


def release(tag: str = "v0.2.2-peto.1", assets: list | None = None, **extra) -> dict:
    return {"tag_name": tag, "draft": False, "prerelease": False, "published_at": "2026-11-05T09:30:00Z",
            "html_url": f"https://github.com/{REPO}/releases/tag/{tag}",
            "assets": assets if assets is not None else [asset("deepseek-harness-0.2.2-win-x64.exe"),
                                                         asset("deepseek-harness-0.2.2-win-x64.exe.blockmap"),
                                                         asset("latest.yml", 400)],
            **extra}


@pytest.fixture
def github(monkeypatch):
    """Thay GitHub bằng một hàm trả phản hồi; ghi lại các yêu cầu đã gửi."""
    state: dict = {"calls": [], "status": 200, "body": [release()]}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"].append(request)
        if isinstance(state["body"], Exception):
            raise state["body"]
        return httpx.Response(state["status"], json=state["body"])

    monkeypatch.setattr(config, "DESKTOP_RELEASES_REPO", REPO)
    monkeypatch.setattr(desktop_release, "_TRANSPORT", httpx.MockTransport(handler))
    desktop_release._cache.clear()
    yield state
    desktop_release._cache.clear()


async def test_latest_release_is_public_and_lists_installers(anon_client, github):
    response = await anon_client.get("/api/agent/desktop/release")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["version"] == "0.2.2-peto.1"
    assert data["published_at"] == "2026-11-05T09:30:00Z"
    assert data["notes_url"] == f"https://github.com/{REPO}/releases/tag/v0.2.2-peto.1"
    assert data["installers"] == [{"os": "windows", "arch": "x64", "name": "deepseek-harness-0.2.2-win-x64.exe",
                                   "url": f"{BASE}/v0.2.2-peto.1/deepseek-harness-0.2.2-win-x64.exe",
                                   "size": 312_000_000, "sha256": DIGEST}]
    request = github["calls"][0]
    assert request.url.host == "api.github.com"
    assert request.url.path == f"/repos/{REPO}/releases"
    assert "authorization" not in request.headers


async def test_result_is_cached(anon_client, github):
    await anon_client.get("/api/agent/desktop/release")
    await anon_client.get("/api/agent/desktop/release")
    assert len(github["calls"]) == 1


async def test_skips_drafts_and_releases_without_installers(github):
    github["body"] = [release("v0.3.0", draft=True), release("v0.2.3", assets=[asset("notes.zip")]),
                      release("v0.2.2-peto.1", prerelease=True,
                              assets=[asset("Peto-Agent-0.2.2-arm64.dmg"), asset("Peto Agent Setup 0.2.2.exe")])]
    data = await desktop_release.latest()
    assert data["version"] == "0.2.2-peto.1"
    assert data["prerelease"] is True
    assert [(item["os"], item["arch"]) for item in data["installers"]] == [("macos", "arm64"), ("windows", "")]


async def test_refuses_download_links_outside_the_repo(github):
    bad = asset("evil-x64.exe")
    bad["browser_download_url"] = "https://example.com/evil-x64.exe"
    other = asset("other-x64.exe")
    other["browser_download_url"] = "https://github.com/someone/else/releases/download/v1/other-x64.exe"
    github["body"] = [release(assets=[bad, other])]
    data = await desktop_release.latest()
    assert data == {"available": False, "releases_url": f"https://github.com/{REPO}/releases"}


async def test_odd_fields_are_dropped_not_trusted(github):
    weird = asset("peto-x64.exe", digest="md5:abc")
    github["body"] = [release(tag="nightly", assets=[weird]), release(assets=[asset("peto-x64.exe", size=True)]),
                      release(published_at="hôm qua", html_url="https://example.com/notes", assets=[weird])]
    data = await desktop_release.latest()
    assert data["version"] == "0.2.2-peto.1"
    assert data["published_at"] is None
    assert data["notes_url"] == f"https://github.com/{REPO}/releases"
    assert data["installers"][0]["sha256"] is None


@pytest.mark.parametrize("failure", ["status", "network", "json"])
async def test_github_failures_report_no_release(github, failure):
    if failure == "status":
        github["status"] = 404
    elif failure == "network":
        github["body"] = httpx.ConnectError("không kết nối được")
    else:
        github["body"] = {"message": "Not Found"}
    data = await desktop_release.latest()
    assert data == {"available": False, "releases_url": f"https://github.com/{REPO}/releases"}


async def test_oversized_response_is_refused(github, monkeypatch):
    monkeypatch.setattr(desktop_release, "MAX_RESPONSE_BYTES", 100)
    assert (await desktop_release.latest())["available"] is False


async def test_no_repo_configured_never_calls_github(github, monkeypatch):
    monkeypatch.setattr(config, "DESKTOP_RELEASES_REPO", "")
    assert await desktop_release.latest() == {"available": False, "releases_url": None}
    assert github["calls"] == []


async def test_desktop_app_update_check_says_no_forced_update(anon_client):
    """Ứng dụng chỉ coi là "không bắt buộc" khi code 0, biz_code 0 và biz_data null (mandatory-update-policy.ts)."""
    response = await anon_client.get("/api/v0/check_client_update", params={"scenario": "startup"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["code"] == 0 and body["data"]["biz_code"] == 0 and body["data"]["biz_data"] is None

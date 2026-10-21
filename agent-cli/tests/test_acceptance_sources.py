"""Bài nghiệm thu xuyên suốt của lộ trình nhiều nguồn (mục 7, mốc M6), bản tất định: máy chủ Peto và OpenAI giả trên
127.0.0.1, project tạm có lỗi xác định được và bài kiểm tra độc lập.

1. Nguồn Peto đọc và sửa một phần (hàm add), lưu kết quả công cụ.
2. Máy chủ Peto báo hết bước; hội thoại giữ nguyên.
3. Người dùng chọn model của nguồn trực tiếp (khóa API riêng, hay gói ChatGPT) bằng /model; giao diện nói đúng nguồn.
4. Nguồn mới làm nốt (hàm mul) dựa trên kết quả đã có và chạy bài kiểm tra độc lập.
5. /compact bằng nguồn mới; đóng peto, mở lại, /resume rồi kiểm tra lại.
6. Không mất yêu cầu, không chạy lại lệnh, không gọi /step của Peto sau khi đổi, khóa không lọt ra đĩa.
"""

from __future__ import annotations

import json
import sys
import time

import pytest
from conftest import FakeUI, handoff
from test_direct_source import KEY, OpenAIHandler, answer, call, leaked, purpose_of, serve
from test_loop_client import Handler as PetoHandler, message

from peto_agent import __main__ as cli
from peto_agent import config, connections, credentials, history

pytestmark = pytest.mark.skipif(not credentials.available(), reason="Kho khóa DPAPI chỉ có trên Windows.")

CALC = "def add(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a + b\n"
CHECK = ("import calc\n\nwith open('runs.log', 'a', encoding='utf-8') as log:\n    log.write('run\\n')\n"
         "assert calc.add(2, 3) == 5, 'add sai'\nassert calc.mul(2, 3) == 6, 'mul sai'\nprint('ALL OK')\n")
CHECK_COMMAND = f'"{sys.executable}" check_calc.py'
FIXED = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
PATCH_MUL = ("*** Begin Patch\n*** Update File: calc.py\n@@\n def mul(a, b):\n-    return a + b\n+    return a * b\n"
             "*** End Patch")
TASKS = ("Sửa hàm add", "Sửa nốt mul", "Làm tiếp", "Kiểm tra lần cuối")
PLAN_TOKEN = "at-plan-" + "Zr4" * 20


def stage(body: dict) -> tuple[str, int, list]:
    """(việc đang làm, số kết quả công cụ từ lúc giao việc đó, các kết quả). Lời nhắc của CLI không phải việc mới."""
    task, outputs = "", []
    for item in body.get("input") or []:
        if item.get("type") == "message" and item.get("role") == "user":
            content = item.get("content")
            text = content if isinstance(content, str) else " ".join(
                part.get("text", "") for part in content or [] if isinstance(part, dict))
            found = next((name for name in TASKS if name in text), None)
            if found:
                task, outputs = found, []
        elif item.get("type") == "function_call_output":
            outputs.append(json.loads(item["output"]))
    return task, len(outputs), outputs


def peto_reply(path: str, body: dict):
    if path == "/api/agent/me":
        return 200, {"account": "Bình", "device_name": "MAY-THU", "steps_used": 196, "steps_limit": 200,
                     "agent_features": [], "models": [{"key": "peto", "label": "Peto", "step_cost": 1}]}
    if path != "/api/agent/step":
        return 404, "Không có"
    task, done, _ = stage(body)
    if task != "Sửa hàm add":
        return 429, "Hôm nay đã dùng hết bước của Peto Agent."
    if done == 0:
        text, calls = "", [call(0, "read_file", path="calc.py", start_line=None, end_line=None)]
    elif done == 1:
        text, calls = "", [call(1, "edit_file", path="calc.py", old_text="    return a - b", new_text="    return a + b")]
    else:
        text, calls = "Đã sửa add; mul còn sai.", []
    return 200, [{"type": "meta", "steps_used": 197 + done, "steps_limit": 200}, {"type": "delta", "text": text},
                 {"type": "done", "output": [message(text), *calls], "usage": {"input_tokens": 9000, "output_tokens": 90}}]


def direct_reply(body: dict):
    purpose = purpose_of(body)
    if purpose == "title":
        return answer("Sửa calc")
    if purpose == "compact":
        return answer(handoff("Đã sửa add (Peto) và mul (nguồn trực tiếp); kiểm tra ALL OK."))
    task, done, outputs = stage(body)
    if task in {"Sửa nốt mul", "Làm tiếp"}:
        steps = [call(2, "read_file", path="calc.py", start_line=None, end_line=None),
                 call(3, "apply_patch", patch_text=PATCH_MUL),
                 call(4, "run_command", command=CHECK_COMMAND, timeout_seconds=None, cwd=None, shell=None)]
        if done < len(steps):
            return answer("", steps[done])
        return answer("Đã sửa mul; bài kiểm tra in ALL OK.")
    if task == "Kiểm tra lần cuối":
        if done == 0:
            return answer("", call(5, "run_command", command=CHECK_COMMAND, timeout_seconds=None, cwd=None, shell=None))
        return answer("Kiểm tra lại vẫn ALL OK.")
    return answer("Chưa rõ việc.")


def connect(source: str, server) -> tuple[connections.Connection, str]:
    endpoint = f"{server.url}/v1"
    if source == "openai-key":
        return connections.add("openai", KEY, endpoint=endpoint, models=("gpt-6-luna",)), KEY
    record = {"issuer": "https://auth.openai.com", "subject": "user-1", "email": "ban@example.com",
              "client_id": "app_test", "access_token": PLAN_TOKEN, "refresh_token": "rt-plan-" + "Qq9" * 20,
              "id_token": "", "token_type": "Bearer", "expires_in": 3600, "expires_at": time.time() + 3600,
              "scopes": "chatgpt.tokens.use.direct openid", "saved_at": time.time()}
    item = connections.add("chatgpt", record, label="ban@example.com", endpoint=endpoint, models=("gpt-6-luna",),
                           extra={"client_id": "app_test", "sub": "user-1", "email": "ban@example.com", "plan": True,
                                  "status": "", "model_names": {"gpt-6-luna": "GPT-6 Luna"}})
    return item, PLAN_TOKEN


@pytest.mark.parametrize("source", ["openai-key", "chatgpt-plan"])
def test_switch_source_mid_task_compact_reopen_and_verify(source, project, agent_home, monkeypatch):
    (project / "calc.py").write_text(CALC, encoding="utf-8", newline="\n")
    (project / "check_calc.py").write_text(CHECK, encoding="utf-8", newline="\n")
    peto = serve(PetoHandler, reply=peto_reply)
    direct = serve(OpenAIHandler, reply=direct_reply, models=(200, {"data": [{"id": "gpt-6-luna"}]}))
    try:
        config.save({"server": peto.url, "token": "peto_token_thu"})
        item, secret = connect(source, direct)
        monkeypatch.chdir(project)

        first = FakeUI(answers=["Sửa hàm add", "Sửa nốt mul rồi chạy kiểm tra", "/model gpt-6-luna", "/usage",
                                "Làm tiếp", "/compact", "/exit"])
        assert cli.session(first) == 0
        steps = [request for request in peto.requests if request["path"] == "/api/agent/step"]
        assert "hết bước" in first.text
        assert "Sửa nốt mul" in json.dumps(steps[-1]["body"]["input"], ensure_ascii=False), \
            "sau lần bị từ chối vì hết bước, không có /step nào nữa"
        assert "Hội thoại này giờ dùng GPT-6 Luna" in first.text
        assert ("Using ChatGPT plan" if source == "chatgpt-plan" else "khóa riêng nên không tính bước Peto") in first.text
        assert (project / "calc.py").read_text(encoding="utf-8") == FIXED, "add do Peto sửa, mul do nguồn mới sửa"
        assert (project / "runs.log").read_text(encoding="utf-8") == "run\n"
        compacts = [request for request in direct.requests if request["path"] == "/v1/responses"
                    and purpose_of(request["body"]) == "compact"]
        assert len(compacts) == 1, "/compact chạy bằng nguồn mới"

        again = FakeUI(answers=["/resume", "Kiểm tra lần cuối", "/exit"])
        assert cli.session(again) == 0
        assert "Kiểm tra lại vẫn ALL OK." in again.text
        assert (project / "runs.log").read_text(encoding="utf-8") == "run\nrun\n", "mở lại không chạy lại lệnh cũ"
        steps_after = [request for request in peto.requests if request["path"] == "/api/agent/step"]
        assert len(steps_after) == len(steps), "mở lại vẫn dùng nguồn của hội thoại, không gọi /step của Peto"

        saved = history.load(project, peto.url)
        assert saved.source == source and saved.model == "gpt-6-luna" and saved.connection == item.id
        text = json.dumps(saved.items, ensure_ascii=False)
        assert "Sửa hàm add" in text or "Sửa nốt mul" in text, "yêu cầu của người dùng còn sau tóm tắt"
        assert text.count("ALL OK") >= 1
        for request in direct.requests:
            if request["path"] != "/v1/responses":
                continue
            body = request["body"]
            assert request["auth"] == f"Bearer {secret}" and secret not in json.dumps(body)
            if source == "chatgpt-plan":
                assert "max_output_tokens" not in body and body["store"] is False
                assert all(tool["type"] == "namespace" for tool in body.get("tools") or [])
        on_disk = [path for path in leaked(agent_home) if "credentials" not in str(path)] if source == "openai-key" \
            else [str(path) for path in agent_home.rglob("*") if path.is_file() and "credentials" not in str(path)
                  and not path.name.endswith("-shm") and secret.encode() in path.read_bytes()]
        assert on_disk == [], "khóa hay token chỉ nằm trong kho DPAPI"
    finally:
        for server in (peto, direct):
            server.shutdown()
            server.server_close()

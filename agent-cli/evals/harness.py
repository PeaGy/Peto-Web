"""Chạy một bài thi: chép dự án mẫu ra thư mục tạm, để Peto làm như khi người dùng gõ yêu cầu, rồi chấm.

Peto chạy bằng đúng mã của agent-cli (Session, Tools) và máy chủ thật; chỉ phần trả lời câu hỏi quyền là PolicyUI thay
người dùng. Mọi thứ Peto lưu (nhật ký, hồ sơ trình duyệt, quyền, ảnh chụp) nằm trong PETO_AGENT_HOME của bài thi, không
đụng tới peto người dùng đang dùng hằng ngày.
"""

from __future__ import annotations

import _thread
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType

from peto_agent import browser, config, loop
from peto_agent.client import ApiError, Client
from peto_agent.context import text_of
from peto_agent.loop import Session, TaskLog
from peto_agent.workspace import Workspace

from checks import Check, Context
from policy import Policy, PolicyUI

TASKS_DIR = Path(__file__).with_name("tasks")
REPO = Path(__file__).resolve().parents[2]
FILE_TOOLS = {"edit_file", "write_file", "delete_file", "move_file"}
LOOK_TOOLS = {"list_files", "read_file", "search_files", "browser_read"}
MAX_PATCH_CHARS = 300_000
MAX_RESULT_PREVIEW = 1500
GENERATED = ("__pycache__/", "*.pyc", ".pytest_cache/", "bin/", "obj/", "node_modules/", "*.egg-info/")
GIT_IDENTITY = ["-c", "user.name=Peto Eval", "-c", "user.email=eval@peto.invalid", "-c", "commit.gpgsign=false",
                "-c", "core.autocrlf=false", "-c", "core.hooksPath=.git/hooks", "-c", "init.defaultBranch=main"]


@dataclass
class Task:
    id: str
    dir: Path
    module: ModuleType
    title: str
    kind: str
    project: str
    prompt: str
    max_steps: int
    sites: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    solution_reply: str = ""
    needs: tuple[str, ...] = ()


def load_tasks(ids: list[str] | None = None) -> list[Task]:
    tasks = []
    for folder in sorted(path for path in TASKS_DIR.iterdir() if (path / "task.py").is_file()):
        spec = importlib.util.spec_from_file_location(f"eval_task_{folder.name.replace('-', '_')}", folder / "task.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tasks.append(Task(folder.name, folder, module, module.TITLE, module.KIND, module.PROJECT, module.PROMPT.strip(),
                          module.MAX_STEPS, tuple(getattr(module, "SITES", ())), tuple(getattr(module, "ALLOW", ())),
                          tuple(getattr(module, "DENY", ())), getattr(module, "SOLUTION_REPLY", "").strip(),
                          tuple(getattr(module, "NEEDS", ()))))
    if ids:
        known = {task.id: task for task in tasks}
        missing = [name for name in ids if name not in known]
        if missing:
            raise SystemExit(f"Không có bài: {', '.join(missing)}. Xem danh sách bằng: run.py list")
        return [known[name] for name in ids]
    return tasks


def remove_tree(path: Path, *, quiet: bool = False) -> None:
    """Xóa cả thư mục, kể cả tệp chỉ đọc: object của git trên Windows là chỉ đọc, rmtree thường bị từ chối."""
    def writable(function, target, _error):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    if not path.exists():
        return
    try:
        shutil.rmtree(path, onexc=writable)
    except OSError as err:
        if not quiet:
            raise
        print(f"   (không xóa hết được {path}: {err.strerror or err})")


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *GIT_IDENTITY, "-C", str(root), *args], capture_output=True, check=check,
                          timeout=120)


def prepare(task: Task, parent: Path) -> Path:
    """Dựng bản sao của dự án bài thi thành một kho git riêng, commit sẵn, để biết chính xác Peto đã đổi gì."""
    root = parent / task.project
    remove_tree(root)
    source = task.dir / "project"
    if source.is_dir():
        shutil.copytree(source, root, ignore=shutil.ignore_patterns("__pycache__", "bin", "obj"))
    else:
        root.mkdir(parents=True)
    if hasattr(task.module, "prepare"):
        task.module.prepare(root)
    subprocess.run(["git", *GIT_IDENTITY, "init", "-q", str(root)], capture_output=True, check=True, timeout=60)
    # Tệp sinh ra khi build hay chạy test không phải thay đổi của Peto. Ghi ở .git/info/exclude chứ không thêm
    # .gitignore, để dự án Peto thấy vẫn đúng như bản gốc.
    info = root / ".git" / "info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "exclude").write_text("\n".join(GENERATED) + "\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "Bản gốc của bài thi")
    # Đường dẫn thật, giống Workspace của Peto: hồ sơ trình duyệt của dự án đặt tên theo mã băm của nó, và đường dẫn chưa
    # resolve có thể khác (thư mục bị Windows chuyển chỗ), làm forget_project xóa nhầm hồ sơ không có.
    return root.resolve()


def apply_solution(task: Task, root: Path) -> None:
    """Chép lời giải mẫu đè lên dự án (dùng cho selftest)."""
    solution = task.dir / "solution"
    if solution.is_dir():
        shutil.copytree(solution, root, dirs_exist_ok=True)


def export_repo(root: Path) -> None:
    """Chép mã đã commit của Peto-Web (git archive HEAD): không có .env, dữ liệu hay phần chưa commit.

    Bỏ chính thư mục bài thi: trong đó có lời giải mẫu của mọi bài, kể cả câu trả lời của bài hỏi về Peto-Web, và Peto
    tìm thấy đáp án trong đề thì bài không còn đo được việc dò code.
    """
    import io
    import tarfile
    archive = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", "HEAD", "--", ".",
                              ":(exclude)agent-cli/evals"], capture_output=True, check=True, timeout=120).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(root, filter="data")


class Recorder:
    """Ghi lại từng bước model và từng lần gọi công cụ bằng cách bọc các hàm của Session."""

    def __init__(self, session: Session):
        self.session = session
        self.steps: list[dict] = []
        self.calls: list[dict] = []
        self.outcome: str | None = None
        self.seconds = 0.0
        original_step, original_call, original_summary = session._step, session.tools.call, session._summary

        def step():
            started = time.monotonic()
            before = dict(session.metrics.usage["model"])
            output = original_step()
            after = session.metrics.usage["model"]
            messages = [text_of(item) for item in output or []
                        if item.get("type") == "message" and item.get("role") == "assistant"]
            self.steps.append({
                "index": len(self.steps) + 1, "seconds": round(time.monotonic() - started, 1),
                "ok": output is not None, "text": "\n".join(text for text in messages if text).strip(),
                "calls": [item.get("name") for item in output or [] if item.get("type") == "function_call"],
                "input_tokens": after["input_tokens"] - before["input_tokens"],
                "output_tokens": after["output_tokens"] - before["output_tokens"],
                "server_steps_used": session.steps_used})
            return output

        def call(name: str, arguments: str) -> dict:
            started = time.monotonic()
            result = original_call(name, arguments)
            try:
                parsed = json.loads(arguments or "{}")
            except (TypeError, ValueError):
                parsed = arguments
            preview = json.dumps(result, ensure_ascii=False)
            self.calls.append({"step": len(self.steps), "name": name, "arguments": parsed,
                               "ok": not (isinstance(result, dict) and result.get("error")),
                               "error": result.get("error") if isinstance(result, dict) else None,
                               "classification": result.get("classification") if isinstance(result, dict) else None,
                               "seconds": round(time.monotonic() - started, 2),
                               "result": preview[:MAX_RESULT_PREVIEW] + ("…" if len(preview) > MAX_RESULT_PREVIEW else "")})
            return result

        def summary(elapsed: float, outcome: str) -> None:
            self.outcome, self.seconds = outcome, elapsed
            original_summary(elapsed, outcome)

        session._step, session.tools.call, session._summary = step, call, summary

    @property
    def reply(self) -> str:
        """Lời của bước cuối, là câu trả lời người dùng đọc khi Peto xong."""
        for step in reversed(self.steps):
            if step["ok"]:
                return step["text"]
        return ""

    @property
    def text(self) -> str:
        return "\n\n".join(step["text"] for step in self.steps if step["text"])


def behavior(calls: list[dict], requests: list[dict]) -> dict:
    """Thói quen làm việc, đo cho mọi bài: lặp y hệt, tự kiểm tra sau khi sửa, lệnh bị từ chối, danh sách việc."""
    # Gọi lại y hệt sau khi đã sửa tệp (chạy lại test, đọc lại tệp vừa sửa) là việc nên làm, không phải lặp: chỉ tính
    # những lần gọi y hệt mà giữa chúng không có tệp nào đổi.
    seen: set[tuple[str, str, int]] = set()
    repeated = []
    revision = 0
    for call in calls:
        key = (call["name"], json.dumps(call["arguments"], ensure_ascii=False, sort_keys=True), revision)
        if key in seen:
            repeated.append(call["name"])
        seen.add(key)
        if call["name"] in FILE_TOOLS and call["ok"]:
            revision += 1
    edits = [index for index, call in enumerate(calls) if call["name"] in FILE_TOOLS and call["ok"]]
    verified = None
    if edits:
        after = calls[edits[-1] + 1:]
        verified = any(call["ok"] and (call["name"] in {"run_command", "browser_open", "browser_screenshot",
                                                        "read_command_output", "start_command"})
                       for call in after)
    refused = [request for request in requests if request.get("answer") == "n"]
    refused_commands = [request.get("command") for request in refused if request.get("command")]
    plans = [call for call in calls if call["name"] == "update_plan" and call["ok"]]
    left = None
    if plans:
        with_left = json.loads(plans[-1]["result"]) if plans[-1]["result"].endswith("}") else {}
        left = with_left.get("left")
    return {"repeated": repeated, "repeated_looks": sum(1 for name in repeated if name in LOOK_TOOLS),
            "edits": len(edits), "verified_after_edit": verified, "refused": len(refused),
            "refused_repeated": len(refused_commands) - len(set(refused_commands)),
            "commands": sum(1 for call in calls if call["name"] in {"run_command", "start_command"}),
            "plan_used": bool(plans), "plan_left": left}


def score(task: Task, ctx: Context) -> list[Check]:
    try:
        task.module.check(ctx)
    except Exception:  # noqa: BLE001 - bộ chấm hỏng thì bài trượt với lý do rõ, không làm dừng cả lượt thi
        ctx.checks.append(Check("bộ chấm chạy được", False, True, traceback.format_exc(limit=3)[-500:]))
    if not any(check.required for check in ctx.checks):
        ctx.checks.append(Check("bài có phép chấm bắt buộc", False, True, "check() không ghi phép bắt buộc nào"))
    return ctx.checks


def run_task(task: Task, client: Client, *, work: Path, out: Path, model: str, effort: str, step_cost: int,
             timeout: int, keep: bool = False, name: str | None = None) -> dict:
    """Cho Peto làm một bài; trả bản ghi kết quả (cũng lưu vào ``out``/<name>/, name mặc định là mã bài; chạy một bài
    nhiều lần trong một lượt thì mỗi lần một name)."""
    name = name or task.id
    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    root = prepare(task, work / name)
    ui = PolicyUI(Policy(root, sites=task.sites, allow=task.allow, deny=task.deny))
    log = TaskLog(task.project)
    session = Session(client, Workspace(root), ui, log=log, effort=effort, model=model, model_step_cost=step_cost)
    recorder = Recorder(session)
    before = _steps_used(client)
    shots_before = set(config.screenshots_dir().glob("*")) if config.screenshots_dir().is_dir() else set()
    saved_limit = loop.MAX_STEPS_PER_TASK
    loop.MAX_STEPS_PER_TASK = task.max_steps
    timed_out = threading.Event()

    def stop() -> None:
        timed_out.set()
        _thread.interrupt_main()

    watchdog = threading.Timer(timeout, stop)
    started = time.monotonic()
    crashed = ""
    try:
        watchdog.start()
        session.run_task(task.prompt)
    except KeyboardInterrupt:
        pass  # hết giờ ngoài vòng làm việc (lúc lưu hay tóm tắt): phần đã ghi vẫn được chấm
    except Exception:  # noqa: BLE001 - lỗi của CLI cũng là kết quả cần ghi
        crashed = traceback.format_exc(limit=4)[-1500:]
    finally:
        watchdog.cancel()
        loop.MAX_STEPS_PER_TASK = saved_limit
        wall = time.monotonic() - started
        try:
            session.tools.jobs.stop_all()
            session.tools.close_browser()
        except KeyboardInterrupt:
            pass
        browser.forget_project(root)
    after = _steps_used(client)
    ctx = Context(root, task.dir, reply=recorder.reply, text=recorder.text, calls=recorder.calls,
                  requests=ui.requests)
    patch = _patch(root)
    checks = score(task, ctx)
    outcome = "timeout" if timed_out.is_set() else ("crash" if crashed else (recorder.outcome or "unknown"))
    usage = session.metrics.usage["model"]
    record = {
        "task": task.id, "name": name, "title": task.title, "kind": task.kind, "project": task.project,
        "prompt": task.prompt,
        "max_steps": task.max_steps, "outcome": outcome, "crash": crashed, "seconds": round(wall, 1),
        "steps": len(recorder.steps),
        "server_steps": (after - before) if before is not None and after is not None else None,
        "tokens": {"input": usage["input_tokens"], "output": usage["output_tokens"], "reported": usage["reported"]},
        "reply": recorder.reply, "text": recorder.text[:20000], "changed": ctx.changed,
        "checks": [asdict(check) for check in checks],
        "passed": all(check.ok for check in checks if check.required),
        "behavior": behavior(recorder.calls, ui.requests), "calls": recorder.calls, "requests": ui.requests,
        "steps_detail": recorder.steps,
    }
    (folder / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "transcript.txt").write_text(ui.transcript, encoding="utf-8")
    (folder / "diff.patch").write_text(patch, encoding="utf-8")
    if log.path and log.path.exists():
        shutil.copyfile(log.path, folder / "log.jsonl")
    shots = sorted(set(config.screenshots_dir().glob("*")) - shots_before) if config.screenshots_dir().is_dir() else []
    if shots:
        (folder / "screenshots").mkdir(exist_ok=True)
        for shot in shots:
            shutil.copyfile(shot, folder / "screenshots" / shot.name)
    if not keep:
        remove_tree(work / name, quiet=True)
    return record


def selftest(task: Task, work: Path) -> tuple[bool, str]:
    """Bài chưa làm phải trượt ít nhất một phép bắt buộc; lời giải mẫu phải qua hết. Không gọi model nào."""
    root = prepare(task, work / f"{task.id}-goc")
    untouched = score(task, Context(root, task.dir))
    failing = [check.name for check in untouched if check.required and not check.ok]
    root = prepare(task, work / f"{task.id}-giai")
    apply_solution(task, root)
    solved = score(task, Context(root, task.dir, reply=task.solution_reply, text=task.solution_reply))
    broken = [f"{check.name} ({check.detail})" for check in solved if check.required and not check.ok]
    remove_tree(work / f"{task.id}-goc", quiet=True)
    remove_tree(work / f"{task.id}-giai", quiet=True)
    if not failing:
        return False, "bản chưa làm vẫn qua hết phép bắt buộc: phép chấm không phân biệt được"
    if broken:
        return False, "lời giải mẫu trượt: " + "; ".join(broken)
    bonus = [check.name for check in solved if not check.required and not check.ok]
    return True, f"bản gốc trượt {len(failing)} phép, lời giải qua hết" + (
        f" (phụ chưa qua: {', '.join(bonus)})" if bonus else "")


def _steps_used(client: Client) -> int | None:
    try:
        return int(client.json("GET", "/api/agent/me").get("steps_used") or 0)
    except (ApiError, ValueError, TypeError):
        return None


def _patch(root: Path) -> str:
    """Toàn bộ thay đổi của Peto so với bản gốc, kể cả tệp mới và tệp đã xóa."""
    try:
        git(root, "add", "-A")
        text = git(root, "diff", "--cached", "--stat", "--patch", check=False).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return ""
    if len(text) > MAX_PATCH_CHARS:
        text = text[:MAX_PATCH_CHARS] + f"\n… (bỏ {len(text) - MAX_PATCH_CHARS} ký tự)\n"
    return text


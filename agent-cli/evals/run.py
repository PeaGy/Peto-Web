"""Bài thi Peto: cho Peto Agent làm các bài mẫu trên máy này rồi chấm tự động.

    python agent-cli/evals/run.py login              kết nối "máy bài thi" với tài khoản Peto (duyệt trên web)
    python agent-cli/evals/run.py status             tài khoản và số bước còn lại hôm nay
    python agent-cli/evals/run.py list               danh sách bài
    python agent-cli/evals/run.py selftest [bài …]   kiểm bộ chấm, không gọi model: bài gốc trượt, lời giải mẫu qua
    python agent-cli/evals/run.py run [bài …]        cho Peto làm bài: tốn bước thật trong hạn mức ngày
    python agent-cli/evals/run.py report <thư mục>   viết lại report.md của một lượt thi

Mọi thứ của bài thi nằm trong %USERPROFILE%\\.peto-eval (đổi bằng --home): đăng nhập riêng, nhật ký, hồ sơ trình
duyệt, bản sao dự án (xóa sau khi chấm) và kết quả. peto người dùng dùng hằng ngày không bị đụng tới.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

# Biến môi trường mang khóa, token, mật khẩu bị bỏ trước khi làm gì khác: lệnh Peto chạy thừa hưởng môi trường của bộ
# chạy, và không bài nào cần chúng. PETO_AGENT_HOME đặt lại ngay sau đó.
SECRET_ENV = re.compile(r"(?i)(KEY|TOKEN|SECRET|PASSW|CREDENTIAL|AUTH|COOKIE|SESSION)"
                        r"|^(PETO_|OPENAI|XAI_|ANTHROPIC|AWS_|AZURE_|GITHUB_|GH_|GITLAB_|NPM_|PYPI_|DISCORD|GOOGLE_)")
REAL_CONFIG = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "PetoAgent" / "config.json"


def scrub_environment() -> list[str]:
    removed = [name for name in list(os.environ) if SECRET_ENV.search(name)]
    for name in removed:
        os.environ.pop(name, None)
    return removed


REMOVED_ENV = scrub_environment()

from peto_agent import __main__ as cli  # noqa: E402
from peto_agent import __version__, browser, config  # noqa: E402
from peto_agent.client import ApiError, Client  # noqa: E402
from peto_agent.ui import UI  # noqa: E402

import harness  # noqa: E402
import report  # noqa: E402

EFFORT_LABELS = {"low": "thấp", "medium": "vừa", "high": "cao"}
EFFORT_COST = {"low": 1, "medium": 1, "high": 2}


def use_home(home: Path) -> None:
    os.environ["PETO_AGENT_HOME"] = str(home / "peto")
    os.environ["PETO_AGENT_NO_BELL"] = "1"


def real_server() -> str:
    """Địa chỉ máy chủ peto hằng ngày đang dùng; chỉ đọc khóa server, không đọc token."""
    try:
        return str(json.loads(REAL_CONFIG.read_text(encoding="utf-8")).get("server") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def saved_client() -> Client:
    settings = config.load()
    if not settings.get("server") or not settings.get("token"):
        raise SystemExit("Máy bài thi chưa đăng nhập. Chạy: python agent-cli/evals/run.py login")
    return Client(settings["server"], settings["token"], timeout=60)


def cmd_login(args) -> int:
    server = args.server or real_server()
    if not server:
        raise SystemExit("Không biết địa chỉ Peto. Chạy lại với --server https://…")
    host = socket.gethostname()
    config.device_name = lambda: f"Bài thi Peto · {host}"
    print("Đăng nhập riêng cho bài thi: trên web sẽ hiện thêm một máy tên \"Bài thi Peto\", thu hồi được trong "
          "Cài đặt → Peto Agent. Bước bài thi dùng vẫn tính vào hạn mức ngày của tài khoản.")
    return cli.login(UI(), server)


def cmd_status(args) -> int:
    client = saved_client()
    me = client.json("GET", "/api/agent/me")
    left = int(me.get("steps_limit") or 0) - int(me.get("steps_used") or 0)
    models = ", ".join(f"{m.get('label')} ({m.get('key')}, {m.get('step_cost', 1)} bước/lượt)"
                       for m in me.get("models") or [])
    print(f"{client.server} · tài khoản {me.get('account')} · còn {left}/{me.get('steps_limit')} bước hôm nay")
    print(f"Model: {models or 'Peto'} · mức mặc định {me.get('default_effort')} · CLI trên máy chủ "
          f"{me.get('cli_version')} · bộ thi dùng peto {__version__}")
    return 0


def cmd_list(args) -> int:
    tasks = harness.load_tasks()
    total = sum(task.max_steps for task in tasks)
    for task in tasks:
        needs = f" · cần {', '.join(task.needs)}" if task.needs else ""
        print(f"{task.id:<28} {task.kind:<10} tối đa {task.max_steps:>2} lượt · {task.title}{needs}")
    print(f"{len(tasks)} bài · tối đa {total} lượt gọi model nếu bài nào cũng dùng hết.")
    return 0


def missing_needs(task) -> list[str]:
    missing = []
    if "dotnet" in task.needs and not shutil.which("dotnet"):
        missing.append("dotnet")
    if "edge" in task.needs and not browser.find_browser():
        missing.append("Edge hoặc Chrome")
    if "git" in task.needs and not shutil.which("git"):
        missing.append("git")
    return missing


def cmd_selftest(args) -> int:
    home = Path(args.home)
    work = home / "work" / "selftest"
    work.mkdir(parents=True, exist_ok=True)
    failures = 0
    for task in harness.load_tasks(args.tasks or None):
        if missing := missing_needs(task):
            print(f"–  {task.id}: bỏ qua, máy thiếu {', '.join(missing)}")
            continue
        ok, detail = harness.selftest(task, work)
        failures += not ok
        print(f"{'✓' if ok else '✗'}  {task.id}: {detail}")
    harness.remove_tree(work, quiet=True)
    return 1 if failures else 0


def cmd_run(args) -> int:
    tasks = [task for task in harness.load_tasks(args.tasks or None) for _ in range(args.repeat)]
    for task in tasks:
        if missing := missing_needs(task):
            raise SystemExit(f"Bài {task.id} cần {', '.join(missing)} mà máy này chưa có.")
    client = saved_client()
    me = client.json("GET", "/api/agent/me")
    models = me.get("models") or [{"key": "peto", "label": "Peto", "step_cost": 1}]
    model = next((item for item in models if item.get("key") == args.model), None)
    if model is None:
        raise SystemExit(f"Tài khoản không dùng được model {args.model}. Có: {', '.join(m['key'] for m in models)}")
    effort = args.effort
    cost = EFFORT_COST[effort] * int(model.get("step_cost") or 1)
    budget = sum(task.max_steps for task in tasks) * cost
    left = int(me.get("steps_limit") or 0) - int(me.get("steps_used") or 0)
    print(f"{len(tasks)} bài · {model.get('label')} · mức {EFFORT_LABELS[effort]} · mỗi lượt tính {cost} bước · "
          f"tối đa {budget} bước (thường ít hơn nhiều) · hôm nay còn {left} bước.")
    if budget > left:
        print("Cảnh báo: có thể hết bước giữa chừng; bài nào không đủ bước sẽ bị bỏ.")
    if not args.yes:
        try:
            if input("Chạy? [y/N] ").strip().lower() != "y":
                return 1
        except EOFError:
            return 1
    home = Path(args.home)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = home / "results" / f"{stamp}-{model['key']}-{effort}"
    out.mkdir(parents=True)
    work = home / "work" / stamp
    run = {"started": datetime.now().strftime("%d/%m/%Y %H:%M"), "server": client.server, "model": model["key"],
           "model_label": model.get("label") or model["key"], "effort": effort, "effort_label": EFFORT_LABELS[effort],
           "cli_version": __version__, "tasks": [], "skipped": []}
    seen: dict[str, int] = {}
    for task in tasks:
        seen[task.id] = seen.get(task.id, 0) + 1
        name = task.id if seen[task.id] == 1 else f"{task.id}~{seen[task.id]}"
        try:
            me = client.json("GET", "/api/agent/me")
            left = int(me.get("steps_limit") or 0) - int(me.get("steps_used") or 0)
        except ApiError:
            left = task.max_steps * cost
        if left < task.max_steps * cost:
            print(f"–  {name}: bỏ qua, hôm nay chỉ còn {left} bước")
            run["skipped"].append(name)
            continue
        print(f"▶  {name} · {task.title}", flush=True)
        record = harness.run_task(task, client, work=work, out=out, model=model["key"], effort=effort,
                                  step_cost=int(model.get("step_cost") or 1), timeout=args.timeout, keep=args.keep,
                                  name=name)
        run["tasks"].append(name)
        (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        failed = [check["name"] for check in record["checks"] if check["required"] and not check["ok"]]
        print(f"{'✓' if record['passed'] else '✗'}  {name} · {record['steps']} lượt · {record['seconds']:.0f} giây · "
              f"{report.OUTCOMES.get(record['outcome'], record['outcome'])}"
              + (f" · trượt: {'; '.join(failed)}" if failed else ""), flush=True)
        if record["outcome"] == "stopped":
            print("Đã dừng theo Ctrl+C; các bài sau không chạy.")
            break
    (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.keep:
        harness.remove_tree(work, quiet=True)
    path = report.write(out)
    print(f"Báo cáo: {path}")
    return 0


def cmd_report(args) -> int:
    """Viết lại report.md; thói quen được tính lại từ các lần gọi đã ghi, để cách đo mới áp cho cả lượt thi cũ."""
    folder = Path(args.folder)
    for path in folder.glob("*/result.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["behavior"] = harness.behavior(record["calls"], record["requests"])
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report.write(folder))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="run.py", description="Bài thi Peto Agent.")
    # Thư mục người dùng chứ không phải %LOCALAPPDATA%: ứng dụng Claude cài từ Microsoft Store (MSIX) chuyển thư mục mới
    # mà tiến trình con của nó tạo trong AppData sang ...\Packages\Claude_…\LocalCache, nên kết quả Claude chạy thì người
    # dùng không thấy ở %LOCALAPPDATA% (gặp ngày 24/09/2026). Thư mục người dùng thì ai chạy cũng là một chỗ.
    parser.add_argument("--home", default=str(Path.home() / ".peto-eval"),
                        help="thư mục của bài thi (đăng nhập, nhật ký, kết quả)")
    commands = parser.add_subparsers(dest="command", required=True)
    login = commands.add_parser("login", help="kết nối máy bài thi với tài khoản Peto")
    login.add_argument("--server", help="địa chỉ Peto; mặc định là máy chủ peto hằng ngày đang dùng")
    commands.add_parser("status", help="tài khoản, số bước còn lại")
    commands.add_parser("list", help="danh sách bài")
    selftest = commands.add_parser("selftest", help="kiểm bộ chấm, không gọi model")
    selftest.add_argument("tasks", nargs="*")
    run = commands.add_parser("run", help="cho Peto làm bài")
    run.add_argument("tasks", nargs="*")
    run.add_argument("--model", default="peto")
    run.add_argument("--effort", choices=sorted(EFFORT_LABELS), default="low")
    run.add_argument("--timeout", type=int, default=900, help="giây tối đa cho mỗi bài")
    run.add_argument("--repeat", type=int, default=1, choices=range(1, 6), metavar="N",
                     help="chạy mỗi bài N lần (1–5) để xem kết quả có ổn định không")
    run.add_argument("--keep", action="store_true", help="giữ bản sao dự án sau khi chấm")
    run.add_argument("--yes", action="store_true", help="không hỏi lại trước khi chạy")
    again = commands.add_parser("report", help="viết lại report.md")
    again.add_argument("folder")
    args = parser.parse_args(argv)
    use_home(Path(args.home))
    handler = {"login": cmd_login, "status": cmd_status, "list": cmd_list, "selftest": cmd_selftest,
               "run": cmd_run, "report": cmd_report}[args.command]
    try:
        return handler(args)
    except ApiError as err:
        print(err.message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Báo cáo một lượt thi: bảng tổng, thói quen chung, rồi từng bài với phép chấm, lệnh đã xin và lời Peto."""

from __future__ import annotations

import json
from pathlib import Path

from peto_agent.loop import format_duration, format_tokens

OUTCOMES = {"done": "xong", "limit": "chạm giới hạn lượt", "stopped": "bị dừng", "error": "lỗi máy chủ",
            "timeout": "hết giờ", "crash": "CLI lỗi", "unknown": "không rõ"}


def load(run_dir: Path) -> tuple[dict, list[dict]]:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    results = []
    for task in run.get("tasks", []):
        path = run_dir / task / "result.json"
        if path.is_file():
            results.append(json.loads(path.read_text(encoding="utf-8")))
    return run, results


def _notes(result: dict) -> str:
    habits = result["behavior"]
    notes = []
    if result["outcome"] != "done":
        notes.append(OUTCOMES.get(result["outcome"], result["outcome"]))
    if habits["repeated"]:
        notes.append(f"gọi lặp {len(habits['repeated'])}")
    if habits["refused"]:
        notes.append(f"bị từ chối {habits['refused']}" + (f" (xin lại {habits['refused_repeated']})"
                                                          if habits["refused_repeated"] else ""))
    if habits["plan_left"]:
        notes.append(f"kế hoạch còn {habits['plan_left']} việc")
    failed = [check["name"] for check in result["checks"] if check["required"] and not check["ok"]]
    if failed:
        notes.append("trượt: " + "; ".join(failed[:2]) + (f" (+{len(failed) - 2})" if len(failed) > 2 else ""))
    return " · ".join(notes)


def _verified(result: dict) -> str:
    value = result["behavior"]["verified_after_edit"]
    return "—" if value is None else ("có" if value else "không")


def render(run: dict, results: list[dict]) -> str:
    passed = sum(1 for result in results if result["passed"])
    steps = sum(result["steps"] for result in results)
    server = [result["server_steps"] for result in results if result["server_steps"] is not None]
    tokens_in = sum(result["tokens"]["input"] for result in results)
    tokens_out = sum(result["tokens"]["output"] for result in results)
    seconds = sum(result["seconds"] for result in results)
    lines = [
        f"# Bài thi Peto · {run['started']} · {run['model_label']} · mức {run['effort_label']}", "",
        f"Máy chủ {run['server']} · peto {run['cli_version']} · {len(results)} lần làm bài. Model trả lời mỗi lần một "
        "khác, nên một lần trượt đơn lẻ chưa nói lên nhiều; so nhiều lần chạy.", "",
        f"**Đạt {passed}/{len(results)}** · {steps} lượt gọi model"
        + (f" ({sum(server)} bước tính trên máy chủ)" if server else "")
        + f" · {format_tokens(tokens_in)} token vào / {format_tokens(tokens_out)} ra · {format_duration(seconds)}", "",
        "| Bài | Loại | Kết quả | Lượt | Thời gian | Token vào | Tự kiểm tra sau sửa | Ghi chú |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        mark = "✓ đạt" if result["passed"] else "✗ trượt"
        lines.append(f"| {result.get('name') or result['task']} | {result['kind']} | {mark} | "
                     f"{result['steps']}/{result['max_steps']} | {format_duration(result['seconds'])} | "
                     f"{format_tokens(result['tokens']['input'])} | {_verified(result)} | {_notes(result)} |")
    edited = [result for result in results if result["behavior"]["verified_after_edit"] is not None]
    repeated = sum(len(result["behavior"]["repeated"]) for result in results)
    looks = sum(result["behavior"]["repeated_looks"] for result in results)
    refused = sum(result["behavior"]["refused"] for result in results)
    again = sum(result["behavior"]["refused_repeated"] for result in results)
    counts: dict[str, list[bool]] = {}
    for result in results:
        counts.setdefault(result["task"], []).append(result["passed"])
    reruns = {task: passes for task, passes in counts.items() if len(passes) > 1}
    if reruns:
        lines += ["", "## Bài chạy nhiều lần", ""]
        for task, passes in reruns.items():
            steps = [result["steps"] for result in results if result["task"] == task]
            lines.append(f"- {task}: đạt {sum(passes)}/{len(passes)} · lượt {', '.join(map(str, steps))}")
    lines += [
        "", "## Thói quen chung", "",
        f"- Tự kiểm tra sau lần sửa cuối: {sum(1 for r in edited if r['behavior']['verified_after_edit'])}/"
        f"{len(edited)} bài có sửa tệp.",
        f"- Gọi công cụ lặp y hệt: {repeated} lần, trong đó {looks} lần chỉ để xem lại (đọc, tìm, liệt kê).",
        f"- Lệnh hay trang bị bài thi từ chối: {refused}; xin lại đúng lệnh đã bị từ chối: {again}.",
        f"- Chạm giới hạn lượt: {sum(1 for r in results if r['outcome'] == 'limit')} bài; hết giờ: "
        f"{sum(1 for r in results if r['outcome'] == 'timeout')} bài; dùng danh sách việc: "
        f"{sum(1 for r in results if r['behavior']['plan_used'])} bài.",
        "", "## Từng bài", "",
    ]
    for result in results:
        mark = "✓" if result["passed"] else "✗"
        lines += [f"### {mark} {result.get('name') or result['task']} · {result['title']}", "",
                  "> " + result["prompt"].replace("\n", "\n> "), ""]
        for check in result["checks"]:
            mark = "✓" if check["ok"] else "✗"
            label = check["name"] if check["required"] else f"(phụ) {check['name']}"
            lines.append(f"- {mark} {label}" + (f" · {check['detail']}" if check["detail"] else ""))
        requests = [request for request in result["requests"] if request.get("kind") in {"command", "background",
                                                                                          "site", "login"}]
        if requests:
            lines += ["", "Xin quyền:"]
            for request in requests:
                what = request.get("command") or request.get("url") or request.get("detail") or ""
                answer = "đồng ý" if request.get("answer") == "y" else f"từ chối ({request.get('reason')})"
                kind = {"background": "lệnh nền", "site": "trang ngoài", "login": "đăng nhập"}.get(request["kind"], "lệnh")
                lines.append(f"- {kind} `{what[:160]}` → {answer}")
        habits = result["behavior"]
        lines += ["", f"Kết thúc: {OUTCOMES.get(result['outcome'], result['outcome'])} · {result['steps']} lượt · "
                      f"{len(result['calls'])} lần gọi công cụ · sửa {habits['edits']} lần · "
                      f"{format_tokens(result['tokens']['input'])} token vào"
                      + (f" · gọi lặp: {', '.join(habits['repeated'])}" if habits["repeated"] else "")]
        if result.get("crash"):
            lines += ["", "```", result["crash"].strip(), "```"]
        reply = result["reply"].strip()
        if reply:
            clipped = reply if len(reply) <= 1200 else reply[:1200] + " …"
            lines += ["", "Peto trả lời:", "", "> " + clipped.replace("\n", "\n> ")]
        lines.append("")
    return "\n".join(lines)


def write(run_dir: Path) -> Path:
    run, results = load(run_dir)
    path = run_dir / "report.md"
    path.write_text(render(run, results), encoding="utf-8")
    return path

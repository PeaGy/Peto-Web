"""Agent con chỉ đọc (CLI 0.27.0, theo tool/plugin/subagent.ts và agent "explore" của opencode).

Peto gọi explore(task, depth) để giao một việc dò mã: CLI chạy một vòng con với hội thoại riêng (chỉ có task), một
Workspace riêng (agent con đọc không tính là Peto đã đọc, nên muốn sửa tệp Peto vẫn phải tự đọc) và bốn công cụ đọc.
Chỉ kết luận của nó quay về hội thoại chính, nên hội thoại đó gọn hơn. Mỗi bước con là một bước thường: cùng model của
phiên, mức suy nghĩ thấp (chủ web chọn ngày 2026-10-15). Hết bước thì lượt cuối không công cụ ("final") để luôn có câu
trả lời. Ctrl+C dừng cả con lẫn yêu cầu.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable

from .client import ApiError
from .context import efficient_input, text_of
from .workspace import Workspace

# Như máy chủ (features/agent/tools.EXPLORE_DEPTHS).
STEPS = {"quick": 4, "medium": 8, "thorough": 15}
ALLOWED = ("list_files", "find_files", "search_files", "read_file")
KEPT_TYPES = {"message", "function_call", "reasoning", "web_search_call"}
MAX_SUMMARY_CHARS = 8000
NOT_ALLOWED = "Agent con chỉ được tìm và đọc (list_files, find_files, search_files, read_file)."


class SubagentError(Exception):
    pass


def label(name: str, args: dict) -> str:
    """Một dòng ngắn cho việc agent con đang làm, hiện ở dòng trạng thái và trong khối Khám phá."""
    if name == "read_file":
        return f"Đọc {args.get('path', '')}"
    if name == "list_files":
        return f"Xem thư mục {args.get('path') or '.'}"
    if name == "find_files":
        return f'Tìm tệp "{args.get("pattern", "")}"'
    if name == "search_files":
        return f'Tìm "{args.get("pattern", "")}"'
    return name


class _ChildUI:
    """Giao diện của Tools con: không vẽ gì; mỗi công cụ thành một dòng tiến độ cho Peto chính."""

    def __init__(self, progress: Callable[[str], None]):
        self.progress = progress
        self.actions: list[str] = []
        self.read: list[str] = []
        self.mode = "build"

    def tool_started(self, call) -> None:
        self.progress(label(call.name, call.args))

    def tool_finished(self, done) -> None:
        if done.meta.get("stopped"):
            return
        failed = bool(done.meta.get("raised") or done.result.get("error"))
        self.actions.append(label(done.name, done.args) + (" (lỗi)" if failed else ""))
        if done.name == "read_file" and not failed and done.result.get("path"):
            self.read.append(done.result["path"])

    def __getattr__(self, name):
        # Mọi sự kiện khác (preview, notice, status…) bỏ qua: agent con không sửa gì, không hỏi gì.
        return lambda *args, **kwargs: None


def run(session, task: str, depth: str, progress: Callable[[str], None]) -> dict:
    """Chạy agent con tới khi nó trả lời hay hết bước; trả kết quả gửi lại cho Peto (kèm ``_actions`` cho giao diện)."""
    from .loop import BOUNDED_KEYS, READ_BOUNDED_KEYS, cap_result, user_message
    from .tools import Tools

    cap = STEPS.get(depth, STEPS["medium"])
    ui = _ChildUI(progress)
    tools = Tools(Workspace(session.ws.root), ui)
    tools.features = list(session.tools.features)
    tools._handlers = {name: handler for name, handler in tools._handlers.items() if name in ALLOWED}
    efforts = getattr(session, "supported_efforts", None)
    effort = "low" if not efforts or "low" in efforts else efforts[0]
    items: list[dict] = [user_message(task)]
    steps, summary, problem = 0, "", None
    try:
        for step in range(cap):
            final = step == cap - 1
            # Dòng trạng thái lúc chờ model: bước mấy, và việc vừa làm (đọc, tìm xong ngay nên khó kịp thấy).
            progress(f"bước {step + 1}/{cap}" + (f" · vừa {ui.actions[-1][:1].lower() + ui.actions[-1][1:]}"
                                                 if ui.actions else ""))
            output = _step(session, items, effort, final)
            steps += 1
            items.extend(output)
            calls = [item for item in output if item.get("type") == "function_call"]
            text = "\n".join(text_of(item) for item in output
                             if item.get("type") == "message" and item.get("role") == "assistant").strip()
            if text:
                summary = text
            if not calls:
                break
            tools.start_step()
            for call in calls:
                name = str(call.get("name", ""))
                if final or name not in ALLOWED:
                    result = {"error": NOT_ALLOWED if name not in ALLOWED else "Đã hết bước, không chạy nữa."}
                else:
                    result = cap_result(tools.call(name, str(call.get("arguments", ""))),
                                        READ_BOUNDED_KEYS if name == "read_file" else BOUNDED_KEYS)
                items.append({"type": "function_call_output", "call_id": call.get("call_id", ""),
                              "output": json.dumps(result, ensure_ascii=False)})
    except SubagentError as err:
        problem = str(err)
    finally:
        with contextlib.suppress(Exception):
            tools.mcp.close()
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[:MAX_SUMMARY_CHARS] + "\n… (kết luận dài, đã cắt)"
    result = {"summary": summary or "(Agent con không trả lời được.)", "steps": steps,
              "files_read": sorted(set(ui.read))[:50], "_actions": ui.actions}
    if problem:
        result["error"] = f"Agent con dừng giữa chừng: {problem}"
    return result


def _step(session, items: list[dict], effort: str, final: bool) -> list[dict]:
    context = session._step_context()
    context.update(purpose="explore", **({"final": True} if final else {}))
    body = {"input": efficient_input(items), "effort": effort, "model": session.model, "context": context}
    try:
        with contextlib.closing(session.client.stream("/api/agent/step", body)) as events:
            for event in events:
                kind = event.get("type")
                if kind == "meta":
                    session.steps_used, session.steps_limit = event.get("steps_used"), event.get("steps_limit")
                elif kind == "error":
                    raise SubagentError(str(event.get("message") or "Máy chủ báo lỗi."))
                elif kind == "done":
                    usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
                    session.metrics.record_usage("model", usage)
                    session.metrics.calls["model"] += 1
                    output = event.get("output")
                    if not isinstance(output, list):
                        raise SubagentError("Máy chủ trả kết quả bước không đúng định dạng.")
                    return [item for item in output if isinstance(item, dict) and item.get("type") in KEPT_TYPES]
    except ApiError as err:
        raise SubagentError(err.message) from err
    raise SubagentError("Kết nối bị ngắt trước khi agent con làm xong bước này.")

"""Công cụ của Peto Agent.

Máy chủ định nghĩa schema để CLI không tự khai thêm công cụ; chương trình trên máy người dùng mới là nơi chạy công
cụ, kiểm đường dẫn và hỏi người dùng trước khi sửa tệp hay chạy lệnh.

Schema strict bắt model gửi đủ mọi tham số, kể cả tham số tùy chọn (null). CLI cũ nhận tham số lạ thì báo sai tham số,
nên tham số và công cụ mới chỉ có trong schema khi CLI khai báo hiểu nó trong ``context.features`` (xem
``tool_schemas``).
"""

from __future__ import annotations

# Khả năng CLI có thể khai báo. "cwd": run_command và start_command nhận thư mục con để chạy lệnh (CLI 0.9.8).
# "browser": ba công cụ xem trang chạy trên máy bằng trình duyệt ẩn (CLI 0.10.0). "browser_act": bấm, gõ, nhấn phím và
# nhờ người dùng đăng nhập trên trang đang xem (CLI 0.11.0); "browser_outside": browser_open nhận cả trang ngoài máy,
# chỉ xem (CLI 0.12.0). Hai khả năng sau chỉ có tác dụng cùng "browser".
# "explore_v2" (CLI 0.18.0, theo OpenCode): read_file đánh số dòng, search_files gộp theo tệp, thêm find_files.
# "edit_v2" (CLI 0.18.0, chủ web duyệt ngày 2026-10-12): edit_file khớp gần đúng có kiểm soát và replace_all.
# CLI 0.21.0 (theo opencode, chủ web chọn ngày 2026-10-12): "question" thêm ask_user; "patch" thay edit_file và
# write_file bằng apply_patch khi model là GPT (Luna, Terra, Sol), như opencode; "title" là lượt đặt tên hội thoại
# (purpose "title"); "steer", "jobs_notify", "plan_mode" chỉ thêm lời nhắc giải thích tin CLI 0.20 chèn vào hội thoại.
# CLI 0.25.0 (theo lõi opencode, chủ web chọn ngày 2026-10-15): "read_more" đọc tới 1000 dòng mỗi lần; "output_files"
# lưu đủ output lệnh dài và thêm read_output; "wrapup" là lượt tóm tắt không công cụ khi hết bước của một yêu cầu;
# "user_guide" gửi kèm AGENTS.md chung của người dùng. CLI 0.27.0: "subagent" thêm explore, giao việc dò mã cho một
# agent con chỉ đọc (purpose "explore").
FEATURES = frozenset({"cwd", "browser", "browser_act", "browser_outside", "skills", "mcp", "explore_v2", "edit_v2",
                      "question", "patch", "title", "steer", "jobs_notify", "plan_mode", "btw", "read_more", "task_state",
                      "output_files", "wrapup", "user_guide", "subagent", "recall", "python_exec"})
# Công cụ của agent con explore: chỉ tìm và đọc trong dự án (theo agent "explore" của opencode).
EXPLORE_TOOLS = ("list_files", "find_files", "search_files", "read_file")
# Số bước tối đa của agent con theo độ kỹ: nhanh, vừa, kỹ.
EXPLORE_DEPTHS = {"quick": 4, "medium": 8, "thorough": 15}

_PATH = {"type": "string", "description": "Đường dẫn tương đối tính từ gốc dự án, ví dụ src/app.py; '.' là gốc."}
_SHELL = {
    "type": ["string", "null"],
    "description": "Trên Windows: 'cmd' hay 'powershell'; null là cmd. Chọn powershell khi lệnh cần cmdlet "
                   "(Get-ChildItem…), biến $env: hay cú pháp PowerShell; hệ khác thì bỏ qua và dùng shell mặc định.",
}
_CWD = {
    "type": ["string", "null"],
    "description": "Thư mục chạy lệnh, tương đối tính từ gốc dự án, ví dụ frontend; null là gốc dự án. Mỗi lệnh mở "
                   "một shell mới nên cd ở lệnh trước không giữ sang lệnh sau: dùng tham số này thay cho cd.",
}


def _tool(name: str, description: str, properties: dict) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
        "strict": True,
    }


_FILE_TOOLS = [
    _tool(
        "list_files",
        "Liệt kê tệp và thư mục trong dự án, bỏ qua node_modules, .venv, .git, dist, build và những gì .gitignore ở "
        "gốc dự án bỏ qua (biết đường dẫn thì vẫn đọc được bằng read_file). Dùng để nắm cấu trúc trước khi đọc.",
        {
            "path": _PATH,
            "depth": {"type": ["integer", "null"], "description": "Số tầng thư mục, 1 đến 4. null là 2."},
        },
    ),
    _tool(
        "read_file",
        "Đọc một tệp chữ trong dự án, có thể theo khoảng dòng. Kết quả là nội dung nguyên văn, không kèm số dòng, "
        "cùng tổng số dòng của tệp.",
        {
            "path": _PATH,
            "start_line": {"type": ["integer", "null"], "description": "Dòng bắt đầu, tính từ 1. null là từ đầu tệp."},
            "end_line": {
                "type": ["integer", "null"],
                "description": "Dòng kết thúc, tính cả dòng này. null đọc tối đa 160 dòng; khoảng chỉ định tối đa 400 dòng. "
                               "Dùng next_start_line trong kết quả để đọc tiếp khi cần.",
            },
        },
    ),
    _tool(
        "search_files",
        "Tìm biểu thức chính quy (cú pháp Python re) trong các tệp chữ của dự án, bỏ qua thư mục nặng và những gì "
        ".gitignore bỏ qua. Trả về tối đa 100 dòng khớp kèm tên tệp và số dòng.",
        {
            "pattern": {"type": "string", "description": "Biểu thức chính quy cần tìm."},
            "path": {"type": ["string", "null"], "description": "Thư mục hoặc tệp để tìm. null là cả dự án."},
            "glob": {"type": ["string", "null"], "description": "Lọc tên tệp, ví dụ *.py. null là mọi tệp chữ."},
        },
    ),
    _tool(
        "edit_file",
        "Sửa một tệp bằng cách thay đúng một đoạn. Người dùng xem diff và phải đồng ý. old_text phải chép nguyên văn "
        "từ lần đọc gần nhất và chỉ xuất hiện một lần; tệp phải chưa bị đổi kể từ lần đọc đó.",
        {
            "path": _PATH,
            "old_text": {"type": "string", "description": "Đoạn cần thay, nguyên văn, đủ dài để chỉ khớp một chỗ."},
            "new_text": {"type": "string", "description": "Đoạn thay vào."},
        },
    ),
    _tool(
        "write_file",
        "Tạo tệp mới với toàn bộ nội dung, hoặc ghi đè cả tệp khi thật cần. Người dùng xem nội dung và phải đồng ý. "
        "Tệp đã có thì ưu tiên edit_file.",
        {
            "path": _PATH,
            "content": {"type": "string", "description": "Toàn bộ nội dung tệp."},
        },
    ),
    _tool(
        "update_plan",
        "Ghi danh sách việc của yêu cầu đang làm để người dùng thấy Peto định làm gì và đang tới đâu. Dùng khi yêu "
        "cầu có từ ba việc trở lên hoặc đụng nhiều tệp; gọi lại mỗi khi xong một việc. Không đụng gì trên máy nên "
        "không phải xin phép. Việc một bước thì đừng dùng.",
        {
            "steps": {
                "type": "array",
                "description": "Các việc theo thứ tự làm, tối đa 10 mục.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Một dòng ngắn nói việc cần làm."},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "running", "done"],
                            "description": "pending là chưa làm, running là đang làm, done là đã xong.",
                        },
                    },
                    "required": ["title", "status"],
                    "additionalProperties": False,
                },
            },
        },
    ),
    _tool(
        "delete_file",
        "Xóa một tệp chữ trong dự án. Người dùng xem nội dung sắp mất và phải đồng ý; sau đó họ hoàn tác được bằng "
        "/undo. Chỉ xóa khi yêu cầu cần tới. Đừng xóa bằng run_command: lệnh xóa của hệ điều hành không hoàn tác được.",
        {"path": _PATH},
    ),
    _tool(
        "move_file",
        "Đổi tên hoặc chuyển một tệp chữ sang chỗ khác trong dự án, nội dung giữ nguyên. Người dùng phải đồng ý; sau "
        "đó họ hoàn tác được bằng /undo. Đích phải chưa có tệp. Đừng đổi tên bằng run_command.",
        {
            "path": _PATH,
            "new_path": {"type": "string", "description": "Đường dẫn mới, tương đối tính từ gốc dự án."},
        },
    ),
]


# Bản mới của ba công cụ tệp (GĐ 4 theo OpenCode), thay đúng chỗ bản cũ trong danh sách khi CLI khai báo khả năng.
_READ_V2 = _tool(
    "read_file",
    "Đọc một tệp chữ trong dự án, có thể theo khoảng dòng. Mỗi dòng trong content bắt đầu bằng số dòng rồi một ký tự "
    "tab (như cat -n): số đó không thuộc tệp, đừng chép vào old_text. Kèm tổng số dòng của tệp.",
    _FILE_TOOLS[1]["parameters"]["properties"],
)
# "read_more" (CLI 0.25.0): nhật ký thật của chủ web có 88/269 lần đọc bị cắt ở 160 dòng, một nửa là tệp chừng 186
# dòng, và mỗi lần đọc thiếu tốn thêm một bước. Đọc tới 1000 dòng (khoảng 32.000 ký tự) như opencode khuyên đọc một
# lần cho đủ thay vì nhiều khúc nhỏ.
_READ_V3 = _tool(
    "read_file",
    "Đọc một tệp chữ trong dự án, cả tệp hoặc một khoảng dòng. Mỗi dòng trong content bắt đầu bằng số dòng rồi một ký "
    "tự tab (như cat -n): số đó không thuộc tệp, đừng chép vào old_text. Kèm tổng số dòng của tệp. Mỗi lần đọc tới "
    "1000 dòng hay khoảng 32.000 ký tự: tệp ngắn hơn thế thì đọc cả tệp một lần, đừng chia nhiều khúc nhỏ.",
    {
        "path": _PATH,
        "start_line": {"type": ["integer", "null"], "description": "Dòng bắt đầu, tính từ 1. null là từ đầu tệp."},
        "end_line": {
            "type": ["integer", "null"],
            "description": "Dòng kết thúc, tính cả dòng này. null là tới cuối tệp (tối đa 1000 dòng mỗi lần). Dùng "
                           "next_start_line trong kết quả để đọc tiếp khi cần.",
        },
    },
)
_SEARCH_V2 = _tool(
    "search_files",
    "Tìm biểu thức chính quy (cú pháp Python re) trong các tệp chữ của dự án, bỏ qua thư mục nặng và những gì "
    ".gitignore bỏ qua. Kết quả gộp theo tệp, tệp sửa gần nhất trước; mỗi chỗ khớp có số dòng và nội dung dòng. "
    "Tối đa 100 chỗ khớp. Tìm tệp theo tên thì dùng find_files.",
    _FILE_TOOLS[2]["parameters"]["properties"],
)
_EDIT_V2 = _tool(
    "edit_file",
    "Sửa một tệp bằng cách thay một đoạn. Người dùng xem diff và phải đồng ý; tệp phải chưa bị đổi kể từ lần đọc gần "
    "nhất. old_text chép từ lần đọc đó, không kèm số dòng. Khớp nguyên văn trước; không khớp thì CLI thử khớp gần "
    "đúng (bỏ qua khoảng trắng đầu và cuối dòng, thụt lề khác) và ghi rõ cho người dùng. Đoạn phải chỉ khớp một chỗ, "
    "trừ khi replace_all là true.",
    {
        **_FILE_TOOLS[3]["parameters"]["properties"],
        "replace_all": {"type": ["boolean", "null"],
                        "description": "true thay mọi chỗ khớp nguyên văn với old_text; null hoặc false chỉ một chỗ."},
    },
)
_FIND = _tool(
    "find_files",
    "Tìm tệp theo tên bằng mẫu glob, ví dụ **/*.py, src/**/test_*.ts hay *.json; bỏ qua thư mục nặng và những gì "
    ".gitignore bỏ qua. Trả tối đa 100 đường dẫn, tệp sửa gần nhất trước. Tìm theo nội dung thì dùng search_files.",
    {
        "pattern": {"type": "string", "description": "Mẫu glob: * khớp trong một tên, ** khớp qua nhiều thư mục, ? "
                                                     "một ký tự."},
        "path": {"type": ["string", "null"], "description": "Thư mục để tìm. null là cả dự án."},
    },
)


_ASK = _tool(
    "ask_user",
    "Hỏi người dùng giữa chừng bằng câu hỏi có lựa chọn, rồi làm tiếp với câu trả lời. Chỉ hỏi khi có quyết định thật "
    "sự của người dùng mà mã nguồn và mặc định hợp lý không trả lời được; không dùng để xin quyền sửa tệp hay chạy "
    "lệnh (CLI đã hỏi). Người dùng luôn có thêm ô tự trả lời, nên đừng thêm lựa chọn \"Khác\". Phương án nên chọn đặt "
    "đầu, nhãn kết thúc bằng \"(nên chọn)\".",
    {
        "questions": {
            "type": "array", "description": "Một tới ba câu hỏi.",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["question", "header", "options", "multiple"],
                "properties": {
                    "question": {"type": "string", "description": "Câu hỏi đầy đủ, kết thúc bằng dấu hỏi."},
                    "header": {"type": "string", "description": "Nhãn ngắn, tối đa 12 ký tự."},
                    "options": {
                        "type": "array", "description": "Hai tới bốn lựa chọn.",
                        "items": {"type": "object", "additionalProperties": False, "required": ["label", "description"],
                                  "properties": {"label": {"type": "string", "description": "1–5 chữ."},
                                                 "description": {"type": "string",
                                                                 "description": "Chọn cái này thì sao."}}},
                    },
                    "multiple": {"type": ["boolean", "null"], "description": "true cho chọn nhiều; null là chọn một."},
                },
            },
        },
    },
)
_PATCH = _tool(
    "apply_patch",
    "Sửa, tạo, xóa hay đổi tên tệp bằng một bản patch (có thể nhiều tệp một lần). Người dùng xem diff từng tệp và đồng "
    "ý một lần cho cả bản patch. Tệp sửa hay xóa phải đã đọc và chưa đổi kể từ lần đọc đó; một chỗ không khớp là không "
    "ghi tệp nào. Định dạng: *** Begin Patch, rồi từng mục *** Add File: đường/dẫn (mọi dòng bắt đầu bằng +), "
    "*** Delete File: đường/dẫn, *** Update File: đường/dẫn (có thể kèm *** Move to: đường/mới) với các đoạn @@ gồm "
    "dòng ' ' giữ nguyên, '-' bỏ, '+' thêm; cuối cùng *** End Patch.",
    {"patch_text": {"type": "string", "description": "Toàn bộ bản patch, từ *** Begin Patch tới *** End Patch."}},
)


# "output_files" (CLI 0.25.0): output vượt 20.000 ký tự được CLI lưu đủ vào tệp trên máy người dùng, kết quả lệnh chỉ
# giữ phần đầu và cuối kèm output_id.
_READ_OUTPUT = _tool(
    "read_output",
    "Đọc hoặc tìm trong output đầy đủ của một lệnh đã chạy, khi kết quả run_command hay read_command_output có "
    "output_id (output dài bị bỏ phần giữa). Chỉ đọc dữ liệu CLI đã lưu trên máy nên không cần xin phép. Có pattern "
    "thì trả tối đa 40 dòng khớp kèm số dòng; không có thì đọc theo khoảng dòng, tối đa 400 dòng.",
    {
        "output_id": {"type": "string", "description": "Mã output_id trong kết quả lệnh."},
        "pattern": {"type": ["string", "null"],
                    "description": "Biểu thức chính quy (cú pháp Python re) cần tìm, ví dụ error|failed. null là đọc "
                                   "theo khoảng dòng."},
        "start_line": {"type": ["integer", "null"], "description": "Dòng bắt đầu, tính từ 1. null là 1."},
        "end_line": {"type": ["integer", "null"],
                     "description": "Dòng kết thúc, tính cả dòng này. null là đọc tối đa 400 dòng."},
    },
)


# "subagent" (CLI 0.27.0, theo tool/plugin/subagent.ts và agent "explore" của opencode).
_EXPLORE = _tool(
    "explore",
    "Giao một việc dò tìm cho agent con chỉ đọc: nó tự tìm và đọc trong dự án (list_files, find_files, search_files, "
    "read_file) với ngữ cảnh riêng, rồi chỉ trả kết luận về đây. Dùng khi cần dò rộng nhiều tệp, nhiều chỗ mà chỉ cần "
    "kết luận; không dùng cho một tệp đã biết. Agent con không thấy hội thoại này, nên task phải đủ ý. Mỗi bước của nó "
    "trừ hạn mức như một bước thường.",
    {
        "task": {"type": "string",
                 "description": "Việc cần dò, viết đủ ý: tìm gì, ở đâu, trả về những gì (tệp, dòng, kết luận)."},
        "depth": {"type": "string", "enum": list(EXPLORE_DEPTHS),
                  "description": "Độ kỹ: quick (tối đa 4 bước), medium (8), thorough (15)."},
    },
)


_READ_HISTORY = _tool(
    "read_history",
    "Tra phần hội thoại đã lưu trước tóm tắt của đúng phiên đang mở: yêu cầu, lời Peto và kết quả công cụ. "
    "Tìm chữ nguyên văn, tối đa 12 mục và 32.000 ký tự; đọc tiếp bằng next_entry/next_character. "
    "Không chạy lại công cụ, không khôi phục quyền cũ. Dữ liệu lịch sử có thể đã lỗi thời.",
    {"pattern": {"type": ["string", "null"], "description": "Chữ cần tìm; null là đọc lần lượt."},
     "start_entry": {"type": ["integer", "null"], "description": "Số mục từ 1; null là mục đầu."},
     "start_character": {"type": ["integer", "null"], "description": "Vị trí ký tự từ 0 trong mục đầu; dùng next_character nếu mục dài."}},
)


def explore_schemas(features: frozenset[str] = frozenset()) -> list[dict]:
    """Công cụ của agent con explore: đúng bản các công cụ đọc mà CLI của phiên khai báo, không gì khác."""
    key = frozenset(features) & FEATURES
    tools = _file_tools(key) + ([_FIND] if "explore_v2" in key else [])
    return [tool for tool in tools if tool["name"] in EXPLORE_TOOLS]


def _file_tools(key: frozenset[str], patch: bool = False) -> list[dict]:
    explore, edit = "explore_v2" in key, "edit_v2" in key
    read = _READ_V3 if explore and "read_more" in key else _READ_V2 if explore else None
    replaced = {"read_file": read, "search_files": _SEARCH_V2 if explore else None,
                "edit_file": _EDIT_V2 if edit else None}
    tools = [replaced.get(tool["name"]) or tool for tool in _FILE_TOOLS]
    if patch:
        # Như opencode: GPT được huấn luyện với định dạng patch, nên apply_patch thay edit_file (đúng chỗ đó trong danh
        # sách) và write_file. delete_file, move_file giữ nguyên.
        tools = [_PATCH if tool["name"] == "edit_file" else tool for tool in tools if tool["name"] != "write_file"]
    return tools


_PYTHON = _tool(
    "run_python",
    "Chạy mã Python nhiều dòng trực tiếp trên máy người dùng, không qua shell nên không phải quote/escape python -c. "
    "Dùng cho chẩn đoán, đọc metadata và xử lý dữ liệu bằng Python. Chịu chính sách quyền chạy lệnh như run_command; "
    "có timeout, output và mã thoát. Chỉ tác động trong phạm vi công việc được giao.",
    {"code": {"type": "string", "description": "Mã Python nguyên văn, có thể nhiều dòng, tối đa 12.000 ký tự."},
     "python": {"type": ["string", "null"], "description": "Tên hoặc đường dẫn trình thông dịch, không kèm tham số; null dùng Python của Peto."},
     "timeout_seconds": {"type": ["integer", "null"], "description": "1 đến 600 giây, null là 120."},
     "cwd": _CWD},
)


def _command_tools(cwd: bool) -> list[dict]:
    where = {"cwd": _CWD} if cwd else {}
    place = "ở gốc dự án hoặc thư mục con cwd" if cwd else "trong thư mục gốc dự án"
    return [
        _tool(
            "start_command",
            "Chạy một lệnh nền trên máy người dùng rồi trả về ngay: dùng cho dev server, watch, tiến trình chạy lâu "
            "không tự kết thúc. Người dùng phải đồng ý trước. Lệnh vẫn chạy sau khi yêu cầu xong, tới khi gọi "
            "stop_command hoặc tới khi người dùng đóng peto. Lệnh có điểm dừng (test, build) thì dùng run_command.",
            {
                "command": {"type": "string", "description": "Lệnh cần chạy nền, ví dụ npm run dev."},
                "shell": _SHELL,
                **where,
            },
        ),
        _tool(
            "read_command_output",
            "Đọc phần output mới của một lệnh nền, kèm trạng thái và mã thoát nếu nó đã dừng. Mỗi lần đọc tốn một "
            "bước, nên đặt wait_seconds để chờ sẵn thay vì hỏi đi hỏi lại.",
            {
                "job_id": {"type": "string", "description": "Mã lệnh nền do start_command trả về."},
                "wait_seconds": {
                    "type": ["integer", "null"],
                    "description": "Chờ tối đa bao nhiêu giây để có output mới, 0 đến 30. null là 5.",
                },
            },
        ),
        _tool(
            "stop_command",
            "Dừng một lệnh nền, giết cả cây tiến trình. Không phải xin phép vì chỉ dừng tiến trình Peto đã tạo.",
            {"job_id": {"type": "string", "description": "Mã lệnh nền do start_command trả về."}},
        ),
        _tool(
            "run_command",
            f"Chạy một lệnh {place} trên máy người dùng. Người dùng phải đồng ý trước. Dùng cho test, build, lint. "
            "Trả về mã thoát và output đã cắt gọn.",
            {
                "command": {"type": "string", "description": "Lệnh cần chạy, ví dụ npm test hoặc python -m pytest."},
                "timeout_seconds": {"type": ["integer", "null"],
                                    "description": "Thời hạn tính bằng giây, 1 đến 600. null là 120."},
                "shell": _SHELL,
                **where,
            },
        ),
    ]


_VIEWPORT = {
    "type": ["string", "null"],
    "description": "'desktop' (máy tính 1280×800) hoặc 'mobile' (điện thoại 390×844, giả lập màn hình cảm ứng); null "
                   "là desktop khi mở trang, còn khi chụp là giữ khung đang dùng.",
}

_OPEN_DESCRIPTION = (
    "Mở hoặc tải lại một trang web chạy trên máy người dùng trong trình duyệt ẩn (hồ sơ riêng, không có tài khoản "
    "của họ). Chỉ nhận localhost, 127.0.0.1, ::1; trang ngoài bị từ chối. Trả về tiêu đề, mã HTTP, lỗi console, "
    "lỗi JavaScript và request hỏng, cùng các phần tử đang hiện (tiêu đề, nút, ô nhập, liên kết, ảnh thiếu alt). "
    "Không kèm ảnh: cần nhìn thì gọi browser_screenshot, cùng bước cũng được."
)
# Với CLI bấm, gõ được (đợt 2): phần tử thao tác được có số, và trang của dev server vừa bật được chờ.
_OPEN_DESCRIPTION_ACT = _OPEN_DESCRIPTION + (
    " Phần tử thao tác được có số trong ngoặc vuông, ví dụ [3], để dùng với browser_click và browser_type. Có lệnh "
    "nền đang chạy mà server chưa nghe cổng thì chờ tối đa 15 giây, nên gọi ngay sau start_command trong cùng bước "
    "được."
)


# Với CLI mở được trang ngoài (đợt 3, chủ web chọn ngày 2026-09-24): chỉ xem, trình duyệt riêng không cookie, hỏi mỗi
# tên miền. Thay câu "trang ngoài bị từ chối" của hai mô tả trên.
_OPEN_DESCRIPTION_OUTSIDE = (
    "Mở hoặc tải lại một trang web. Trang trên máy người dùng (localhost, 127.0.0.1, ::1) mở trong trình duyệt của dự "
    "án. Trang ngoài máy (http, https) mở trong một trình duyệt riêng không cookie, không đăng nhập, chỉ xem: lần đầu "
    "mỗi tên miền người dùng được hỏi, địa chỉ dài bất thường luôn hỏi lại, địa chỉ trong mạng nhà bị từ chối. Trả về "
    "tiêu đề, mã HTTP, lỗi console, lỗi JavaScript và request hỏng, cùng các phần tử đang hiện (tiêu đề, nút, ô nhập, "
    "liên kết, ảnh thiếu alt); trên trang ngoài, link ghi kèm địa chỉ sau dấu → để mở tiếp. Không kèm ảnh: cần nhìn "
    "thì gọi browser_screenshot, cùng bước cũng được."
)
_OPEN_ACT_NOTE = (
    " Trên trang trên máy, phần tử thao tác được có số trong ngoặc vuông, ví dụ [3], để dùng với browser_click và "
    "browser_type. Có lệnh nền đang chạy mà server chưa nghe cổng thì chờ tối đa 15 giây, nên gọi ngay sau "
    "start_command trong cùng bước được."
)


def _open_tool(act: bool, outside: bool = False) -> dict:
    if outside:
        description = _OPEN_DESCRIPTION_OUTSIDE + (_OPEN_ACT_NOTE if act else "")
        url = ("Địa chỉ trang: trang trên máy, ví dụ http://localhost:5173/ (lấy đúng địa chỉ dev server in ra), hoặc "
               "trang ngoài người dùng đưa, ví dụ https://docs.python.org/3/.")
    else:
        description = _OPEN_DESCRIPTION_ACT if act else _OPEN_DESCRIPTION
        url = "Địa chỉ trang, ví dụ http://localhost:5173/ (lấy đúng địa chỉ dev server in ra)."
    return _tool("browser_open", description, {"url": {"type": "string", "description": url}, "viewport": _VIEWPORT})


# Đợt 1 của trình duyệt (chủ web chọn ngày 2026-09-23): chỉ xem, không bấm hay gõ, và chỉ trang chạy trên máy.
_BROWSER_TOOLS = [
    _open_tool(act=False),
    _tool(
        "browser_screenshot",
        "Chụp trang đang mở. Ảnh tới ở tin kế tiếp, sau kết quả các công cụ của bước này, và tốn nhiều token hơn chữ: "
        "chỉ chụp khi cần nhìn bố cục, màu sắc hay chỗ bị tràn.",
        {
            "viewport": _VIEWPORT,
            "full_page": {"type": ["boolean", "null"],
                          "description": "true chụp cả trang dài (tối đa 4000px); null hoặc false chỉ phần đang hiện."},
        },
    ),
    _tool(
        "browser_read",
        "Đọc chữ đang hiện trên trang đang mở (tối đa 20.000 ký tự), kèm lỗi mới xuất hiện từ lần xem trước.",
        {"selector": {"type": ["string", "null"],
                      "description": "CSS selector của phần cần đọc, ví dụ main hoặc #loi; null là cả trang."}},
    ),
]

_TARGET = {
    "type": "string",
    "description": "Phần tử cần thao tác: số trong ngoặc vuông ở danh sách phần tử của kết quả gần nhất (ví dụ 3), "
                   "hoặc CSS selector chỉ khớp một phần tử đang hiện (ví dụ #gui).",
}
_ACCEPT_DIALOG = {
    "type": ["boolean", "null"],
    "description": "Nếu thao tác này làm trang hỏi confirm hay prompt: true chọn OK, null hoặc false chọn Hủy. "
                   "alert luôn được đóng.",
}
KEYS = ["Enter", "Escape", "Tab", "Shift+Tab", "Backspace", "Delete", "Space", "ArrowUp", "ArrowDown", "ArrowLeft",
        "ArrowRight", "Home", "End", "PageUp", "PageDown"]

# Đợt 2 (chủ web chọn ngày 2026-09-23): bấm, gõ trên trang đang xem, hỏi quyền một lần cho mỗi trang; người dùng tự
# đăng nhập trong cửa sổ, Peto không gõ mật khẩu.
_BROWSER_ACT_TOOLS = [
    _tool(
        "browser_click",
        "Bấm một phần tử trên trang đang mở bằng chuột thật, như người dùng (tự cuộn tới nó). Lần đầu thao tác trên mỗi "
        "trang, người dùng được hỏi. Trả về những gì đổi: trang mới hay địa chỉ mới, chữ mới hiện, phần tử mới hiện "
        "hoặc vừa đổi trạng thái (có số mới), lỗi, hộp thoại, việc bị chặn. Phần tử bị che hay bị tắt thì báo lỗi "
        "thay vì bấm. Hộp chọn (select) thì dùng browser_type.",
        {"target": _TARGET, "accept_dialog": _ACCEPT_DIALOG},
    ),
    _tool(
        "browser_type",
        "Gõ chữ vào ô nhập (thay chữ đang có; chữ rỗng là xóa), hoặc chọn một lựa chọn trong hộp chọn theo chữ hiện "
        "của nó. Trả về chữ ô đang có sau khi gõ và những gì đổi như browser_click. Không gõ được vào ô mật khẩu: "
        "cần đăng nhập thì dùng browser_login.",
        {
            "target": _TARGET,
            "text": {"type": "string", "description": "Chữ cần gõ, hoặc chữ của lựa chọn cần chọn."},
            "submit": {"type": ["boolean", "null"], "description": "true nhấn Enter sau khi gõ (thường là gửi form)."},
            "accept_dialog": _ACCEPT_DIALOG,
        },
    ),
    _tool(
        "browser_press",
        "Nhấn một phím trên phần tử đang được chọn (focus) của trang đang mở, ví dụ Escape để đóng hộp thoại, Tab để "
        "chuyển ô, PageDown để cuộn. Trả về những gì đổi và phần tử đang được chọn.",
        {"key": {"type": "string", "enum": KEYS, "description": "Phím cần nhấn."}, "accept_dialog": _ACCEPT_DIALOG},
    ),
    _tool(
        "browser_login",
        "Nhờ người dùng tự đăng nhập (hay làm bước chỉ họ làm được: mã 2FA, CAPTCHA) trong cửa sổ trình duyệt của Peto, "
        "ở trang đang mở, rồi chờ họ báo xong. Mật khẩu họ gõ không tới Peto; đăng nhập được nhớ cho dự án này. Trả về "
        "trang sau khi xong, hoặc lỗi nếu họ bỏ qua.",
        {"reason": {"type": "string", "description": "Một câu ngắn nói vì sao cần họ, ví dụ: trang /admin cần đăng "
                                                     "nhập."}},
    ),
]

# Schema cho CLI không khai báo khả năng nào (bản 0.9.7 trở về trước): giữ nguyên từng chữ.
TOOL_SCHEMAS = _FILE_TOOLS + _command_tools(cwd=False)
_SCHEMAS: dict[tuple[frozenset[str], bool, bool], list[dict]] = {(frozenset(), False, False): TOOL_SCHEMAS}

TOOL_NAMES = frozenset(tool["name"] for tool in TOOL_SCHEMAS)


def tool_schemas(features: frozenset[str] = frozenset(), *, patch_model: bool = False) -> list[dict]:
    """Schema theo khả năng CLI khai báo, để bản CLI đang cài không nhận công cụ hay tham số nó chưa hiểu.

    ``patch_model``: model của bước là GPT; cùng khả năng "patch" thì dùng apply_patch thay edit_file, write_file.
    GPT cũng không có update_plan (chủ web chọn ngày 2026-10-14): ở hai lượt thi, 6 Luna dành 29/96 rồi 29/90 lượt
    chỉ để cập nhật danh sách việc, mỗi lượt một bước, và lời nhắc gửi chung lượt không đổi được thói quen đó."""
    key = frozenset(features) & FEATURES
    patch = patch_model and "patch" in key
    if (key, patch, patch_model) not in _SCHEMAS:
        browsing = []
        if "browser" in key:
            act = "browser_act" in key
            browsing = [_open_tool(act, "browser_outside" in key), *_BROWSER_TOOLS[1:],
                        *(_BROWSER_ACT_TOOLS if act else [])]
        skills = [_tool('load_skill', 'Đọc toàn bộ SKILL.md theo tên trong danh sách skills của dự án. Nạp trước khi áp dụng; không tự chạy script.',
                        {'name': {'type': 'string', 'description': 'Tên skill trong danh sách.'}})] if 'skills' in key else []
        mcp = [
            _tool('mcp_list_tools', 'Xem tên, mô tả và inputSchema công cụ của MCP đang bật. Đọc trước khi gọi.',
                  {'server': {'type': 'string'}}),
            _tool('mcp_call_tool', 'Gọi công cụ MCP đã xem schema. CLI hỏi người dùng mỗi lần. Không gửi bí mật trong tham số.',
                  {'server': {'type': 'string'}, 'tool': {'type': 'string'}, 'arguments_json': {'type': 'string'}})
        ] if 'mcp' in key else []
        # Công cụ mới đứng cuối danh sách, để phần đầu giống hệt bản cũ và prompt cache vẫn dùng lại được.
        files = [tool for tool in _file_tools(key, patch) if not (patch_model and tool["name"] == "update_plan")]
        _SCHEMAS[(key, patch, patch_model)] = (files + _command_tools(cwd="cwd" in key) + browsing + skills + mcp
                                               + ([_FIND] if "explore_v2" in key else [])
                                               + ([_ASK] if "question" in key else [])
                                               + ([_READ_OUTPUT] if "output_files" in key else [])
                                               + ([_EXPLORE] if "subagent" in key else [])
                                               + ([_READ_HISTORY] if "recall" in key else [])
                                               + ([_PYTHON] if "python_exec" in key else [])
                                               + ([_tool('record_acceptance',
                                                   'Ghi trạng thái một tiêu chí nghiệm thu với evidence_id thực do công cụ trả về. '
                                                   'Mã thoát 0 chỉ chứng minh lệnh chạy thành công; ghi rõ phạm vi và phần chưa xác minh. '
                                                   'Bằng chứng phải thuộc bản sửa hiện tại; không dùng kết quả cũ sau khi sửa tiếp.',
                                                   {'criterion': {'type': 'string'},
                                                    'status': {'type': 'string', 'enum': ['passed', 'failed', 'unverified']},
                                                    'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
                                                    'note': {'type': 'string'}})] if 'task_state' in key else []))
    return _SCHEMAS[(key, patch, patch_model)]

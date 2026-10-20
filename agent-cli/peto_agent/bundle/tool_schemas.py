# Tệp sinh tự động từ backend/features/agent/tools.py bởi agent-cli/tools/make_bundle.py.
# Đừng sửa tay: sửa tệp nguồn ở backend rồi chạy lại công cụ đó.
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
# agent con chỉ đọc (purpose "explore"). CLI 0.29.1: "english_tools" gửi mô tả công cụ bằng tiếng Anh (xem ``EN``).
FEATURES = frozenset({"cwd", "browser", "browser_act", "browser_outside", "skills", "mcp", "explore_v2", "edit_v2",
                      "question", "patch", "title", "steer", "jobs_notify", "plan_mode", "btw", "read_more", "task_state",
                      "output_files", "wrapup", "user_guide", "subagent", "recall", "python_exec", "english_tools", "context_budget"})
# Công cụ của agent con explore: chỉ tìm và đọc trong dự án (theo agent "explore" của opencode).
EXPLORE_TOOLS = ("list_files", "find_files", "search_files", "read_file")
# Số bước tối đa của agent con theo độ kỹ: nhanh, vừa, kỹ.
EXPLORE_DEPTHS = {"quick": 4, "medium": 8, "thorough": 15}

# Bản tiếng Anh của mọi mô tả (khả năng "english_tools", chủ web chọn ngày 2026-10-19). Mô tả công cụ được gửi kèm mỗi
# bước và tiếng Việt tốn nhiều token hơn, như lời nhắc Agent đã chuyển sang tiếng Anh ngày 2026-10-15. Mỗi mô tả tiếng
# Việt khai bản dịch ngay cạnh nó qua ``_en``, nên schema tiếng Việt của các CLI cũ giữ nguyên từng chữ. Tên công cụ,
# tham số, enum và cấu trúc giống hệt nhau; chỉ chữ mô tả đổi. Bản dịch viết gọn nhưng giữ đủ mọi ràng buộc. Nhãn
# "(nên chọn)" giữ nguyên vì bài thi tìm đúng chữ đó.
EN: dict[str, str] = {}


def _en(vi: str, en: str) -> str:
    """Ghi bản tiếng Anh của một mô tả và trả lại đúng chữ tiếng Việt."""
    EN[vi] = en
    return vi


def _english(tools: list[dict]) -> list[dict]:
    """Bản sao của schema với mọi mô tả đổi sang tiếng Anh; mô tả chưa có bản dịch giữ nguyên (test bắt chỗ thiếu)."""
    def convert(node):
        if isinstance(node, dict):
            return {key: EN.get(value, value) if key == "description" and isinstance(value, str) else convert(value)
                    for key, value in node.items()}
        if isinstance(node, list):
            return [convert(item) for item in node]
        return node
    return [convert(tool) for tool in tools]


_PATH = {"type": "string", "description": _en("Đường dẫn tương đối tính từ gốc dự án, ví dụ src/app.py; '.' là gốc.",
                                              "Path relative to the project root, e.g. src/app.py; '.' is the root.")}
_SHELL = {
    "type": ["string", "null"],
    "description": _en("Trên Windows: 'cmd' hay 'powershell'; null là cmd. Chọn powershell khi lệnh cần cmdlet "
                       "(Get-ChildItem…), biến $env: hay cú pháp PowerShell; hệ khác thì bỏ qua và dùng shell mặc định.",
                       "Windows: 'cmd' or 'powershell'; null is cmd. Use powershell for cmdlets (Get-ChildItem…), $env: "
                       "or PowerShell syntax; ignored on other systems."),
}
_CWD = {
    "type": ["string", "null"],
    "description": _en("Thư mục chạy lệnh, tương đối tính từ gốc dự án, ví dụ frontend; null là gốc dự án. Mỗi lệnh mở "
                       "một shell mới nên cd ở lệnh trước không giữ sang lệnh sau: dùng tham số này thay cho cd.",
                       "Folder to run in, relative to the project root, e.g. frontend; null is the root. Each command "
                       "gets a new shell, so cd never carries over: use this instead."),
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


_START_LINE = _en("Dòng bắt đầu, tính từ 1. null là từ đầu tệp.", "First line, from 1. null is the file start.")
_FILE_TOOLS = [
    _tool(
        "list_files",
        _en("Liệt kê tệp và thư mục trong dự án, bỏ qua node_modules, .venv, .git, dist, build và những gì .gitignore ở "
            "gốc dự án bỏ qua (biết đường dẫn thì vẫn đọc được bằng read_file). Dùng để nắm cấu trúc trước khi đọc.",
            "List project files and folders, skipping node_modules, .venv, .git, dist, build and root .gitignore "
            "entries (read_file still reads known paths). Use to learn the layout before reading."),
        {
            "path": _PATH,
            "depth": {"type": ["integer", "null"],
                      "description": _en("Số tầng thư mục, 1 đến 4. null là 2.", "Folder depth, 1 to 4. null is 2.")},
        },
    ),
    _tool(
        "read_file",
        _en("Đọc một tệp chữ trong dự án, có thể theo khoảng dòng. Kết quả là nội dung nguyên văn, không kèm số dòng, "
            "cùng tổng số dòng của tệp.",
            "Read a project text file, optionally a line range. Returns verbatim content without line numbers, plus "
            "the total line count."),
        {
            "path": _PATH,
            "start_line": {"type": ["integer", "null"], "description": _START_LINE},
            "end_line": {
                "type": ["integer", "null"],
                "description": _en("Dòng kết thúc, tính cả dòng này. null đọc tối đa 160 dòng; khoảng chỉ định tối đa "
                                   "400 dòng. Dùng next_start_line trong kết quả để đọc tiếp khi cần.",
                                   "Last line, inclusive. null reads up to 160 lines; a range up to 400. Continue with "
                                   "next_start_line."),
            },
        },
    ),
    _tool(
        "search_files",
        _en("Tìm biểu thức chính quy (cú pháp Python re) trong các tệp chữ của dự án, bỏ qua thư mục nặng và những gì "
            ".gitignore bỏ qua. Trả về tối đa 100 dòng khớp kèm tên tệp và số dòng.",
            "Regex search (Python re) over project text files, skipping heavy folders and .gitignore entries. Returns "
            "up to 100 matching lines with file and line number."),
        {
            "pattern": {"type": "string", "description": _en("Biểu thức chính quy cần tìm.", "Regex to find.")},
            "path": {"type": ["string", "null"],
                     "description": _en("Thư mục hoặc tệp để tìm. null là cả dự án.",
                                        "Folder or file to search. null is the whole project.")},
            "glob": {"type": ["string", "null"],
                     "description": _en("Lọc tên tệp, ví dụ *.py. null là mọi tệp chữ.",
                                        "File name filter, e.g. *.py. null is all text files.")},
        },
    ),
    _tool(
        "edit_file",
        _en("Sửa một tệp bằng cách thay đúng một đoạn. Người dùng xem diff và phải đồng ý. old_text phải chép nguyên văn "
            "từ lần đọc gần nhất và chỉ xuất hiện một lần; tệp phải chưa bị đổi kể từ lần đọc đó.",
            "Replace exactly one passage in a file. The user sees the diff and must approve. old_text must be copied "
            "verbatim from the latest read and occur once; the file must be unchanged since."),
        {
            "path": _PATH,
            "old_text": {"type": "string",
                         "description": _en("Đoạn cần thay, nguyên văn, đủ dài để chỉ khớp một chỗ.",
                                            "Verbatim passage to replace, long enough to match once.")},
            "new_text": {"type": "string", "description": _en("Đoạn thay vào.", "Replacement.")},
        },
    ),
    _tool(
        "write_file",
        _en("Tạo tệp mới với toàn bộ nội dung, hoặc ghi đè cả tệp khi thật cần. Người dùng xem nội dung và phải đồng ý. "
            "Tệp đã có thì ưu tiên edit_file.",
            "Create a file with full content, or overwrite a whole file when truly needed. The user sees it and must "
            "approve. Prefer edit_file for existing files."),
        {
            "path": _PATH,
            "content": {"type": "string", "description": _en("Toàn bộ nội dung tệp.", "Full file content.")},
        },
    ),
    _tool(
        "update_plan",
        _en("Ghi danh sách việc của yêu cầu đang làm để người dùng thấy Peto định làm gì và đang tới đâu. Dùng khi yêu "
            "cầu có từ ba việc trở lên hoặc đụng nhiều tệp; gọi lại mỗi khi xong một việc. Không đụng gì trên máy nên "
            "không phải xin phép. Việc một bước thì đừng dùng.",
            "Show the user the current request's task list and progress. Use for requests with 3+ tasks or many "
            "files; call again as each task finishes. Changes nothing, needs no permission. Skip for one-step work."),
        {
            "steps": {
                "type": "array",
                "description": _en("Các việc theo thứ tự làm, tối đa 10 mục.", "Tasks in order, at most 10."),
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string",
                                  "description": _en("Một dòng ngắn nói việc cần làm.", "One short line.")},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "running", "done"],
                            "description": _en("pending là chưa làm, running là đang làm, done là đã xong.",
                                               "pending, running (in progress) or done."),
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
        _en("Xóa một tệp chữ trong dự án. Người dùng xem nội dung sắp mất và phải đồng ý; sau đó họ hoàn tác được bằng "
            "/undo. Chỉ xóa khi yêu cầu cần tới. Đừng xóa bằng run_command: lệnh xóa của hệ điều hành không hoàn tác "
            "được.",
            "Delete a project text file. The user sees the content and must approve; /undo restores it. Only when the "
            "request needs it. Never delete via run_command: OS deletes can't be undone."),
        {"path": _PATH},
    ),
    _tool(
        "move_file",
        _en("Đổi tên hoặc chuyển một tệp chữ sang chỗ khác trong dự án, nội dung giữ nguyên. Người dùng phải đồng ý; sau "
            "đó họ hoàn tác được bằng /undo. Đích phải chưa có tệp. Đừng đổi tên bằng run_command.",
            "Rename or move a project text file, keeping content. The user must approve; /undo reverts it. The "
            "destination must not exist. Never rename via run_command."),
        {
            "path": _PATH,
            "new_path": {"type": "string",
                         "description": _en("Đường dẫn mới, tương đối tính từ gốc dự án.",
                                            "New path relative to the project root.")},
        },
    ),
]


_NUMBERED = ("Each content line starts with its line number and a tab (like cat -n); it is not file content, never "
             "copy it into old_text. Includes the total line count.")
# Bản mới của ba công cụ tệp (GĐ 4 theo OpenCode), thay đúng chỗ bản cũ trong danh sách khi CLI khai báo khả năng.
_READ_V2 = _tool(
    "read_file",
    _en("Đọc một tệp chữ trong dự án, có thể theo khoảng dòng. Mỗi dòng trong content bắt đầu bằng số dòng rồi một ký tự "
        "tab (như cat -n): số đó không thuộc tệp, đừng chép vào old_text. Kèm tổng số dòng của tệp.",
        "Read a project text file, optionally a line range. " + _NUMBERED),
    _FILE_TOOLS[1]["parameters"]["properties"],
)
# "read_more" (CLI 0.25.0): nhật ký thật của chủ web có 88/269 lần đọc bị cắt ở 160 dòng, một nửa là tệp chừng 186
# dòng, và mỗi lần đọc thiếu tốn thêm một bước. Đọc tới 1000 dòng (khoảng 32.000 ký tự) như opencode khuyên đọc một
# lần cho đủ thay vì nhiều khúc nhỏ.
_READ_V3 = _tool(
    "read_file",
    _en("Đọc một tệp chữ trong dự án, cả tệp hoặc một khoảng dòng. Mỗi dòng trong content bắt đầu bằng số dòng rồi một ký "
        "tự tab (như cat -n): số đó không thuộc tệp, đừng chép vào old_text. Kèm tổng số dòng của tệp. Mỗi lần đọc tới "
        "1000 dòng hay khoảng 32.000 ký tự: tệp ngắn hơn thế thì đọc cả tệp một lần, đừng chia nhiều khúc nhỏ.",
        "Read a project text file, whole or a line range. " + _NUMBERED + " Up to 1000 lines or about 32,000 "
        "characters per read: read shorter files whole in one call, not in chunks."),
    {
        "path": _PATH,
        "start_line": {"type": ["integer", "null"], "description": _START_LINE},
        "end_line": {
            "type": ["integer", "null"],
            "description": _en("Dòng kết thúc, tính cả dòng này. null là tới cuối tệp (tối đa 1000 dòng mỗi lần). Dùng "
                               "next_start_line trong kết quả để đọc tiếp khi cần.",
                               "Last line, inclusive. null is the end of file (max 1000 lines per read). Continue with "
                               "next_start_line."),
        },
    },
)
_SEARCH_V2 = _tool(
    "search_files",
    _en("Tìm biểu thức chính quy (cú pháp Python re) trong các tệp chữ của dự án, bỏ qua thư mục nặng và những gì "
        ".gitignore bỏ qua. Kết quả gộp theo tệp, tệp sửa gần nhất trước; mỗi chỗ khớp có số dòng và nội dung dòng. "
        "Tối đa 100 chỗ khớp. Tìm tệp theo tên thì dùng find_files.",
        "Regex search (Python re) over project text files, skipping heavy folders and .gitignore entries. Grouped by "
        "file, most recently modified first; each match has line number and text. Up to 100 matches. Find files by "
        "name with find_files."),
    _FILE_TOOLS[2]["parameters"]["properties"],
)
_EDIT_V2 = _tool(
    "edit_file",
    _en("Sửa một tệp bằng cách thay một đoạn. Người dùng xem diff và phải đồng ý; tệp phải chưa bị đổi kể từ lần đọc gần "
        "nhất. old_text chép từ lần đọc đó, không kèm số dòng. Khớp nguyên văn trước; không khớp thì CLI thử khớp gần "
        "đúng (bỏ qua khoảng trắng đầu và cuối dòng, thụt lề khác) và ghi rõ cho người dùng. Đoạn phải chỉ khớp một chỗ, "
        "trừ khi replace_all là true.",
        "Replace one passage in a file. The user sees the diff and must approve; the file must be unchanged since the "
        "latest read. Copy old_text from that read without line numbers. Exact match first, else the CLI tries an "
        "approximate match (ignoring edge whitespace and indentation) and tells the user. Must match once unless "
        "replace_all is true."),
    {
        **_FILE_TOOLS[3]["parameters"]["properties"],
        "replace_all": {"type": ["boolean", "null"],
                        "description": _en("true thay mọi chỗ khớp nguyên văn với old_text; null hoặc false chỉ một chỗ.",
                                           "true replaces every exact match; null or false one.")},
    },
)
_FIND = _tool(
    "find_files",
    _en("Tìm tệp theo tên bằng mẫu glob, ví dụ **/*.py, src/**/test_*.ts hay *.json; bỏ qua thư mục nặng và những gì "
        ".gitignore bỏ qua. Trả tối đa 100 đường dẫn, tệp sửa gần nhất trước. Tìm theo nội dung thì dùng search_files.",
        "Find files by glob, e.g. **/*.py, src/**/test_*.ts, *.json; skips heavy folders and .gitignore entries. Up "
        "to 100 paths, most recently modified first. Search contents with search_files."),
    {
        "pattern": {"type": "string",
                    "description": _en("Mẫu glob: * khớp trong một tên, ** khớp qua nhiều thư mục, ? một ký tự.",
                                       "Glob: * within a name, ** across folders, ? one character.")},
        "path": {"type": ["string", "null"],
                 "description": _en("Thư mục để tìm. null là cả dự án.", "Folder to search. null is the whole project.")},
    },
)


_ASK = _tool(
    "ask_user",
    _en("Hỏi người dùng giữa chừng bằng câu hỏi có lựa chọn, rồi làm tiếp với câu trả lời. Chỉ hỏi khi có quyết định thật "
        "sự của người dùng mà mã nguồn và mặc định hợp lý không trả lời được; không dùng để xin quyền sửa tệp hay chạy "
        "lệnh (CLI đã hỏi). Người dùng luôn có thêm ô tự trả lời, nên đừng thêm lựa chọn \"Khác\". Phương án nên chọn đặt "
        "đầu, nhãn kết thúc bằng \"(nên chọn)\".",
        "Ask the user a multiple-choice question mid-task, then continue. Only for real user decisions the code and "
        "sensible defaults can't settle; never for edit or command permission (the CLI asks). A free-text box is always "
        "added, so no \"Other\" option. Put the recommended option first, its label ending with \"(nên chọn)\"."),
    {
        "questions": {
            "type": "array", "description": _en("Một tới ba câu hỏi.", "1 to 3 questions."),
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["question", "header", "options", "multiple"],
                "properties": {
                    "question": {"type": "string",
                                 "description": _en("Câu hỏi đầy đủ, kết thúc bằng dấu hỏi.",
                                                    "Full question ending with a question mark.")},
                    "header": {"type": "string",
                               "description": _en("Nhãn ngắn, tối đa 12 ký tự.", "Short label, max 12 characters.")},
                    "options": {
                        "type": "array", "description": _en("Hai tới bốn lựa chọn.", "2 to 4 options."),
                        "items": {"type": "object", "additionalProperties": False, "required": ["label", "description"],
                                  "properties": {"label": {"type": "string",
                                                           "description": _en("1–5 chữ.", "1 to 5 words.")},
                                                 "description": {"type": "string",
                                                                 "description": _en("Chọn cái này thì sao.",
                                                                                    "What picking it means.")}}},
                    },
                    "multiple": {"type": ["boolean", "null"],
                                 "description": _en("true cho chọn nhiều; null là chọn một.",
                                                    "true allows several; null one.")},
                },
            },
        },
    },
)
_PATCH = _tool(
    "apply_patch",
    _en("Sửa, tạo, xóa hay đổi tên tệp bằng một bản patch (có thể nhiều tệp một lần). Người dùng xem diff từng tệp và đồng "
        "ý một lần cho cả bản patch. Tệp sửa hay xóa phải đã đọc và chưa đổi kể từ lần đọc đó; một chỗ không khớp là không "
        "ghi tệp nào. Định dạng: *** Begin Patch, rồi từng mục *** Add File: đường/dẫn (mọi dòng bắt đầu bằng +), "
        "*** Delete File: đường/dẫn, *** Update File: đường/dẫn (có thể kèm *** Move to: đường/mới) với các đoạn @@ gồm "
        "dòng ' ' giữ nguyên, '-' bỏ, '+' thêm; cuối cùng *** End Patch.",
        "Edit, create, delete or rename files with one patch (multiple files allowed). The user sees each diff and "
        "approves once. Updated or deleted files must be read and unchanged since; any mismatch writes nothing. "
        "Format: *** Begin Patch, then entries *** Add File: path (all lines start with +), *** Delete File: path, "
        "*** Update File: path (optional *** Move to: new/path) with @@ hunks of ' ' kept, '-' removed, '+' added "
        "lines; then *** End Patch."),
    {"patch_text": {"type": "string",
                    "description": _en("Toàn bộ bản patch, từ *** Begin Patch tới *** End Patch.",
                                       "Full patch from *** Begin Patch to *** End Patch.")}},
)


# "output_files" (CLI 0.25.0): output vượt 20.000 ký tự được CLI lưu đủ vào tệp trên máy người dùng, kết quả lệnh chỉ
# giữ phần đầu và cuối kèm output_id.
_READ_OUTPUT = _tool(
    "read_output",
    _en("Đọc hoặc tìm trong output đầy đủ của một lệnh đã chạy, khi kết quả run_command hay read_command_output có "
        "output_id (output dài bị bỏ phần giữa). Chỉ đọc dữ liệu CLI đã lưu trên máy nên không cần xin phép. Có pattern "
        "thì trả tối đa 40 dòng khớp kèm số dòng; không có thì đọc theo khoảng dòng, tối đa 400 dòng.",
        "Read or search a finished command's full output when a run_command or read_command_output result has "
        "output_id (long output lost its middle). Reads only CLI-saved local data; no permission needed. With "
        "pattern: up to 40 matching lines with numbers; else a line range up to 400 lines."),
    {
        "output_id": {"type": "string",
                      "description": _en("Mã output_id trong kết quả lệnh.", "output_id from the command result.")},
        "pattern": {"type": ["string", "null"],
                    "description": _en("Biểu thức chính quy (cú pháp Python re) cần tìm, ví dụ error|failed. null là đọc "
                                       "theo khoảng dòng.",
                                       "Regex (Python re), e.g. error|failed. null reads by line range.")},
        "start_line": {"type": ["integer", "null"],
                       "description": _en("Dòng bắt đầu, tính từ 1. null là 1.", "First line, from 1. null is 1.")},
        "end_line": {"type": ["integer", "null"],
                     "description": _en("Dòng kết thúc, tính cả dòng này. null là đọc tối đa 400 dòng.",
                                        "Last line, inclusive. null reads up to 400 lines.")},
    },
)


# "subagent" (CLI 0.27.0, theo tool/plugin/subagent.ts và agent "explore" của opencode).
_EXPLORE = _tool(
    "explore",
    _en("Giao một việc dò tìm cho agent con chỉ đọc: nó tự tìm và đọc trong dự án (list_files, find_files, search_files, "
        "read_file) với ngữ cảnh riêng, rồi chỉ trả kết luận về đây. Dùng khi cần dò rộng nhiều tệp, nhiều chỗ mà chỉ cần "
        "kết luận; không dùng cho một tệp đã biết. Agent con không thấy hội thoại này, nên task phải đủ ý. Mỗi bước của nó "
        "trừ hạn mức như một bước thường.",
        "Delegate a search to a read-only subagent: it searches and reads the project (list_files, find_files, "
        "search_files, read_file) in its own context and returns only its conclusion. For broad sweeps where only the "
        "conclusion matters, not one known file. It can't see this conversation, so make the task self-contained. "
        "Each of its steps costs quota like a normal step."),
    {
        "task": {"type": "string",
                 "description": _en("Việc cần dò, viết đủ ý: tìm gì, ở đâu, trả về những gì (tệp, dòng, kết luận).",
                                    "Self-contained task: what to find, where, what to return (files, lines, "
                                    "conclusion).")},
        "depth": {"type": "string", "enum": list(EXPLORE_DEPTHS),
                  "description": _en("Độ kỹ: quick (tối đa 4 bước), medium (8), thorough (15).",
                                     "quick (up to 4 steps), medium (8), thorough (15).")},
    },
)


_READ_HISTORY = _tool(
    "read_history",
    _en("Tra phần hội thoại đã lưu trước tóm tắt của đúng phiên đang mở: yêu cầu, lời Peto và kết quả công cụ. "
        "Tìm chữ nguyên văn, tối đa 12 mục và 32.000 ký tự; đọc tiếp bằng next_entry/next_character. "
        "Không chạy lại công cụ, không khôi phục quyền cũ. Dữ liệu lịch sử có thể đã lỗi thời.",
        "Search this session's history saved before compaction: requests, Peto's replies, tool results. Literal text, "
        "up to 12 entries and 32,000 characters; continue with next_entry/next_character. Doesn't rerun tools or "
        "restore permissions. May be outdated."),
    {"pattern": {"type": ["string", "null"],
                 "description": _en("Chữ cần tìm; null là đọc lần lượt.", "Text to find; null reads in order.")},
     "start_entry": {"type": ["integer", "null"],
                     "description": _en("Số mục từ 1; null là mục đầu.", "Entry number from 1; null is the first.")},
     "start_character": {"type": ["integer", "null"],
                         "description": _en("Vị trí ký tự từ 0 trong mục đầu; dùng next_character nếu mục dài.",
                                            "Character offset from 0 in the first entry; next_character for long "
                                            "entries.")}},
)


def explore_schemas(features: frozenset[str] = frozenset()) -> list[dict]:
    """Công cụ của agent con explore: đúng bản các công cụ đọc mà CLI của phiên khai báo, không gì khác."""
    key = frozenset(features) & FEATURES
    tools = _file_tools(key) + ([_FIND] if "explore_v2" in key else [])
    tools = [tool for tool in tools if tool["name"] in EXPLORE_TOOLS]
    return _english(tools) if "english_tools" in key else tools


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
    _en("Chạy mã Python nhiều dòng trực tiếp trên máy người dùng, không qua shell nên không phải quote/escape python -c. "
        "Dùng cho chẩn đoán, đọc metadata và xử lý dữ liệu bằng Python. Chịu chính sách quyền chạy lệnh như run_command; "
        "có timeout, output và mã thoát. Chỉ tác động trong phạm vi công việc được giao.",
        "Run multi-line Python directly on the user's machine, no shell, so no python -c quoting. For diagnostics, "
        "metadata and data processing. Same permission policy as run_command; timeout, output and exit code. Stay "
        "within the assigned work."),
    {"code": {"type": "string",
              "description": _en("Mã Python nguyên văn, có thể nhiều dòng, tối đa 12.000 ký tự.",
                                 "Verbatim Python source, multi-line allowed, up to 12,000 characters.")},
     "python": {"type": ["string", "null"],
                "description": _en("Tên hoặc đường dẫn trình thông dịch, không kèm tham số; null dùng Python của Peto.",
                                   "Interpreter name or path, no arguments; null uses Peto's Python.")},
     "timeout_seconds": {"type": ["integer", "null"],
                         "description": _en("1 đến 600 giây, null là 120.", "1 to 600 seconds, null is 120.")},
     "cwd": _CWD},
)


_JOB_ID = _en("Mã lệnh nền do start_command trả về.", "Job ID from start_command.")


def _command_tools(cwd: bool) -> list[dict]:
    where = {"cwd": _CWD} if cwd else {}
    place = "ở gốc dự án hoặc thư mục con cwd" if cwd else "trong thư mục gốc dự án"
    place_en = "in the project root or the cwd subfolder" if cwd else "in the project root"
    return [
        _tool(
            "start_command",
            _en("Chạy một lệnh nền trên máy người dùng rồi trả về ngay: dùng cho dev server, watch, tiến trình chạy lâu "
                "không tự kết thúc. Người dùng phải đồng ý trước. Lệnh vẫn chạy sau khi yêu cầu xong, tới khi gọi "
                "stop_command hoặc tới khi người dùng đóng peto. Lệnh có điểm dừng (test, build) thì dùng run_command.",
                "Start a background command on the user's machine and return at once: dev servers, watchers, "
                "processes that don't exit. The user must approve. It keeps running after the request until "
                "stop_command or peto closes. For commands that finish (tests, builds) use run_command."),
            {
                "command": {"type": "string",
                            "description": _en("Lệnh cần chạy nền, ví dụ npm run dev.", "Command, e.g. npm run dev.")},
                "shell": _SHELL,
                **where,
            },
        ),
        _tool(
            "read_command_output",
            _en("Đọc phần output mới của một lệnh nền, kèm trạng thái và mã thoát nếu nó đã dừng. Mỗi lần đọc tốn một "
                "bước, nên đặt wait_seconds để chờ sẵn thay vì hỏi đi hỏi lại.",
                "Read a background command's new output, plus status and exit code once stopped. Each read costs a "
                "step: set wait_seconds rather than polling."),
            {
                "job_id": {"type": "string", "description": _JOB_ID},
                "wait_seconds": {
                    "type": ["integer", "null"],
                    "description": _en("Chờ tối đa bao nhiêu giây để có output mới, 0 đến 30. null là 5.",
                                       "Seconds to wait for new output, 0 to 30. null is 5."),
                },
            },
        ),
        _tool(
            "stop_command",
            _en("Dừng một lệnh nền, giết cả cây tiến trình. Không phải xin phép vì chỉ dừng tiến trình Peto đã tạo.",
                "Stop a background command and its process tree. No permission needed: only Peto's own processes."),
            {"job_id": {"type": "string", "description": _JOB_ID}},
        ),
        _tool(
            "run_command",
            _en(f"Chạy một lệnh {place} trên máy người dùng. Người dùng phải đồng ý trước. Dùng cho test, build, lint. "
                "Trả về mã thoát và output đã cắt gọn.",
                f"Run a command {place_en} on the user's machine. The user must approve. For tests, builds, lint. "
                "Returns exit code and trimmed output."),
            {
                "command": {"type": "string",
                            "description": _en("Lệnh cần chạy, ví dụ npm test hoặc python -m pytest.",
                                               "Command, e.g. npm test or python -m pytest.")},
                "timeout_seconds": {"type": ["integer", "null"],
                                    "description": _en("Thời hạn tính bằng giây, 1 đến 600. null là 120.",
                                                       "Seconds, 1 to 600. null is 120.")},
                "shell": _SHELL,
                **where,
            },
        ),
    ]


_VIEWPORT = {
    "type": ["string", "null"],
    "description": _en("'desktop' (máy tính 1280×800) hoặc 'mobile' (điện thoại 390×844, giả lập màn hình cảm ứng); null "
                       "là desktop khi mở trang, còn khi chụp là giữ khung đang dùng.",
                       "'desktop' (1280×800) or 'mobile' (390×844 phone, touch emulated); null is desktop when "
                       "opening, the current frame when screenshotting."),
}

_RESULT_EN = ("Returns title, HTTP status, console and JavaScript errors, failed requests and visible elements "
              "(headings, buttons, inputs, links, images missing alt)")
_NO_IMAGE_EN = "No image: call browser_screenshot to look, even in the same step."
_OPEN_DESCRIPTION = _en(
    "Mở hoặc tải lại một trang web chạy trên máy người dùng trong trình duyệt ẩn (hồ sơ riêng, không có tài khoản "
    "của họ). Chỉ nhận localhost, 127.0.0.1, ::1; trang ngoài bị từ chối. Trả về tiêu đề, mã HTTP, lỗi console, "
    "lỗi JavaScript và request hỏng, cùng các phần tử đang hiện (tiêu đề, nút, ô nhập, liên kết, ảnh thiếu alt). "
    "Không kèm ảnh: cần nhìn thì gọi browser_screenshot, cùng bước cũng được.",
    "Open or reload a page served on the user's machine in a hidden browser (own profile, none of their accounts). "
    "Only localhost, 127.0.0.1, ::1; outside pages are refused. " + _RESULT_EN + ". " + _NO_IMAGE_EN,
)
_ACT_EN = ("elements have numbers in square brackets, e.g. [3], for browser_click and browser_type. If a background "
           "command's server isn't listening yet, it waits up to 15 seconds, so it can follow start_command in the "
           "same step.")
# Với CLI bấm, gõ được (đợt 2): phần tử thao tác được có số, và trang của dev server vừa bật được chờ.
_OPEN_DESCRIPTION_ACT = _en(_OPEN_DESCRIPTION + (
    " Phần tử thao tác được có số trong ngoặc vuông, ví dụ [3], để dùng với browser_click và browser_type. Có lệnh "
    "nền đang chạy mà server chưa nghe cổng thì chờ tối đa 15 giây, nên gọi ngay sau start_command trong cùng bước "
    "được."
), EN[_OPEN_DESCRIPTION] + " Interactive " + _ACT_EN)


# Với CLI mở được trang ngoài (đợt 3, chủ web chọn ngày 2026-09-24): chỉ xem, trình duyệt riêng không cookie, hỏi mỗi
# tên miền. Thay câu "trang ngoài bị từ chối" của hai mô tả trên.
_OPEN_DESCRIPTION_OUTSIDE = _en(
    "Mở hoặc tải lại một trang web. Trang trên máy người dùng (localhost, 127.0.0.1, ::1) mở trong trình duyệt của dự "
    "án. Trang ngoài máy (http, https) mở trong một trình duyệt riêng không cookie, không đăng nhập, chỉ xem: lần đầu "
    "mỗi tên miền người dùng được hỏi, địa chỉ dài bất thường luôn hỏi lại, địa chỉ trong mạng nhà bị từ chối. Trả về "
    "tiêu đề, mã HTTP, lỗi console, lỗi JavaScript và request hỏng, cùng các phần tử đang hiện (tiêu đề, nút, ô nhập, "
    "liên kết, ảnh thiếu alt); trên trang ngoài, link ghi kèm địa chỉ sau dấu → để mở tiếp. Không kèm ảnh: cần nhìn "
    "thì gọi browser_screenshot, cùng bước cũng được.",
    "Open or reload a page. Pages on the user's machine (localhost, 127.0.0.1, ::1) open in the project browser. "
    "Outside pages (http, https) open view-only in a separate browser without cookies or login: the user is asked "
    "once per domain, unusually long addresses are always re-asked, home-network addresses are refused. "
    + _RESULT_EN + "; on outside pages links show their address after →. " + _NO_IMAGE_EN,
)
_OPEN_ACT_NOTE = _en(
    " Trên trang trên máy, phần tử thao tác được có số trong ngoặc vuông, ví dụ [3], để dùng với browser_click và "
    "browser_type. Có lệnh nền đang chạy mà server chưa nghe cổng thì chờ tối đa 15 giây, nên gọi ngay sau "
    "start_command trong cùng bước được.",
    " On local pages, interactive " + _ACT_EN,
)


def _open_tool(act: bool, outside: bool = False) -> dict:
    if outside:
        description = _en(_OPEN_DESCRIPTION_OUTSIDE + (_OPEN_ACT_NOTE if act else ""),
                          EN[_OPEN_DESCRIPTION_OUTSIDE] + (EN[_OPEN_ACT_NOTE] if act else ""))
        url = _en("Địa chỉ trang: trang trên máy, ví dụ http://localhost:5173/ (lấy đúng địa chỉ dev server in ra), hoặc "
                  "trang ngoài người dùng đưa, ví dụ https://docs.python.org/3/.",
                  "Page address: local, e.g. http://localhost:5173/ (as the dev server prints it), or an outside page "
                  "the user gave, e.g. https://docs.python.org/3/.")
    else:
        description = _OPEN_DESCRIPTION_ACT if act else _OPEN_DESCRIPTION
        url = _en("Địa chỉ trang, ví dụ http://localhost:5173/ (lấy đúng địa chỉ dev server in ra).",
                  "Page address, e.g. http://localhost:5173/ (as the dev server prints it).")
    return _tool("browser_open", description, {"url": {"type": "string", "description": url}, "viewport": _VIEWPORT})


# Đợt 1 của trình duyệt (chủ web chọn ngày 2026-09-23): chỉ xem, không bấm hay gõ, và chỉ trang chạy trên máy.
_BROWSER_TOOLS = [
    _open_tool(act=False),
    _tool(
        "browser_screenshot",
        _en("Chụp trang đang mở. Ảnh tới ở tin kế tiếp, sau kết quả các công cụ của bước này, và tốn nhiều token hơn chữ: "
            "chỉ chụp khi cần nhìn bố cục, màu sắc hay chỗ bị tràn.",
            "Screenshot the open page. The image comes in the next message, after this step's tool results, and costs "
            "more tokens than text: only to check layout, colours or overflow."),
        {
            "viewport": _VIEWPORT,
            "full_page": {"type": ["boolean", "null"],
                          "description": _en("true chụp cả trang dài (tối đa 4000px); null hoặc false chỉ phần đang hiện.",
                                             "true captures the full page (up to 4000px); null or false the visible "
                                             "part.")},
        },
    ),
    _tool(
        "browser_read",
        _en("Đọc chữ đang hiện trên trang đang mở (tối đa 20.000 ký tự), kèm lỗi mới xuất hiện từ lần xem trước.",
            "Read the open page's visible text (up to 20,000 characters), plus errors new since the last look."),
        {"selector": {"type": ["string", "null"],
                      "description": _en("CSS selector của phần cần đọc, ví dụ main hoặc #loi; null là cả trang.",
                                         "CSS selector to read, e.g. main or #error; null is the whole page.")}},
    ),
]

_TARGET = {
    "type": "string",
    "description": _en("Phần tử cần thao tác: số trong ngoặc vuông ở danh sách phần tử của kết quả gần nhất (ví dụ 3), "
                       "hoặc CSS selector chỉ khớp một phần tử đang hiện (ví dụ #gui).",
                       "Element: a bracketed number from the latest element list (e.g. 3), or a CSS selector matching "
                       "one visible element (e.g. #send)."),
}
_ACCEPT_DIALOG = {
    "type": ["boolean", "null"],
    "description": _en("Nếu thao tác này làm trang hỏi confirm hay prompt: true chọn OK, null hoặc false chọn Hủy. "
                       "alert luôn được đóng.",
                       "If this triggers confirm or prompt: true picks OK, null or false Cancel. alert is always "
                       "dismissed."),
}
KEYS = ["Enter", "Escape", "Tab", "Shift+Tab", "Backspace", "Delete", "Space", "ArrowUp", "ArrowDown", "ArrowLeft",
        "ArrowRight", "Home", "End", "PageUp", "PageDown"]

# Đợt 2 (chủ web chọn ngày 2026-09-23): bấm, gõ trên trang đang xem, hỏi quyền một lần cho mỗi trang; người dùng tự
# đăng nhập trong cửa sổ, Peto không gõ mật khẩu.
_BROWSER_ACT_TOOLS = [
    _tool(
        "browser_click",
        _en("Bấm một phần tử trên trang đang mở bằng chuột thật, như người dùng (tự cuộn tới nó). Lần đầu thao tác trên mỗi "
            "trang, người dùng được hỏi. Trả về những gì đổi: trang mới hay địa chỉ mới, chữ mới hiện, phần tử mới hiện "
            "hoặc vừa đổi trạng thái (có số mới), lỗi, hộp thoại, việc bị chặn. Phần tử bị che hay bị tắt thì báo lỗi "
            "thay vì bấm. Hộp chọn (select) thì dùng browser_type.",
            "Click an element on the open page with a real mouse, like the user (scrolls to it). The user is asked "
            "the first time per page. Returns what changed: new page or address, new text, new or changed elements "
            "(new numbers), errors, dialogs, blocked actions. Covered or disabled elements report an error instead. "
            "For select boxes use browser_type."),
        {"target": _TARGET, "accept_dialog": _ACCEPT_DIALOG},
    ),
    _tool(
        "browser_type",
        _en("Gõ chữ vào ô nhập (thay chữ đang có; chữ rỗng là xóa), hoặc chọn một lựa chọn trong hộp chọn theo chữ hiện "
            "của nó. Trả về chữ ô đang có sau khi gõ và những gì đổi như browser_click. Không gõ được vào ô mật khẩu: "
            "cần đăng nhập thì dùng browser_login.",
            "Type into an input (replaces its text; empty clears it) or pick a select option by its text. Returns the "
            "input's resulting text and what changed, like browser_click. No password fields: use browser_login."),
        {
            "target": _TARGET,
            "text": {"type": "string",
                     "description": _en("Chữ cần gõ, hoặc chữ của lựa chọn cần chọn.",
                                        "Text to type, or the option text to pick.")},
            "submit": {"type": ["boolean", "null"],
                       "description": _en("true nhấn Enter sau khi gõ (thường là gửi form).",
                                          "true presses Enter after typing (usually submits).")},
            "accept_dialog": _ACCEPT_DIALOG,
        },
    ),
    _tool(
        "browser_press",
        _en("Nhấn một phím trên phần tử đang được chọn (focus) của trang đang mở, ví dụ Escape để đóng hộp thoại, Tab để "
            "chuyển ô, PageDown để cuộn. Trả về những gì đổi và phần tử đang được chọn.",
            "Press a key on the page's focused element, e.g. Escape closes a dialog, Tab moves fields, PageDown "
            "scrolls. Returns what changed and the focused element."),
        {"key": {"type": "string", "enum": KEYS, "description": _en("Phím cần nhấn.", "Key to press.")},
         "accept_dialog": _ACCEPT_DIALOG},
    ),
    _tool(
        "browser_login",
        _en("Nhờ người dùng tự đăng nhập (hay làm bước chỉ họ làm được: mã 2FA, CAPTCHA) trong cửa sổ trình duyệt của Peto, "
            "ở trang đang mở, rồi chờ họ báo xong. Mật khẩu họ gõ không tới Peto; đăng nhập được nhớ cho dự án này. Trả về "
            "trang sau khi xong, hoặc lỗi nếu họ bỏ qua.",
            "Ask the user to log in (or do what only they can: 2FA, CAPTCHA) in Peto's browser window at the open "
            "page, then wait for them. Their password never reaches Peto; the login is remembered for this project. "
            "Returns the page afterwards, or an error if they skip."),
        {"reason": {"type": "string",
                    "description": _en("Một câu ngắn nói vì sao cần họ, ví dụ: trang /admin cần đăng nhập.",
                                       "One short sentence why, e.g.: /admin requires login.")}},
    ),
]

# Schema cho CLI không khai báo khả năng nào (bản 0.9.7 trở về trước): giữ nguyên từng chữ.
TOOL_SCHEMAS = _FILE_TOOLS + _command_tools(cwd=False)
_SCHEMAS: dict[tuple[frozenset[str], bool, bool], list[dict]] = {(frozenset(), False, False): TOOL_SCHEMAS}

TOOL_NAMES = frozenset(tool["name"] for tool in TOOL_SCHEMAS)

_SKILLS = [_tool("load_skill",
                 _en("Đọc toàn bộ SKILL.md theo tên trong danh sách skills của dự án. Nạp trước khi áp dụng; không tự "
                     "chạy script.",
                     "Read a skill's full SKILL.md by its name in the project's skills list. Load before applying; "
                     "never run its scripts yourself."),
                 {"name": {"type": "string", "description": _en("Tên skill trong danh sách.", "Skill name from the list.")}})]
_MCP = [
    _tool("mcp_list_tools",
          _en("Xem tên, mô tả và inputSchema công cụ của MCP đang bật. Đọc trước khi gọi.",
              "List an enabled MCP server's tools: names, descriptions, inputSchema. Read before calling."),
          {"server": {"type": "string"}}),
    _tool("mcp_call_tool",
          _en("Gọi công cụ MCP đã xem schema. CLI hỏi người dùng mỗi lần. Không gửi bí mật trong tham số.",
              "Call an MCP tool after reading its schema. The CLI asks the user each time. No secrets in arguments."),
          {"server": {"type": "string"}, "tool": {"type": "string"}, "arguments_json": {"type": "string"}}),
]
_ACCEPTANCE = _tool(
    "record_acceptance",
    _en("Ghi trạng thái một tiêu chí nghiệm thu với evidence_id thực do công cụ trả về. "
        "Mã thoát 0 chỉ chứng minh lệnh chạy thành công; ghi rõ phạm vi và phần chưa xác minh. "
        "Bằng chứng phải thuộc bản sửa hiện tại; không dùng kết quả cũ sau khi sửa tiếp.",
        "Record one acceptance criterion's status with real tool-issued evidence_ids. Exit code 0 only proves the "
        "command succeeded; state scope and what is unverified. Evidence must be from the current revision; never "
        "reuse results from before later edits."),
    {"criterion": {"type": "string"},
     "status": {"type": "string", "enum": ["passed", "failed", "unverified"]},
     "evidence_ids": {"type": "array", "items": {"type": "string"}},
     "note": {"type": "string"}},
)


def tool_schemas(features: frozenset[str] = frozenset(), *, patch_model: bool = False) -> list[dict]:
    """Schema theo khả năng CLI khai báo, để bản CLI đang cài không nhận công cụ hay tham số nó chưa hiểu.

    ``patch_model``: model của bước là GPT; cùng khả năng "patch" thì dùng apply_patch thay edit_file, write_file.
    GPT cũng không có update_plan (chủ web chọn ngày 2026-10-14): ở hai lượt thi, 6 Luna dành 29/96 rồi 29/90 lượt
    chỉ để cập nhật danh sách việc, mỗi lượt một bước, và lời nhắc gửi chung lượt không đổi được thói quen đó.
    Có "english_tools" thì mọi mô tả là tiếng Anh; công cụ, tham số và thứ tự giống hệt bản không có nó."""
    key = frozenset(features) & FEATURES
    patch = patch_model and "patch" in key
    if (key, patch, patch_model) not in _SCHEMAS:
        browsing = []
        if "browser" in key:
            act = "browser_act" in key
            browsing = [_open_tool(act, "browser_outside" in key), *_BROWSER_TOOLS[1:],
                        *(_BROWSER_ACT_TOOLS if act else [])]
        # Công cụ mới đứng cuối danh sách, để phần đầu giống hệt bản cũ và prompt cache vẫn dùng lại được.
        files = [tool for tool in _file_tools(key, patch) if not (patch_model and tool["name"] == "update_plan")]
        tools = (files + _command_tools(cwd="cwd" in key) + browsing + (_SKILLS if "skills" in key else [])
                 + (_MCP if "mcp" in key else [])
                 + ([_FIND] if "explore_v2" in key else [])
                 + ([_ASK] if "question" in key else [])
                 + ([_READ_OUTPUT] if "output_files" in key else [])
                 + ([_EXPLORE] if "subagent" in key else [])
                 + ([_READ_HISTORY] if "recall" in key else [])
                 + ([_PYTHON] if "python_exec" in key else [])
                 + ([_ACCEPTANCE] if "task_state" in key else []))
        _SCHEMAS[(key, patch, patch_model)] = _english(tools) if "english_tools" in key else tools
    return _SCHEMAS[(key, patch, patch_model)]

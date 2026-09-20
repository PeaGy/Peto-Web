"""Công cụ của Peto Agent.

Máy chủ định nghĩa schema để CLI không tự khai thêm công cụ; chương trình trên máy người dùng mới là nơi chạy công
cụ, kiểm đường dẫn và hỏi người dùng trước khi sửa tệp hay chạy lệnh.
"""

from __future__ import annotations

_PATH = {"type": "string", "description": "Đường dẫn tương đối tính từ gốc dự án, ví dụ src/app.py; '.' là gốc."}
_SHELL = {
    "type": ["string", "null"],
    "description": "Trên Windows: 'cmd' hay 'powershell'; null là cmd. Chọn powershell khi lệnh cần cmdlet "
                   "(Get-ChildItem…), biến $env: hay cú pháp PowerShell; hệ khác thì bỏ qua và dùng shell mặc định.",
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


TOOL_SCHEMAS = [
    _tool(
        "list_files",
        "Liệt kê tệp và thư mục trong dự án, bỏ qua node_modules, .venv, .git, dist, build. Dùng để nắm cấu trúc "
        "trước khi đọc.",
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
        "Tìm biểu thức chính quy (cú pháp Python re) trong các tệp chữ của dự án. Trả về tối đa 100 dòng khớp kèm "
        "tên tệp và số dòng.",
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
    _tool(
        "start_command",
        "Chạy một lệnh nền trên máy người dùng rồi trả về ngay: dùng cho dev server, watch, tiến trình chạy lâu không "
        "tự kết thúc. Người dùng phải đồng ý trước. Lệnh vẫn chạy sau khi yêu cầu xong, tới khi gọi stop_command hoặc "
        "tới khi người dùng đóng peto. Lệnh có điểm dừng (test, build) thì dùng run_command.",
        {
            "command": {"type": "string", "description": "Lệnh cần chạy nền, ví dụ npm run dev."},
            "shell": _SHELL,
        },
    ),
    _tool(
        "read_command_output",
        "Đọc phần output mới của một lệnh nền, kèm trạng thái và mã thoát nếu nó đã dừng. Mỗi lần đọc tốn một bước, "
        "nên đặt wait_seconds để chờ sẵn thay vì hỏi đi hỏi lại.",
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
        "Chạy một lệnh trong thư mục gốc dự án trên máy người dùng. Người dùng phải đồng ý trước. Dùng cho test, "
        "build, lint. Trả về mã thoát và output đã cắt gọn.",
        {
            "command": {"type": "string", "description": "Lệnh cần chạy, ví dụ npm test hoặc python -m pytest."},
            "timeout_seconds": {"type": ["integer", "null"], "description": "Thời hạn tính bằng giây, 1 đến 600. null là 120."},
            "shell": _SHELL,
        },
    ),
]

TOOL_NAMES = frozenset(tool["name"] for tool in TOOL_SCHEMAS)

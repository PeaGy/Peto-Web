"""Luật tự duyệt của bài thi: trả lời thay người dùng mỗi khi Peto xin quyền.

Bài thi chạy trên máy thật. Windows Home không có Windows Sandbox, nên luật này là lớp bảo vệ chính:

- Sửa, ghi, xóa, đổi tên tệp: đồng ý, vì Peto tự giới hạn trong thư mục dự án, ở đây là bản sao tạm của bài thi.
- Lệnh: chỉ đồng ý lệnh xem, build, test, chạy của đúng bộ công cụ các bài dùng (Python, .NET, Node, git chỉ đọc).
  Không đường dẫn ra ngoài thư mục bài, không địa chỉ ngoài máy, không cài gói, không xóa hay chuyển tệp bằng lệnh,
  không tắt tiến trình. Lệnh khác bị từ chối và ghi lại để chấm.
- Trước lệnh chạy code (python, dotnet, node), quét những tệp Peto vừa sửa hay tạo, tìm thứ rõ ràng nguy hiểm: xóa tệp,
  gọi mạng, chạy tiến trình khác, đọc biến môi trường, đường dẫn ra ngoài. Có thì không chạy.
- Trang trên máy: cho bấm, gõ. Trang ngoài: chỉ tên miền bài cho phép. Nhờ đăng nhập: bỏ qua.

Đây không phải sandbox. Code Peto viết rồi chạy qua test vẫn chạy bằng quyền của người dùng; bộ quét chỉ bắt những thứ lộ
liễu, đủ cho lỗi vô ý chứ không chặn được kẻ cố tình. Vì vậy bài thi không bao giờ cho lệnh ra ngoài thư mục tạm.
"""

from __future__ import annotations

import base64
import functools
import io
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from peto_agent.ui import UI


@dataclass
class Decision:
    allowed: bool
    reason: str


ALLOW = Decision(True, "")

LOCAL_URL = re.compile(r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?(?:[/?#][^\s\"']*)?$", re.I)
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s\"']+", re.I)
# Chuyển hướng vô hại: gộp stderr vào stdout, hay bỏ output. Mọi chuyển hướng khác (ghi tệp) bị từ chối.
HARMLESS_REDIRECT = re.compile(r"(?<![\w>])[12]?>\s*(?:&\s*[12]|nul|\$null)\b", re.I)
POWERSHELL_DRIVE = re.compile(r"(?i)\b(env|variable|function|alias|hklm|hkcu|cert|wsman|registry)::?")
SECRET_NAME = re.compile(r"(?i)(^|[\\/])(\.env(\.[\w.-]*)?|[^\\/]*\.(pem|key|p12|pfx)|id_(rsa|dsa|ecdsa|ed25519)[^\\/]*)$")
CMD_FLAG = re.compile(r"^/[a-z?]{1,3}(:\S*)?$", re.I)
DOMAIN = re.compile(r"^(?:[a-z0-9-]+\.)+([a-z]{2,})(?::\d+)?(?:/\S*)?$", re.I)
FILE_EXTENSIONS = {"json", "txt", "html", "htm", "js", "css", "py", "cs", "md", "csv", "xml", "log", "png", "jpg",
                   "jpeg", "gif", "svg", "ico", "map", "ts", "tsx", "jsx", "yml", "yaml", "toml", "ini", "cfg", "sln",
                   "csproj", "dll", "exe", "pdb", "c", "h", "bin", "sav", "db", "sqlite", "lock", "mjs", "cjs"}

# Không có tasklist, netstat: danh sách tiến trình, kết nối của người dùng không cần gửi cho dịch vụ AI.
READ_ONLY_PROGRAMS = {"cd", "chdir", "dir", "ls", "type", "cat", "more", "findstr", "find", "where", "echo", "tree",
                      "ver", "sort", "fc", "comp", "mkdir", "md"}
POWERSHELL_READ_ONLY = {
    "get-childitem", "gci", "get-content", "gc", "select-string", "sls", "test-path", "get-location", "pwd",
    "resolve-path", "measure-object", "measure", "select-object", "select", "sort-object", "format-list", "fl",
    "format-table", "ft", "out-string", "out-null", "write-output", "write", "write-host", "convertto-json",
    "convertfrom-json", "start-sleep", "sleep", "get-command", "gcm", "get-item", "gi",
    "split-path", "join-path", "get-date", "set-location", "sl", "push-location", "pop-location", "new-item",
    "foreach-object", "%", "where-object", "?", "group-object", "get-member", "gm", "out-host", "write-warning"}
# PowerShell phân tích bằng chính bộ đọc cú pháp của nó: cho biến tự đặt trong lệnh ($r = Invoke-WebRequest …), try/catch,
# khối lệnh của ForEach-Object; mỗi lệnh con vẫn phải nằm trong danh sách.
SAFE_VARIABLES = {"_", "psitem", "null", "true", "false", "lastexitcode", "?", "matches", "input", "pwd", "error",
                  "args", "psversiontable"}
SAFE_METHODS = {"tostring", "trim", "trimstart", "trimend", "split", "substring", "replace", "contains", "startswith",
                "endswith", "tolower", "toupper", "indexof", "lastindexof", "padleft", "padright", "getstring",
                "getresponsestream", "readtoend", "equals", "gettype", "where", "foreach", "join", "format",
                "containskey", "getbytes"}
# cmd chỉ thay %TÊN% (biến môi trường); %{http_code} của curl thì để nguyên.
CMD_VARIABLE = re.compile(r"%[A-Za-z_][^%\s\"]*%")
HTTP_PROGRAMS = {"curl", "invoke-webrequest", "iwr", "invoke-restmethod", "irm", "wget"}
GIT_READ_ONLY = {"status", "diff", "log", "show", "ls-files", "rev-parse", "blame", "grep", "branch", "--version"}
PYTHON = {"python", "python3", "py"}
PYTHON_MODULES = {"unittest", "pytest", "py_compile", "compileall", "json.tool", "http.server", "doctest", "tabnanny"}
DOTNET_COMMANDS = {"build", "run", "test", "restore", "clean", "watch", "--info", "--version", "--list-sdks",
                   "--list-runtimes"}
NODE_SCRIPTS = (".js", ".mjs", ".cjs")

# Mẫu nguy hiểm trong code Peto vừa viết, theo đuôi tệp. Chỉ quét tệp Peto sửa hay tạo: code gốc của bài đã được soát.
_PY_RISKS = [
    (r"\bshutil\.(rmtree|move|copyfile|copytree|copy2?|chown)\b", "xóa hay chép tệp bằng shutil"),
    (r"\bos\.(system|popen|remove|unlink|rmdir|removedirs|rename|renames|replace|startfile|kill|exec\w*|spawn\w*)\b",
     "gọi hệ điều hành xóa, đổi tệp hay chạy lệnh"),
    (r"\b(subprocess|multiprocessing|ctypes|winreg|_winapi|msvcrt|webbrowser)\b", "chạy tiến trình hay gọi thẳng Windows"),
    (r"\b(socket|urllib|requests|http\.client|httpx|aiohttp|ftplib|smtplib|telnetlib)\b", "gọi mạng"),
    (r"\b(environ|getenv|putenv)\b", "đọc biến môi trường"),
    (r"\.(unlink|rmdir|rename|symlink_to|hardlink_to|chmod)\(", "xóa hay đổi tệp bằng pathlib"),
]
_CS_RISKS = [
    (r"\bProcess\b|System\.Diagnostics", "chạy tiến trình khác"),
    (r"\b(File|Directory)\.(Delete|Move|Replace|Copy)\b", "xóa hay chuyển tệp"),
    (r"\b(HttpClient|WebClient|WebRequest|TcpClient|Socket)\b", "gọi mạng"),
    (r"\b(Registry|DllImport|Marshal)\b", "gọi thẳng Windows"),
    (r"\bEnvironment\.(GetEnvironmentVariable|GetEnvironmentVariables|Exit|FailFast)\b", "đọc biến môi trường hay tắt"),
]
_JS_RISKS = [
    (r"\bchild_process\b|\bexec(Sync)?\(|\bspawn(Sync)?\(", "chạy tiến trình khác"),
    (r"\bfs\.(rm|rmSync|rmdir|rmdirSync|unlink|unlinkSync|rename|renameSync)\b", "xóa hay đổi tệp"),
    (r"\bprocess\.env\b", "đọc biến môi trường"),
    (r"require\(\s*['\"](https?|net|dgram|tls)['\"]\s*\)", "gọi mạng"),
]
_COMMON_RISKS = [
    (r"(?<![\w/])[A-Za-z]:[\\/]{1,2}(?!/)", "đường dẫn tuyệt đối trên ổ đĩa"),
    (r"\\\\\\\\[\w.$-]+", "đường dẫn mạng"),
    (r"(\.\.[\\/]){2,}", "đường dẫn ra ngoài thư mục dự án"),
    (r"\b(expanduser|USERPROFILE|APPDATA|LOCALAPPDATA|HOMEPATH)\b|Path\.home\(", "thư mục người dùng"),
]
CODE_RISKS = {".py": _PY_RISKS, ".cs": _CS_RISKS, ".js": _JS_RISKS, ".mjs": _JS_RISKS, ".cjs": _JS_RISKS}
SCRIPT_SUFFIXES = {".bat", ".cmd", ".ps1", ".vbs", ".sh"}
# Makefile chạy lệnh gì cũng được: bản gốc của bài thì đã soát, Peto sửa rồi thì không cho make chạy nữa.
MAKEFILES = {"makefile", "gnumakefile"}
PATH_LIKE = re.compile(r"[\w.\-\\/:~* ]+")


def risky_code(text: str, suffix: str) -> str | None:
    """Lý do code này bị coi là nguy hiểm, hoặc None. ``.csproj`` có Exec hay Target là chạy lệnh khi build."""
    if suffix == "makefile":
        return "Makefile đã bị sửa"
    if suffix == ".csproj":
        return "tệp dự án .NET chạy lệnh khi build" if re.search(r"<(Exec|Target)\b", text) else None
    if suffix in SCRIPT_SUFFIXES:
        return "tệp script lệnh"
    for pattern, reason in CODE_RISKS.get(suffix, []) + (_COMMON_RISKS if suffix in CODE_RISKS else []):
        if re.search(pattern, text):
            return reason
    return None


def changed_files(root: Path) -> list[str]:
    """Tệp đã đổi hay mới so với lần commit đầu của bài (bản sao bài thi là một kho git riêng)."""
    try:
        output = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-z", "-uall", "--no-renames"],
                                capture_output=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    entries = [entry for entry in output.decode("utf-8", "replace").split("\0") if entry]
    return [entry[3:] for entry in entries]


def scan_changes(root: Path) -> str | None:
    """Quét những tệp Peto đã sửa hay tạo; trả lý do nếu có tệp nguy hiểm."""
    for rel in changed_files(root):
        path = root / rel
        suffix = "makefile" if path.name.lower() in MAKEFILES else path.suffix.lower()
        if suffix not in CODE_RISKS and suffix not in SCRIPT_SUFFIXES and suffix not in {".csproj", "makefile"}:
            continue
        try:
            if path.stat().st_size > 1_000_000:
                return f"{rel} quá lớn để soát"
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # tệp đã bị xóa: không còn gì để chạy
        if reason := risky_code(text, suffix):
            return f"{rel}: {reason}"
    return None


def split_segments(command: str) -> list[str] | None:
    """Tách lệnh ở &&, ||, &, |, ; nằm ngoài dấu nháy. None khi dấu nháy không khép."""
    parts: list[str] = []
    current: list[str] = []
    quote = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current.append(char)
        elif command.startswith("&&", index) or command.startswith("||", index):
            parts.append("".join(current))
            current = []
            index += 2
            continue
        elif char in "&|;":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    if quote:
        return None
    parts.append("".join(current))
    return [part.strip() for part in parts]


def tokens(segment: str) -> list[str]:
    """Tách từ theo khoảng trắng; chuỗi trong nháy là một từ (bỏ dấu nháy)."""
    result: list[str] = []
    current: list[str] = []
    quote = None
    quoted = False
    for char in segment:
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "\"'":
            quote = char
            quoted = True
        elif char.isspace():
            if current or quoted:
                result.append("".join(current))
                current, quoted = [], False
        else:
            current.append(char)
    if current or quoted:
        result.append("".join(current))
    return result


POWERSHELL_OUTLINE = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$source = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('__SOURCE__'))
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
$result = @{ errors = @($errors).Count; commands = @(); variables = @(); assigned = @(); calls = @();
             redirects = @(); strings = @() }
foreach ($node in $ast.FindAll({ $true }, $true)) {
    if ($node -is [System.Management.Automation.Language.CommandAst]) {
        $result.commands += @{ name = $node.GetCommandName(); text = $node.Extent.Text;
                               dot = ($node.InvocationOperator -eq 'Dot') }
    } elseif ($node -is [System.Management.Automation.Language.VariableExpressionAst]) {
        $result.variables += @{ name = $node.VariablePath.UserPath; drive = $node.VariablePath.DriveName }
    } elseif ($node -is [System.Management.Automation.Language.AssignmentStatementAst]) {
        foreach ($target in $node.Left.FindAll({ $args[0] -is [System.Management.Automation.Language.VariableExpressionAst] }, $true)) {
            $result.assigned += $target.VariablePath.UserPath
        }
    } elseif ($node -is [System.Management.Automation.Language.ForEachStatementAst]) {
        $result.assigned += $node.Variable.VariablePath.UserPath
    } elseif ($node -is [System.Management.Automation.Language.InvokeMemberExpressionAst]) {
        $result.calls += @{ static = $node.Static; name = $node.Member.Extent.Text }
    } elseif ($node -is [System.Management.Automation.Language.FileRedirectionAst]) {
        $result.redirects += $node.Location.Extent.Text
    } elseif ($node -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
              $node -is [System.Management.Automation.Language.ExpandableStringExpressionAst]) {
        $result.strings += $node.Value
    }
}
$result | ConvertTo-Json -Depth 5 -Compress
"""


@functools.lru_cache(maxsize=256)
def powershell_outline(source: str) -> dict | None:
    """Các lệnh, biến, lời gọi hàm, chuyển hướng và chuỗi trong một lệnh PowerShell, theo bộ đọc cú pháp của chính
    PowerShell 5.1 (cũng là bản chạy lệnh của Peto). None khi máy không chạy được PowerShell."""
    if os.name != "nt":
        return None
    script = POWERSHELL_OUTLINE.replace("__SOURCE__", base64.b64encode(source.encode("utf-8")).decode("ascii"))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                              capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
        data = json.loads(done.stdout.decode("utf-8-sig", "replace") or "null")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return data if isinstance(data, dict) and "commands" in data else None


def _without_quoted(segment: str, quotes: str) -> str:
    return re.sub("|".join(f"{q}[^{q}]*{q}" for q in quotes), " ", segment)


def _program(word: str) -> str:
    name = PureWindowsPath(word).name.lower()
    return name[:-4] if name.endswith(".exe") else name


class CommandPolicy:
    """Quyết định một lệnh Peto xin chạy, trong thư mục ``directory`` của bản sao bài thi ``root``."""

    def __init__(self, root: Path, *, allow: tuple[str, ...] = (), deny: tuple[str, ...] = ()):
        self.root = root.resolve()
        self.allow = [re.compile(pattern, re.I) for pattern in allow]
        self.deny = [re.compile(pattern, re.I) for pattern in deny]

    def decide(self, command: str, directory: str | Path, shell: str = "cmd") -> Decision:
        text = command.strip()
        if not text:
            return Decision(False, "lệnh trống")
        if any(pattern.search(text) for pattern in self.deny):
            return Decision(False, "lệnh bài này cấm")
        if any(pattern.fullmatch(text) for pattern in self.allow):
            return ALLOW
        cwd = Path(directory).resolve()
        if not self._inside(cwd):
            return Decision(False, "thư mục chạy nằm ngoài bài thi")
        for url in URL.findall(text):
            if not LOCAL_URL.match(url):
                return Decision(False, f"địa chỉ ngoài máy: {url[:80]}")
        outline = powershell_outline(text) if shell == "powershell" else None
        if outline is not None:
            decision, runs_code = self._powershell(outline, cwd)
        else:
            decision, runs_code = self._plain(text, cwd, shell)
        if not decision.allowed:
            return decision
        if runs_code and (reason := scan_changes(self.root)):
            return Decision(False, f"code Peto vừa viết có thứ không an toàn ({reason})")
        return ALLOW

    def _plain(self, text: str, cwd: Path, shell: str) -> tuple[Decision, bool]:
        """cmd (và PowerShell khi không đọc được cú pháp): tách lệnh ở &&, |, ; rồi soát từng đoạn."""
        segments = split_segments(URL.sub("LOCAL_URL", HARMLESS_REDIRECT.sub(" ", text)))
        if segments is None:
            return Decision(False, "dấu nháy không khép"), False
        runs_code = False
        for segment in segments:
            if not segment:
                continue
            decision, code = self._segment(segment, cwd, shell)
            if not decision.allowed:
                return decision, False
            runs_code = runs_code or code
        return ALLOW, runs_code

    def _powershell(self, outline: dict, cwd: Path) -> tuple[Decision, bool]:
        """PowerShell theo cây cú pháp: biến chỉ được là biến tự đặt trong lệnh, không gọi hàm .NET tĩnh, không ghi tệp
        bằng chuyển hướng, không gọi lệnh qua biến; mỗi lệnh con soát như một đoạn lệnh thường."""
        if outline.get("errors"):
            return Decision(False, "không đọc được cú pháp lệnh PowerShell"), False
        assigned = {str(name).lower() for name in outline.get("assigned") or [] if name}
        for variable in outline.get("variables") or []:
            if variable.get("drive"):
                return Decision(False, f"đọc biến {variable['drive']}: (môi trường, registry…)"), False
            name = str(variable.get("name") or "")
            if name.lower() not in assigned and name.lower() not in SAFE_VARIABLES:
                return Decision(False, f"biến ${name} không đặt trong lệnh"), False
        for call in outline.get("calls") or []:
            name = str(call.get("name") or "")
            if call.get("static"):
                return Decision(False, f"gọi hàm .NET {name}"), False
            if name.lower() not in SAFE_METHODS:
                return Decision(False, f"gọi phương thức {name}"), False
        for target in outline.get("redirects") or []:
            if str(target).strip().lower() != "$null":
                return Decision(False, "ghi ra tệp bằng chuyển hướng"), False
        strings = [URL.sub("LOCAL_URL", str(value)) for value in outline.get("strings") or [] if value]
        decision = self._paths_ok(strings, cwd)
        if not decision.allowed:
            return decision, False
        runs_code = False
        for command in outline.get("commands") or []:
            if not command.get("name") or command.get("dot"):
                return Decision(False, "gọi lệnh qua biến hay chạy script"), False
            text = URL.sub("LOCAL_URL", HARMLESS_REDIRECT.sub(" ", str(command.get("text") or "")))
            decision, code = self._segment(text, cwd, "powershell", parsed=True)
            if not decision.allowed:
                return decision, False
            runs_code = runs_code or code
        return ALLOW, runs_code

    def _inside(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root)
            return True
        except (ValueError, OSError):
            return False

    def _paths_ok(self, words: list[str], cwd: Path) -> Decision:
        for word in words:
            if word == "LOCAL_URL" or CMD_FLAG.match(word):
                continue
            for piece in word.split("="):
                if not piece or piece.startswith("-"):
                    continue
                if SECRET_NAME.search(piece.rstrip("\\/")):
                    return Decision(False, "đụng tệp bí mật (.env, khóa)")
                if piece.startswith("~"):
                    return Decision(False, "đường dẫn thư mục người dùng")
                if piece.startswith("\\\\") or piece.startswith("//"):
                    return Decision(False, "đường dẫn mạng")
                # Chữ có ngoặc nhọn, nháy… (thân JSON của curl) không phải đường dẫn.
                looks_like_path = PATH_LIKE.fullmatch(piece) and (
                    "\\" in piece or "/" in piece or piece.startswith("..") or re.match(r"[A-Za-z]:", piece))
                if looks_like_path and not self._inside(cwd / piece):
                    return Decision(False, f"đường dẫn ra ngoài thư mục bài: {piece[:80]}")
        return ALLOW

    def _segment(self, segment: str, cwd: Path, shell: str, *, parsed: bool = False) -> tuple[Decision, bool]:
        """Một đoạn lệnh (chương trình và tham số). ``parsed``: đoạn lấy từ cây cú pháp PowerShell, biến và khối lệnh đã
        được soát ở _powershell."""
        if shell == "powershell" and not parsed:
            bare = _without_quoted(segment, "'\"")
            if re.search(r"[$`(){}@<>]", bare) or re.search(r"[$`]", _without_quoted(segment, "'")):
                return Decision(False, "cú pháp PowerShell ngoài phạm vi bài thi ($, khối lệnh, chuyển hướng)"), False
        elif shell != "powershell":
            if CMD_VARIABLE.search(segment) or re.search(r"[\^<>()]", _without_quoted(segment, '"')):
                return Decision(False, "cú pháp cmd ngoài phạm vi bài thi (%BIẾN%, ^, chuyển hướng, nhóm lệnh)"), False
        if POWERSHELL_DRIVE.search(segment):
            return Decision(False, "đọc biến môi trường hay registry"), False
        words = tokens(segment)
        if not words:
            return ALLOW, False
        decision = self._paths_ok(words, cwd)
        if not decision.allowed:
            return decision, False
        program, args = _program(words[0]), words[1:]
        if program in READ_ONLY_PROGRAMS or (shell == "powershell" and program in POWERSHELL_READ_ONLY):
            if program == "new-item" and "directory" not in [arg.lower() for arg in args]:
                return Decision(False, "New-Item chỉ được tạo thư mục; tệp thì dùng công cụ ghi tệp"), False
            return ALLOW, False
        if program == "git":
            sub = next((arg.lower() for arg in args if not arg.startswith("-") or arg == "--version"), "")
            if sub in GIT_READ_ONLY and not (sub == "branch" and any(a in {"-d", "-D", "-m", "-M"} for a in args)):
                return ALLOW, False
            return Decision(False, f"git {sub or '(trống)'} đổi kho; bài thi chỉ cho git xem"), False
        if program in PYTHON:
            return self._python(args, cwd)
        if program in {"make", "mingw32-make", "nmake"}:
            # Máy không có make thì người dùng thật cũng chỉ nhận lỗi "không tìm thấy": để Peto thấy đúng lỗi đó.
            return ALLOW, True
        if program == "dotnet":
            sub = (args[0].lower() if args else "")
            if sub in DOTNET_COMMANDS:
                return ALLOW, sub in {"build", "run", "test", "watch"}
            return Decision(False, f"dotnet {sub or '(trống)'} ngoài phạm vi (không cài gói, không tạo dự án)"), False
        if program == "node":
            if args and args[0].lower() in {"-v", "--version"}:
                return ALLOW, False
            script = next((arg for arg in args if not arg.startswith("-")), "")
            if script.lower().endswith(NODE_SCRIPTS) and self._inside(cwd / script):
                return ALLOW, True
            return Decision(False, "node chỉ được chạy tệp .js trong dự án"), False
        if program in {"npm", "npx", "yarn", "pnpm"}:
            # Script trong package.json chạy gì cũng được, còn npx tải gói về chạy: chưa bài nào cần, nên chưa cho.
            return Decision(False, f"{program}: bài thi chưa dùng npm"), False
        if program in HTTP_PROGRAMS or program == "curl.exe":
            if "LOCAL_URL" not in words:
                return Decision(False, "gọi HTTP phải tới địa chỉ trên máy (http://localhost)"), False
            for word in words[1:]:
                match = DOMAIN.match(word)
                if match and match.group(1).lower() not in FILE_EXTENSIONS:
                    return Decision(False, f"địa chỉ ngoài máy: {word[:80]}"), False
            return ALLOW, False
        return Decision(False, f"lệnh {words[0][:40]} ngoài danh sách của bài thi"), False

    def _python(self, args: list[str], cwd: Path) -> tuple[Decision, bool]:
        rest = list(args)
        while rest:
            if rest[0] in {"-u", "-B", "-3", "-E", "-I"} or re.fullmatch(r"-3\.\d+", rest[0]):
                rest.pop(0)
            elif len(rest) >= 2 and rest[0] in {"-X", "-W"}:
                del rest[:2]
            else:
                break
        if not rest or rest[0] in {"--version", "-V"}:
            return (ALLOW, False) if rest else (Decision(False, "python không kèm gì sẽ chờ bàn phím"), False)
        if rest[0] == "-m":
            module = rest[1] if len(rest) > 1 else ""
            if module in PYTHON_MODULES:
                return ALLOW, module != "http.server"
            if module in {"pip", "venv", "ensurepip"}:
                return Decision(False, "bài thi không cài gói hay tạo môi trường"), False
            return Decision(False, f"python -m {module or '(trống)'} ngoài danh sách của bài thi"), False
        if rest[0] == "-c":
            code = rest[1] if len(rest) > 1 else ""
            if reason := risky_code(code, ".py"):
                return Decision(False, f"python -c có thứ không an toàn ({reason})"), False
            return ALLOW, True
        script = rest[0]
        if script.lower().endswith(".py") and self._inside(cwd / script):
            return ALLOW, True
        return Decision(False, "python chỉ được chạy tệp .py trong dự án"), False


class Policy:
    """Luật của một bài: lệnh theo CommandPolicy, trang ngoài theo danh sách tên miền của bài."""

    def __init__(self, root: Path, *, sites: tuple[str, ...] = (), allow: tuple[str, ...] = (),
                 deny: tuple[str, ...] = ()):
        self.commands = CommandPolicy(root, allow=allow, deny=deny)
        self.sites = set(sites)

    def decide(self, pending: dict | None) -> Decision:
        if not pending:
            return Decision(False, "câu hỏi không rõ của gì")
        kind = pending["kind"]
        if kind == "file":
            return ALLOW
        if kind in {"command", "background"}:
            return self.commands.decide(pending["command"], pending["directory"], pending.get("shell", "cmd"))
        if kind == "page":
            return ALLOW  # Peto chỉ bấm, gõ trên trang của máy này (trình duyệt của dự án không mở trang ngoài)
        if kind == "site":
            if pending.get("unusual"):
                return Decision(False, "địa chỉ dài bất thường")
            if pending.get("site") in self.sites:
                return ALLOW
            return Decision(False, "trang ngoài bài thi không cho")
        return Decision(False, "loại câu hỏi bài thi không trả lời")


class PolicyUI(UI):
    """Giao diện của bài thi: ghi lại mọi thứ như terminal (không màu) và trả lời câu hỏi quyền theo Policy."""

    def __init__(self, policy: Policy):
        self.policy = policy
        self.pending: dict | None = None
        self.requests: list[dict] = []
        super().__init__(out=io.StringIO(), reader=self._read, colors=False, width=120)

    @property
    def transcript(self) -> str:
        return self.out.getvalue()

    def _read(self, prompt: str) -> str:
        # Câu hỏi ngoài ask_permission (xem tiếp diff…): Enter là bỏ qua.
        return ""

    def diff(self, title: str, before: str, after: str) -> None:
        super().diff(title, before, after)
        self.pending = {"kind": "file", "detail": title}

    def line(self, text: str = "", color: str | None = None) -> None:
        super().line(text, color)
        if text.strip().startswith("✎ Muốn đổi tên"):
            self.pending = {"kind": "file", "detail": text.strip()[2:]}

    def command(self, command: str, directory: str, timeout: int, *, shell: str = "cmd",
                background: bool = False) -> None:
        super().command(command, directory, timeout, shell=shell, background=background)
        self.pending = {"kind": "background" if background else "command", "command": command,
                        "directory": directory, "shell": shell}

    def page_permission(self, origin: str, action: str) -> None:
        super().page_permission(origin, action)
        self.pending = {"kind": "page", "detail": f"{origin} · {action}"}

    def site_permission(self, url: str, site: str, unusual: bool = False) -> None:
        super().site_permission(url, site, unusual)
        self.pending = {"kind": "site", "url": url, "site": site, "unusual": unusual}

    def hand_over(self, reason: str) -> None:
        super().hand_over(reason)
        self.requests.append({"kind": "login", "detail": reason, "answer": "n",
                              "reason": "bài thi không đăng nhập thay người dùng"})

    def wait_for_user(self) -> bool:
        return False

    def ask_permission(self, *, allow_session: bool = False, allow_always: bool = False,
                       session_label: str = "", question: str = "") -> str:
        pending, self.pending = self.pending, None
        decision = self.policy.decide(pending)
        record = dict(pending or {"kind": "unknown"})
        record.update(answer="y" if decision.allowed else "n", reason=decision.reason)
        self.requests.append(record)
        self.line(f"    [bài thi] {'đồng ý' if decision.allowed else 'từ chối'}"
                  + (f": {decision.reason}" if decision.reason else ""))
        return "y" if decision.allowed else "n"

    def bell(self) -> None:
        pass

    def title(self, text: str) -> None:
        pass

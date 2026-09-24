"""Conservative command-result hints, never used to grant execution permission."""
import re
import shlex

# Lệnh gọi HTTP tới server trên máy (curl, Invoke-WebRequest…): Peto đang thử app vừa sửa, kể cả khi lệnh được nối
# bằng && để gọi vài địa chỉ một lượt. Chỉ dùng để biết Peto đã kiểm lại việc mình làm, không bao giờ để cho phép chạy.
LOCAL_PROBE = re.compile(r"(?i)\b(curl(\.exe)?|wget|invoke-webrequest|iwr|invoke-restmethod|irm)\b.*"
                         r"\bhttps?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?\b")


def local_probe(command):
    return bool(LOCAL_PROBE.search(command))


def command_kind(command):
    # Shell expressions and wrappers are deliberately left unknown.
    if any(char in command for char in "&|;<>`\n\r"):
        return "other"
    try:
        words = [word.strip('"\'') for word in shlex.split(command, posix=False)]
    except ValueError:
        return "other"
    if not words:
        return "other"
    exe = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe").removesuffix(".cmd")
    args = words[1:]
    if any(arg in {"--help", "--version", "-h"} for arg in args):
        return "other"
    if exe in {"rg", "grep", "findstr"}:
        return "search"
    if exe in {"pytest", "vitest", "jest", "eslint", "tsc"}:
        return "check"
    if exe in {"python", "python3", "py"} and args[:2] in (["-m", "pytest"], ["-m", "unittest"]):
        return "check"
    if exe in {"npm", "pnpm", "yarn"} and (args[:1] in (["test"], ["build"], ["lint"], ["typecheck"])
            or args[:2] in (["run", "test"], ["run", "build"], ["run", "lint"], ["run", "typecheck"])):
        return "check"
    if exe in {"cargo", "dotnet", "go"} and args[:1] in (["test"], ["build"], ["check"], ["clippy"], ["vet"]):
        return "check"
    return "other"


def classify(command, result):
    kind = command_kind(command)
    output = str(result.get("output") or "")
    if result.get("error"):
        return "execution_error"
    code = result.get("exit_code")
    if code == 0:
        return "passed" if kind == "check" else "success"
    if code == 1 and kind == "search" and not output.strip():
        return "no_match"
    if kind == "check" and re.search(r"(?i)(?:^|[\\/\s\"])(?:pytest(?:\.exe)?|python(?:3)?(?:\.exe)?\"?\s+-m\s+pytest)(?:\s|$)", command):
        if code == 5:
            return "no_tests"
        if code in {2, 3, 4}:
            return "execution_error"
    if re.search(r"(?im)(not recognized as an internal or external command|command not found|"
                 r"is not recognized as the name of a cmdlet|CommandNotFoundException|"
                 r"ModuleNotFoundError:|No module named |Missing script:|ENOENT|No such file or directory)", output):
        return "environment_error"
    return "check_failed" if kind == "check" else "unknown_failure"

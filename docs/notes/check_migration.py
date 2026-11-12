"""Kiểm tra việc chuyển CLAUDE.md cũ sang CLAUDE.md mới và docs/notes/*.md không làm mất nội dung.

Cách dùng (từ gốc repo):

    git show 91e6b2f:CLAUDE.md > old-claude.md
    python docs/notes/check_migration.py old-claude.md

Không truyền tệp thì script tự lấy `git show <rev>:CLAUDE.md` (mặc định `--rev HEAD`; sau khi commit bản rút gọn,
dùng `--rev 91e6b2f`, bản cuối cùng còn đủ nội dung).

Script in ra mọi tiêu đề `##`/`###` và mọi dòng dài hơn 80 ký tự của tệp cũ không còn xuất hiện nguyên văn trong
CLAUDE.md mới hay docs/notes/*.md. Các dòng trạng thái commit đã sửa có chủ ý (bước 3: "not committed" thành
"committed `<hash>`") được liệt kê riêng. Mã thoát 1 nếu có dòng mất hoặc mục Invariants khác bản cũ.
Chỉ dùng thư viện chuẩn.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

NOTES = Path(__file__).resolve().parent
ROOT = NOTES.parent.parent
LONG = 80
INVARIANTS = "## Invariants — do not break these"

# Trạng thái commit cũ và mới đều quy về cùng một dấu, để nhận ra dòng chỉ đổi trạng thái.
NEW_STATUS = re.compile(r"committed `[0-9a-f]{7,40}`(, not deployed|; chưa deploy)?")
OLD_STATUS = re.compile(r"not committed(/deployed| or deployed)?|[Cc]hưa commit/deploy")


def status_key(line: str) -> str:
    return OLD_STATUS.sub("<STATUS>", NEW_STATUS.sub("<STATUS>", line))


def read_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def old_text(path: str | None, rev: str) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    result = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:CLAUDE.md"], capture_output=True)
    if result.returncode:
        sys.exit(f"Không đọc được {rev}:CLAUDE.md: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout.decode("utf-8")


def targets(lines: list[str]) -> list[tuple[int, str, bool]]:
    """(số dòng, dòng, là tiêu đề) của mọi tiêu đề ##/### ngoài khối code và mọi dòng dài."""
    found = []
    fence = False
    for number, line in enumerate(lines, 1):
        if line.startswith("```"):
            fence = not fence
        heading = not fence and (line.startswith("## ") or line.startswith("### "))
        if heading or len(line) > LONG:
            found.append((number, line, heading))
    return found


def section(lines: list[str], title: str) -> list[str] | None:
    try:
        start = lines.index(title)
    except ValueError:
        return None
    end = start + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    body = lines[start:end]
    while body and not body[-1].strip():
        body.pop()
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra CLAUDE.md đã chuyển sang docs/notes/ mà không mất dòng.")
    parser.add_argument("old", nargs="?", help="Tệp CLAUDE.md cũ (mặc định: git show <rev>:CLAUDE.md)")
    parser.add_argument("--rev", default="HEAD", help="Bản git để lấy CLAUDE.md cũ khi không truyền tệp")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    old = read_lines(old_text(args.old, args.rev))
    new_claude = read_lines((ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
    corpus = list(new_claude)
    notes = sorted(NOTES.glob("*.md"))
    for note in notes:
        corpus += read_lines(note.read_text(encoding="utf-8"))
    present = set(corpus)
    keyed = {}
    for line in corpus:
        keyed.setdefault(status_key(line), line)

    print(f"Tệp cũ: {len(old)} dòng. CLAUDE.md mới: {len(new_claude)} dòng. Tệp ghi chú: {len(notes)}.")
    if len(old) < 1000:
        print("Lưu ý: tệp cũ ngắn, có thể đây đã là bản rút gọn. Thử --rev 91e6b2f.")

    # Thay đổi có chủ ý: dòng có trạng thái commit cũ, không còn nguyên văn, nhưng có bản chỉ khác trạng thái.
    intended = {}
    for number, line in enumerate(old, 1):
        if OLD_STATUS.search(line) and line not in present and status_key(line) in keyed:
            intended[number] = keyed[status_key(line)]

    missing_headings, missing_lines = [], []
    for number, line, heading in targets(old):
        if line in present or number in intended:
            continue
        (missing_headings if heading else missing_lines).append((number, line))

    print(f"\nTiêu đề mất ({len(missing_headings)}):")
    for number, line in missing_headings:
        print(f"  {number}: {line}")
    print(f"\nDòng dài hơn {LONG} ký tự mất ({len(missing_lines)}):")
    for number, line in missing_lines:
        print(f"  {number}: {line}")
    print(f"\nThay đổi có chủ ý, trạng thái commit (bước 3) ({len(intended)}):")
    for number, line in intended.items():
        print(f"  {number}: {old[number - 1].strip()}")
        print(f"      -> {line.strip()}")

    old_inv, new_inv = section(old, INVARIANTS), section(new_claude, INVARIANTS)
    same = old_inv is not None and old_inv == new_inv
    print(f"\nMục Invariants trùng nguyên văn với bản cũ: {'có' if same else 'KHÔNG'}")
    return 0 if same and not missing_headings and not missing_lines else 1


if __name__ == "__main__":
    sys.exit(main())

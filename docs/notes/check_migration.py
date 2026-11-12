"""Kiểm tra việc chuyển CLAUDE.md cũ sang CLAUDE.md mới và docs/notes/*.md không làm mất nội dung.

Cách dùng (từ gốc repo):

    python docs/notes/check_migration.py                 # cũ: 91e6b2f, mới: HEAD
    python docs/notes/check_migration.py --new 81d00c0   # kiểm một commit bất kỳ
    python docs/notes/check_migration.py --new index     # kiểm phần đã `git add`, trước khi commit
    python docs/notes/check_migration.py old-claude.md   # tệp CLAUDE.md cũ lấy sẵn bằng git show

Phía cũ mặc định là `git show 91e6b2f:CLAUDE.md`, bản cuối cùng còn đủ nội dung (đổi bằng `--rev`). Phía mới chỉ
đọc nội dung git đã theo dõi ở `--new` (một commit, hoặc `index`), không đọc thư mục trên đĩa: một tệp ghi chú bị
.gitignore chặn sẽ không có trong commit, nên phải bị báo thiếu.

Script in ra mọi tiêu đề `##`/`###` và mọi dòng dài hơn 80 ký tự của tệp cũ không còn xuất hiện nguyên văn trong
CLAUDE.md mới hay docs/notes/*.md đã được theo dõi. Các dòng trạng thái commit đã sửa có chủ ý (bước 3: "not committed" thành
"committed `<hash>`") và các tham chiếu chéo trong CLAUDE.md đã sửa vì đích đã chuyển sang docs/notes/ được
liệt kê riêng. Mã thoát 1 nếu có dòng mất hoặc mục Invariants khác bản cũ.
Chỉ dùng thư viện chuẩn.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LONG = 80
INVARIANTS = "## Invariants — do not break these"

# Trạng thái commit cũ và mới đều quy về cùng một dấu, để nhận ra dòng chỉ đổi trạng thái.
NEW_STATUS = re.compile(r"committed `[0-9a-f]{7,40}`(, not deployed|; chưa deploy)?")
OLD_STATUS = re.compile(r"not committed(/deployed| or deployed)?|[Cc]hưa commit/deploy")

# Tham chiếu chéo trong CLAUDE.md đã sửa có chủ ý vì mục đích đã chuyển sang docs/notes/:
# dòng cũ -> đoạn phải có trong CLAUDE.md mới.
CROSS_REFERENCES = {
    'when the owner removed it (see the section at the top and "Roleplay mode (removed)"). Peto Agent uses the same '
    'core.': '"Roleplay mode\n(removed)" in `docs/notes/chat.md`',
    'Companion has its own persona, `COMPANION_SYSTEM_PROMPT` (see "Companion persona" under "Companion tab and voice':
        '(see "Companion persona" under "Companion tab and voice relay" in `docs/notes/companion.md`)',
    'Responses API, plus OpenAI\'s GPT-6 models as a user-selectable option (see "Model choice"). Registration is '
    '**open**:': '(see "Model choice" in `docs/notes/chat.md`)',
    '- `DESIGN.md` — frontend visual and copy conventions (see "Frontend conventions").':
        '(see "Frontend conventions" in `docs/notes/frontend.md`)',
}


def status_key(line: str) -> str:
    return OLD_STATUS.sub("<STATUS>", NEW_STATUS.sub("<STATUS>", line))


def read_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def git(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    if result.returncode:
        sys.exit(f"git {' '.join(args)} lỗi: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout.decode("utf-8")


def old_text(path: str | None, rev: str) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return git("show", f"{rev}:CLAUDE.md")


def tracked(new: str) -> dict[str, str]:
    """Nội dung CLAUDE.md và docs/notes/*.md mà git theo dõi ở commit `new`, hoặc trong index."""
    if new == "index":
        names = git("ls-files", "-z", "--", "CLAUDE.md", "docs/notes").split("\0")
        prefix = ":"
    else:
        names = git("ls-tree", "-r", "-z", "--name-only", new, "--", "CLAUDE.md", "docs/notes").split("\0")
        prefix = f"{new}:"
    names = [n for n in names if n == "CLAUDE.md" or (n.startswith("docs/notes/") and n.endswith(".md"))]
    return {name: git("show", prefix + name) for name in sorted(names)}


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
    parser.add_argument("--rev", default="91e6b2f", help="Bản git để lấy CLAUDE.md cũ khi không truyền tệp")
    parser.add_argument("--new", default="HEAD", help="Commit chứa bản mới, hoặc `index` cho phần đã git add")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    old = read_lines(old_text(args.old, args.rev))
    files = tracked(args.new)
    if "CLAUDE.md" not in files:
        sys.exit(f"{args.new} không có CLAUDE.md.")
    new_claude = read_lines(files.pop("CLAUDE.md"))
    corpus = list(new_claude)
    notes = list(files)
    for text in files.values():
        corpus += read_lines(text)
    present = set(corpus)
    keyed = {}
    for line in corpus:
        keyed.setdefault(status_key(line), line)

    print(f"Tệp cũ: {len(old)} dòng. Bản mới ({args.new}): CLAUDE.md {len(new_claude)} dòng, "
          f"{len(notes)} tệp ghi chú: {', '.join(Path(n).name for n in notes)}.")
    if len(old) < 1000:
        print("Lưu ý: tệp cũ ngắn, có thể đây đã là bản rút gọn. Kiểm lại --rev.")

    # Thay đổi có chủ ý: dòng có trạng thái commit cũ, không còn nguyên văn, nhưng có bản chỉ khác trạng thái.
    intended = {}
    for number, line in enumerate(old, 1):
        if OLD_STATUS.search(line) and line not in present and status_key(line) in keyed:
            intended[number] = keyed[status_key(line)]

    claude_text = "\n".join(new_claude)
    references = {}
    missing_headings, missing_lines = [], []
    for number, line, heading in targets(old):
        if line in present or number in intended:
            continue
        if line in CROSS_REFERENCES and CROSS_REFERENCES[line] in claude_text:
            references[number] = CROSS_REFERENCES[line]
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

    print(f"\nThay đổi có chủ ý, tham chiếu chéo trong CLAUDE.md ({len(references)}):")
    for number, target in references.items():
        print(f"  {number}: {old[number - 1].strip()}")
        print(f"      -> {' '.join(target.split())}")

    old_inv, new_inv = section(old, INVARIANTS), section(new_claude, INVARIANTS)
    same = old_inv is not None and old_inv == new_inv
    print(f"\nMục Invariants trùng nguyên văn với bản cũ: {'có' if same else 'KHÔNG'}")
    return 0 if same and not missing_headings and not missing_lines else 1


if __name__ == "__main__":
    sys.exit(main())

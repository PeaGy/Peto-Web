"""Sinh peto_agent/bundle/ từ các module thuần của backend (lộ trình nhiều nguồn, M3).

Nguồn trực tiếp (khóa API riêng) chạy không cần máy chủ Peto, nên CLI cần chính lời nhắc, schema công cụ và cách ghép
bước của máy chủ. Một nguồn duy nhất: các tệp backend dưới đây. Công cụ này chép chúng, đổi import sang tương đối, và
dừng nếu còn import nào trỏ về backend (FastAPI, DB, cấu hình). Test của backend và của CLI chạy ``--check`` để bắt bản
chép cũ.

    python agent-cli/tools/make_bundle.py          # ghi lại peto_agent/bundle/
    python agent-cli/tools/make_bundle.py --check  # chỉ so, lệch thì mã thoát 1
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
TARGET = REPO / "agent-cli" / "peto_agent" / "bundle"

# (tệp backend, tên module trong bundle, các dòng import cần đổi: mỗi dòng phải có đúng một lần)
SOURCES = (
    ("prompts/core.py", "core_prompt", {}),
    ("prompts/agent.py", "agent_prompts", {}),
    ("prompts/providers.py", "provider_prompts", {}),
    ("features/agent/tools.py", "tool_schemas", {}),
    ("features/agent/assembly.py", "assembly", {
        "from prompts import agent as agent_prompts\n": "from . import agent_prompts\n",
        "from prompts.core import CORE_PROMPT\n": "from .core_prompt import CORE_PROMPT\n",
        "from prompts.providers import provider_prompt\n": "from .provider_prompts import provider_prompt\n",
        "from features.agent.tools import FEATURES, explore_schemas, tool_schemas\n":
            "from .tool_schemas import FEATURES, explore_schemas, tool_schemas\n",
    }),
)
BACKEND_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:prompts|features|ai|core|shared|storage|fastapi|pydantic|anyio)\b",
                            re.MULTILINE)
HEADER = ("# Tệp sinh tự động từ backend/{path} bởi agent-cli/tools/make_bundle.py.\n"
          "# Đừng sửa tay: sửa tệp nguồn ở backend rồi chạy lại công cụ đó.\n")


def render() -> dict[str, str]:
    files: dict[str, str] = {}
    for path, name, rewrites in SOURCES:
        text = (BACKEND / path).read_text(encoding="utf-8").replace("\r\n", "\n")
        for old, new in rewrites.items():
            if text.count(old) != 1:
                raise SystemExit(f"backend/{path}: không thấy đúng một dòng import {old.strip()!r}")
            text = text.replace(old, new)
        if found := BACKEND_IMPORT.search(text):
            raise SystemExit(f"backend/{path}: còn import backend không chép được: {found.group(0).strip()!r}")
        files[f"{name}.py"] = HEADER.format(path=path) + text
    digest = hashlib.sha256("".join(files[name] for name in sorted(files)).encode("utf-8")).hexdigest()
    files["__init__.py"] = (
        '"""Lời nhắc, schema công cụ và cách ghép bước Agent của máy chủ Peto, chép nguyên văn cho nguồn trực tiếp.\n\n'
        "Sinh tự động bởi agent-cli/tools/make_bundle.py; đừng sửa tay.\n"
        '"""\n\n'
        f'SOURCE_DIGEST = "{digest}"\n')
    return files


def current() -> dict[str, str]:
    if not TARGET.is_dir():
        return {}
    return {path.name: path.read_text(encoding="utf-8").replace("\r\n", "\n") for path in TARGET.glob("*.py")}


def main(argv: list[str]) -> int:
    # Console Windows có thể không phải UTF-8: lời báo tiếng Việt không được làm hỏng lệnh.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    expected = render()
    if "--check" in argv:
        found = current()
        stale = sorted(name for name in set(expected) | set(found) if expected.get(name) != found.get(name))
        if stale:
            print("peto_agent/bundle lệch nguồn backend: " + ", ".join(stale) + ". Chạy agent-cli/tools/make_bundle.py.")
            return 1
        return 0
    TARGET.mkdir(exist_ok=True)
    for path in TARGET.glob("*.py"):
        if path.name not in expected:
            path.unlink()
    for name, text in expected.items():
        (TARGET / name).write_bytes(text.encode("utf-8"))
    print(f"Đã ghi {len(expected)} tệp vào {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

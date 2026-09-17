"""Chạy lệnh: lấy output và mã thoát, hết giờ thì giết cả cây tiến trình."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

from peto_agent import runner


def alive(pid: int) -> bool:
    if os.name == "nt":
        listed = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in listed
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_run_returns_output_and_exit_code(tmp_path):
    result = runner.run(f'"{sys.executable}" -c "print(\'xin chào\'); raise SystemExit(3)"', tmp_path, 30)
    assert result["exit_code"] == 3
    assert "xin chào" in result["output"]
    assert "error" not in result


def test_timeout_kills_the_whole_process_tree(tmp_path):
    marker = tmp_path / "grandchild.pid"
    script = tmp_path / "parent.py"
    script.write_text(textwrap.dedent(f"""
        import subprocess, sys, time
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        open(r"{marker}", "w").write(str(child.pid))
        time.sleep(60)
    """))
    result = runner.run(f'"{sys.executable}" "{script}"', tmp_path, 2)
    assert "quá 2 giây" in result["error"]
    time.sleep(0.5)
    assert not alive(int(marker.read_text()))


def test_cap_text_keeps_the_start_and_the_end():
    text = "đầu" + "x" * 30000 + "cuối"
    capped = runner.cap_text(text, 1000)
    assert capped.startswith("đầu") and capped.endswith("cuối")
    assert "bỏ bớt" in capped and len(capped) < 1100

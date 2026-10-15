"""Lệnh chạy nền: dev server, watch, tiến trình không có điểm dừng.

``run_command`` chờ lệnh chạy xong nên không mở được server. Ở đây mỗi lệnh chạy trong một tiến trình riêng, output
được một luồng gom vào bộ đệm, và Peto đọc lại khi cần. Lệnh nền sống qua nhiều yêu cầu, nhưng không sống quá phiên:
đóng peto là mọi lệnh nền bị giết cả cây tiến trình.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import outputs, runner
from .workspace import WorkspaceError

MAX_JOBS = 3
# Giữ phần cuối của output; phần đầu bị bỏ được ghi rõ để Peto không đoán phần thiếu.
KEEP_BYTES = 256 * 1024
MAX_WAIT_SECONDS = 30
DEFAULT_WAIT_SECONDS = 5


@dataclass
class Job:
    id: str
    command: str
    shell: str
    process: object
    started: float
    lock: threading.Lock = field(default_factory=threading.Lock)
    fresh: threading.Event = field(default_factory=threading.Event)
    buffer: bytearray = field(default_factory=bytearray)
    # Tổng số byte đã đọc được, số byte đã bị bỏ ở đầu, và số byte đã gửi cho Peto.
    total: int = 0
    dropped: int = 0
    sent: int = 0
    # Lệnh tự dừng thì CLI báo Peto một lần ở bước kế tiếp (CLI 0.20.0, theo opencode). Peto đã thấy nó dừng qua
    # read_command_output, hay chính Peto dừng nó, thì không báo nữa.
    reported: bool = False
    stopped_by_peto: bool = False
    # Khả năng "output_files" (CLI 0.25.0): cả output được ghi vào tệp; chỉ giữ tệp khi có lần đọc bị cắt hay mất phần
    # đầu, để Peto tìm lại bằng read_output.
    spool: outputs.Spool | None = None
    spool_kept: bool = False

    def running(self) -> bool:
        return self.process.poll() is None


class Jobs:
    """Sổ các lệnh nền của một phiên."""

    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._next = 1

    def running(self) -> list[Job]:
        return [job for job in self.jobs.values() if job.running()]

    def start(self, command: str, cwd: Path, shell: str = "cmd", *, spool: bool = False) -> Job:
        if len(self.running()) >= MAX_JOBS:
            raise WorkspaceError(f"Đang có {MAX_JOBS} lệnh nền chạy rồi; dừng bớt bằng stop_command trước.")
        process = runner.spawn(command, cwd, shell)
        job = Job(id=str(self._next), command=command, shell=shell, process=process, started=time.monotonic(),
                  spool=outputs.Spool() if spool else None)
        self._next += 1
        self.jobs[job.id] = job
        threading.Thread(target=self._reader, args=(job,), daemon=True).start()
        return job

    def _reader(self, job: Job) -> None:
        try:
            while chunk := job.process.stdout.read1(65536):
                if job.spool is not None:
                    job.spool.write(chunk)
                with job.lock:
                    job.buffer.extend(chunk)
                    job.total += len(chunk)
                    if len(job.buffer) > KEEP_BYTES:
                        extra = len(job.buffer) - KEEP_BYTES
                        del job.buffer[:extra]
                        job.dropped += extra
                job.fresh.set()
        except (OSError, ValueError):
            pass
        finally:
            if job.spool is not None:
                job.spool.close()
            job.fresh.set()

    def _job(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            known = ", ".join(f"#{key}" for key in self.jobs) or "chưa có lệnh nền nào"
            raise WorkspaceError(f"Không có lệnh nền #{job_id}. Đang có: {known}.")
        return job

    def read(self, job_id: str, wait_seconds: int | None = None) -> dict:
        """Phần output chưa gửi cho Peto, chờ tối đa ``wait_seconds`` giây để có cái mới."""
        job = self._job(job_id)
        wait = max(0, min(MAX_WAIT_SECONDS, DEFAULT_WAIT_SECONDS if wait_seconds is None else wait_seconds))
        deadline = time.monotonic() + wait
        while True:
            with job.lock:
                new = job.total > job.sent
            if new or not job.running() or time.monotonic() >= deadline:
                break
            job.fresh.clear()
            job.fresh.wait(min(0.25, max(0.0, deadline - time.monotonic())))
        with job.lock:
            start = max(job.sent, job.dropped)
            output = bytes(job.buffer[start - job.dropped:])
            lost = max(0, job.dropped - job.sent)
            job.sent = job.total
        text = output.decode("utf-8", errors="replace")
        if lost:
            text = f"… (bỏ bớt {lost} byte output cũ) …\n" + text
        running = job.running()
        if not running:
            job.reported = True
        saved = {}
        if job.spool is not None and (lost or len(text) > runner.MAX_RESULT_CHARS):
            job.spool_kept = True
            saved = {"output_id": job.spool.id, "output_note": "Output bị cắt; bản đầy đủ của cả lệnh nền đọc bằng "
                                                               "read_output."}
        return {
            "id": job.id,
            "command": job.command,
            "running": running,
            "exit_code": job.process.returncode,
            "seconds": round(time.monotonic() - job.started, 1),
            "output": runner.cap_text(text),
            **saved,
        }

    def finished(self) -> list[dict]:
        """Các lệnh vừa tự dừng mà Peto chưa biết: phần output chưa gửi kèm mã thoát, mỗi lệnh chỉ một lần."""
        done = []
        for job in self.jobs.values():
            if job.reported or job.stopped_by_peto or job.running():
                continue
            # Luồng đọc có thể chưa gom hết phần cuối: chờ chút cho chắc.
            job.fresh.wait(0.2)
            done.append(self.read(job.id, 0))
        return done

    def stop(self, job_id: str) -> dict:
        job = self._job(job_id)
        job.stopped_by_peto = True
        runner.kill_tree(job.process)
        try:
            job.process.wait(timeout=10)
        except Exception:  # noqa: BLE001 - tiến trình cứng đầu thì vẫn báo đã yêu cầu dừng
            pass
        return {"ok": True, "id": job.id, "command": job.command, "running": job.running(),
                "exit_code": job.process.returncode}

    def stop_all(self) -> list[str]:
        """Dừng mọi lệnh nền còn chạy khi đóng phiên; trả danh sách lệnh đã dừng."""
        stopped = []
        for job in self.running():
            job.stopped_by_peto = True
            runner.kill_tree(job.process)
            stopped.append(job.command)
        for job in self.jobs.values():
            try:
                job.process.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
            # Hết phiên thì không ai đọc output lệnh nền nữa, trừ khi Peto đã được báo output_id.
            if job.spool is not None and not job.spool_kept:
                job.spool.discard()
        return stopped

"""Kiểm thử giới hạn tải — cooldown, đồng thời, hàng chờ."""

from __future__ import annotations

import asyncio

import pytest

from rate_limit import Admission, AdmissionDenied


async def test_cooldown_blocks_second_request():
    gate = Admission(max_concurrent=2, max_queue=2, queue_timeout=1, cooldown=10)
    async with gate.slot("ai"):
        pass

    with pytest.raises(AdmissionDenied) as excinfo:
        async with gate.slot("ai"):
            pass
    assert excinfo.value.reason == "cooldown"
    assert excinfo.value.retry_after > 0


async def test_cooldown_is_per_user():
    gate = Admission(max_concurrent=2, max_queue=2, queue_timeout=1, cooldown=10)
    async with gate.slot("nguoi_a"):
        pass
    async with gate.slot("nguoi_b"):  # không được ảnh hưởng bởi người khác
        pass


async def test_queue_full_is_rejected():
    gate = Admission(max_concurrent=1, max_queue=0, queue_timeout=1, cooldown=0)
    started = asyncio.Event()
    release = asyncio.Event()

    async def hold():
        async with gate.slot("nguoi_a"):
            started.set()
            await release.wait()

    task = asyncio.create_task(hold())
    await started.wait()

    with pytest.raises(AdmissionDenied) as excinfo:
        async with gate.slot("nguoi_b"):
            pass
    assert excinfo.value.reason == "queue_full"

    release.set()
    await task


async def test_queue_timeout_gives_up():
    gate = Admission(max_concurrent=1, max_queue=5, queue_timeout=0.05, cooldown=0)
    started = asyncio.Event()
    release = asyncio.Event()

    async def hold():
        async with gate.slot("nguoi_a"):
            started.set()
            await release.wait()

    task = asyncio.create_task(hold())
    await started.wait()

    with pytest.raises(AdmissionDenied) as excinfo:
        async with gate.slot("nguoi_b"):
            pass
    assert excinfo.value.reason == "queue_timeout"

    release.set()
    await task


async def test_slot_is_released_after_error():
    gate = Admission(max_concurrent=1, max_queue=1, queue_timeout=0.5, cooldown=0)
    with pytest.raises(RuntimeError):
        async with gate.slot("ai"):
            raise RuntimeError("hỏng giữa chừng")

    # Nếu semaphore không được trả lại, lệnh dưới đây sẽ timeout.
    async with gate.slot("ai"):
        pass

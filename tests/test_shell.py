"""Subprocess lifetime and output limits apply to the whole shell command."""

import asyncio

import pytest

from agents_clm import LocalShell


async def test_timeout_kills_descendants(tmp_path):
    shell = LocalShell(tmp_path, timeout=0.1, allow_unsandboxed=True)
    output, code = await shell.execute("(sleep 0.4; printf survived > marker) & wait")
    assert code is None and "timed out" in output
    await asyncio.sleep(0.5)
    assert not (tmp_path / "marker").exists()


async def test_cancellation_kills_descendants(tmp_path):
    shell = LocalShell(tmp_path, allow_unsandboxed=True)
    task = asyncio.create_task(shell.execute("(touch started; sleep 0.4; printf survived > marker) & wait"))
    async def wait_started():
        while not (tmp_path / "started").exists():
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(wait_started(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.5)
        assert not (tmp_path / "marker").exists()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_large_output_keeps_bounded_head_and_tail(tmp_path):
    shell = LocalShell(tmp_path, max_output_chars=100, allow_unsandboxed=True)
    output, code = await shell.execute("python3 -c \"print('start' + 'x'*2000000 + 'end')\"")
    assert code == 0
    assert output.startswith("start") and output.endswith("end")
    assert "chars elided" in output and len(output) < 160


async def test_quoted_workspace_path_is_valid(tmp_path):
    workdir = tmp_path / 'quoted"workspace'
    workdir.mkdir()
    assert await LocalShell(workdir, allow_unsandboxed=True).run("echo ok") == "ok\n(exit_code=0)"

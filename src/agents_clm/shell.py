"""The general-purpose tool a CLM edits its context with.

Commands are written by the model, so they run with a scrubbed environment (no API keys)
and, on macOS, inside a sandbox: no network, writes only inside the workspace, and no
reads from the user's home directory.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import json
import math
import os
import platform
import signal
from pathlib import Path

from agents import FunctionTool, function_tool


def _macos_profile(workdir: Path) -> str:
    home = json.dumps(os.path.realpath(Path.home()), ensure_ascii=False)
    workspace = json.dumps(str(workdir), ensure_ascii=False)
    return f"""(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath {workspace}) (subpath "/dev"))
(allow file-write* (regex #"^/private/var/folders/[^/]+/[^/]+/T/xcrun_db"))
(deny file-read* (subpath {home}))
(allow file-read* (subpath {workspace}))
"""


class LocalShell:
    """Runs the agent's commands on this machine. Use ``ContextFile`` for SDK sandboxes."""

    def __init__(
        self,
        workdir: Path,
        *,
        timeout: float = 60,
        max_output_chars: int = 50_000,
        allow_unsandboxed: bool = False,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if type(max_output_chars) is not int or max_output_chars <= 0:
            raise ValueError("max_output_chars must be a positive integer")
        self.workdir = Path(os.path.realpath(workdir))
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self._sandbox: list[str] = []
        if platform.system() == "Darwin":
            self._sandbox = ["/usr/bin/sandbox-exec", "-p", _macos_profile(self.workdir)]
        elif not allow_unsandboxed:
            raise RuntimeError(
                "No sandbox is available on this platform. Run inside a container and pass "
                "allow_unsandboxed=True to accept running model-written commands."
            )

    async def run(self, command: str) -> str:
        output, code = await self.execute(command)
        return f"{output}\n(exit_code={code})".strip() if code is not None else output

    async def execute(self, command: str) -> tuple[str, int | None]:
        """Run a command and return its output and exit code (None if it timed out)."""
        temp = self.workdir / ".tmp"
        temp.mkdir(parents=True, exist_ok=True)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.workdir), "TMPDIR": str(temp), "LANG": "C.UTF-8"}
        process = await asyncio.create_subprocess_exec(
            *self._sandbox,
            "/bin/bash",
            "-c",
            command,
            cwd=self.workdir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        assert process.stdout is not None
        output_task = asyncio.create_task(self._read_output(process.stdout))
        try:
            output, _ = await asyncio.wait_for(
                asyncio.gather(output_task, process.wait()), self.timeout
            )
        except asyncio.TimeoutError:
            return f"Command timed out after {self.timeout:g}s.", None
        finally:
            # Killing only bash leaves background descendants alive, including on task
            # cancellation. They can keep editing the context and holding stdout open.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            if not output_task.done():
                output_task.cancel()
            await asyncio.gather(output_task, return_exceptions=True)
        return output, process.returncode

    async def _read_output(self, stream: asyncio.StreamReader) -> str:
        """Drain stdout while retaining only a bounded head and tail."""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        head_size = (self.max_output_chars + 1) // 2
        tail_size = self.max_output_chars // 2
        head = tail = ""
        total = 0
        while True:
            chunk = await stream.read(65_536)
            text = decoder.decode(chunk, final=not chunk)
            total += len(text)
            head += text[:max(0, head_size - len(head))]
            if tail_size:
                tail = (tail + text)[-tail_size:]
            if not chunk:
                break
        if total <= self.max_output_chars:
            remaining = total - len(head)
            return (head + (tail[-remaining:] if remaining else "")).rstrip()
        return f"{head}\n---- {total - len(head) - len(tail)} chars elided ----\n{tail}".rstrip()

    def tool(self) -> FunctionTool:
        shell = self

        async def bash(command: str) -> str:
            """Run a bash command in your workspace. python3, grep, and sed are available.

            Args:
                command: The command to run.
            """
            return await shell.run(command)

        return function_tool(bash)

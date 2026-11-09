"""The general-purpose tool a CLM edits its context with.

Commands are written by the model, so they run with a scrubbed environment (no API keys)
and, on macOS, inside a sandbox: no network, writes only inside the workspace, and no
reads from the user's home directory.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import platform
from pathlib import Path

from agents import FunctionTool, function_tool


def _macos_profile(workdir: Path) -> str:
    home = os.path.realpath(Path.home())
    return f"""(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "{workdir}") (subpath "/dev"))
(allow file-write* (regex #"^/private/var/folders/[^/]+/[^/]+/T/xcrun_db"))
(deny file-read* (subpath "{home}"))
(allow file-read* (subpath "{workdir}"))
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
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), self.timeout)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            return f"Command timed out after {self.timeout:g}s.", None
        return self._clip(stdout.decode(errors="replace").rstrip()), process.returncode

    def _clip(self, output: str) -> str:
        if len(output) <= self.max_output_chars:
            return output
        half = self.max_output_chars // 2
        return f"{output[:half]}\n---- {len(output) - 2 * half} chars elided ----\n{output[-half:]}"

    def tool(self) -> FunctionTool:
        shell = self

        async def bash(command: str) -> str:
            """Run a bash command in your workspace. python3, grep, and sed are available.

            Args:
                command: The command to run.
            """
            return await shell.run(command)

        return function_tool(bash)

"""Builds and runs the ``claude`` CLI subprocess (spec §5, §9).

The prompt is delivered on stdin to avoid argument-length and shell-escaping
problems; everything else is passed as flags.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .errors import WrapperError

# 2 MiB line buffer: the stream-json ``init`` event can be large.
_STREAM_LIMIT = 2 * 1024 * 1024


@dataclass
class PromptOptions:
    prompt: str
    working_dir: str
    model: str | None = None
    permission_mode: str | None = None
    allowed_tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    system_prompt_append: str | None = None
    session_id: str | None = None      # resume an existing session
    new_session_id: str | None = None  # mint a specific id for a new session
    max_budget_usd: float | None = None


@dataclass
class PromptResult:
    text: str
    session_id: str | None
    is_error: bool
    cost_usd: float | None = None
    duration_ms: int | None = None


def build_command(cfg: Config, opts: PromptOptions, *, stream: bool = False) -> list[str]:
    """Construct the argv for the claude CLI. Caller pipes ``opts.prompt`` to stdin.

    ``stream=True`` selects the NDJSON event stream (spec §5.2) instead of the
    single JSON result object (§5.1).
    """
    if stream:
        cmd: list[str] = [
            cfg.cli, "-p",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",  # required by the CLI for stream-json in -p mode
        ]
    else:
        cmd = [cfg.cli, "-p", "--output-format", "json"]

    model = opts.model or cfg.model
    if model:
        cmd += ["--model", model]

    mode = opts.permission_mode or cfg.permission_mode
    if mode == "bypassPermissions":
        # Server-level gate is checked before we get here (spec §7.4).
        cmd += ["--dangerously-skip-permissions"]
    elif mode and mode != "default":
        cmd += ["--permission-mode", mode]

    if opts.allowed_tools:
        cmd += ["--allowedTools", *opts.allowed_tools]
    if opts.disallowed_tools:
        cmd += ["--disallowedTools", *opts.disallowed_tools]
    if opts.system_prompt_append:
        cmd += ["--append-system-prompt", opts.system_prompt_append]
    if opts.max_budget_usd is not None:
        cmd += ["--max-budget-usd", str(opts.max_budget_usd)]

    # Sessions: resume takes precedence; otherwise pin a freshly-minted id.
    if opts.session_id:
        cmd += ["--resume", opts.session_id]
    elif opts.new_session_id:
        cmd += ["--session-id", opts.new_session_id]

    return cmd


async def run_prompt(cfg: Config, opts: PromptOptions) -> PromptResult:
    """Run claude headless in ``opts.working_dir`` and parse its JSON result."""
    cmd = build_command(cfg, opts)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=opts.working_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise WrapperError("cli_not_found", f"Claude CLI not found: {cfg.cli}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=opts.prompt.encode("utf-8")),
            timeout=cfg.timeout,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise WrapperError("timeout", f"Claude exceeded {cfg.timeout}s timeout.") from exc

    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0 and not out:
        raise WrapperError(
            "cli_failed",
            f"Claude exited with code {proc.returncode}: {err or '(no stderr)'}",
        )

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        # Fall back to raw stdout (spec §8).
        return PromptResult(text=out, session_id=None, is_error=True)

    return PromptResult(
        text=data.get("result", ""),
        session_id=data.get("session_id"),
        is_error=bool(data.get("is_error", False)),
        cost_usd=data.get("total_cost_usd"),
        duration_ms=data.get("duration_ms"),
    )


async def run_prompt_stream(
    cfg: Config,
    opts: PromptOptions,
    on_delta: Callable[[str], Awaitable[None]],
) -> PromptResult:
    """Run claude in streaming mode, invoking ``on_delta`` for each text chunk.

    Parses the NDJSON event stream (spec §5.2): forwards ``content_block_delta``
    text deltas as they arrive and returns the same summary fields as
    :func:`run_prompt` from the terminal ``result`` event.
    """
    cmd = build_command(cfg, opts, stream=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=opts.working_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=_STREAM_LIMIT,
        )
    except FileNotFoundError as exc:
        raise WrapperError("cli_not_found", f"Claude CLI not found: {cfg.cli}") from exc

    # Drain stderr concurrently so a full pipe can never deadlock the child.
    stderr_task = asyncio.ensure_future(proc.stderr.read())

    async def _consume() -> tuple[PromptResult, bool, str]:
        if proc.stdin is not None:
            proc.stdin.write(opts.prompt.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

        session_id: str | None = None
        acc: list[str] = []
        text = ""
        is_error = False
        cost: float | None = None
        duration: int | None = None
        got_result = False

        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = evt.get("type")
            if etype == "system" and evt.get("subtype") == "init":
                session_id = evt.get("session_id") or session_id
            elif etype == "stream_event":
                inner = evt.get("event") or {}
                if inner.get("type") == "content_block_delta":
                    delta = inner.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        chunk = delta.get("text") or ""
                        if chunk:
                            acc.append(chunk)
                            await on_delta(chunk)
            elif etype == "result":
                got_result = True
                text = evt.get("result", "")
                is_error = bool(evt.get("is_error", False))
                cost = evt.get("total_cost_usd")
                duration = evt.get("duration_ms")
                session_id = evt.get("session_id") or session_id

        if not got_result:
            # Stream ended without a result event: fall back to accumulated text.
            text = "".join(acc)
            is_error = True
        return PromptResult(text, session_id, is_error, cost, duration), got_result, ""

    try:
        result, got_result, _ = await asyncio.wait_for(_consume(), timeout=cfg.timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        stderr_task.cancel()
        raise WrapperError("timeout", f"Claude exceeded {cfg.timeout}s timeout.") from exc

    err = (await stderr_task).decode("utf-8", errors="replace").strip()
    await proc.wait()

    if proc.returncode not in (0, None) and not got_result:
        raise WrapperError(
            "cli_failed",
            f"Claude exited with code {proc.returncode}: {err or '(no stderr)'}",
        )

    return result


async def _probe_version(executable: str) -> str | None:
    """Return ``<executable> --version`` trimmed output, or None if unavailable."""
    try:
        proc = await asyncio.create_subprocess_exec(
            executable, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        return None
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    return stdout.decode("utf-8", errors="replace").strip()


async def cli_version(cfg: Config) -> str | None:
    """Return the Claude CLI version string, or None if the CLI is unavailable."""
    return await _probe_version(cfg.cli)


async def node_version() -> str | None:
    """Return the Node.js version string, or None if Node is unavailable."""
    return await _probe_version("node")


def check_authenticated() -> bool:
    """Cheap, credit-free auth probe (spec §5.4, §7.1).

    True if an API key is present in the environment, or a logged-in Claude
    Code credential store exists. Honors CLAUDE_CONFIG_DIR when set.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config_dir) if config_dir else Path.home() / ".claude"
    return (base / ".credentials.json").is_file()

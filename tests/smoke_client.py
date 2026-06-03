"""Smoke test: connect to a running claude-wrapper over Streamable HTTP,
list tools, call claude_health, and exercise claude_prompt error paths.

Usage:
    python tests/smoke_client.py [base_url] [--stream <abs_working_dir>]

The error-path checks are credit-free. Passing ``--stream <dir>`` adds a real
``claude_prompt_stream`` call (spends a small amount of quota) that prints each
streamed delta as it arrives.

Default base_url: http://127.0.0.1:8787/mcp
"""

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main(url: str, stream_dir: str | None) -> None:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            health = await session.call_tool("claude_health", {})
            print("HEALTH:", health.structuredContent or health.content)

            # Danger gate: bypassPermissions should be rejected (server not --dangerous).
            denied = await session.call_tool("claude_prompt", {
                "prompt": "hi",
                "working_dir": ".",
                "permission_mode": "bypassPermissions",
            })
            print("DANGER_GATE:", denied.structuredContent or denied.content)

            # Invalid working dir (relative) should be rejected.
            bad = await session.call_tool("claude_prompt", {
                "prompt": "hi",
                "working_dir": "not/absolute",
            })
            print("BAD_WD:", bad.structuredContent or bad.content)

            if stream_dir:
                deltas: list[str] = []

                async def on_progress(progress, total, message):
                    deltas.append(message or "")
                    print(f"  delta: {message!r}", flush=True)

                res = await session.call_tool(
                    "claude_prompt_stream",
                    {"prompt": "Reply with exactly: one two three",
                     "working_dir": stream_dir},
                    progress_callback=on_progress,
                )
                print(f"STREAM: {len(deltas)} deltas ->",
                      res.structuredContent or res.content)


if __name__ == "__main__":
    args = sys.argv[1:]
    stream_dir = None
    if "--stream" in args:
        i = args.index("--stream")
        stream_dir = args[i + 1]
        del args[i:i + 2]
    base = args[0] if args else "http://127.0.0.1:8787/mcp"
    asyncio.run(main(base, stream_dir))

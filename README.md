# Claude Wrapper

An MCP server that wraps the **Claude Code CLI** (`claude -p`) and exposes it as
a callable service over Streamable HTTP, so any application on the local machine
can send a prompt and receive Claude's text response.

See [`claude_wrapper_specification.md`](claude_wrapper_specification.md) for the
full design.

## Prerequisites

- Node.js + Claude Code CLI (`claude`) on `PATH`, authenticated
  (`ANTHROPIC_API_KEY` or a logged-in subscription).
- Python ≥ 3.11.

## Install & run

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e .

# Run (safe defaults: loopback, conservative permissions)
.venv\Scripts\python -m claude_wrapper

# With options
.venv\Scripts\python -m claude_wrapper --port 9000 --root C:\projects --token s3cret
```

The server listens on `http://127.0.0.1:8787/mcp` by default.

## Build a standalone binary (optional)

A one-file executable (no Python needed on the target, but still requires Node +
the Claude Code CLI on the host) is built with PyInstaller:

```bash
.venv\Scripts\python -m pip install -e ".[build]"
.venv\Scripts\python -m PyInstaller build\claude-wrapper.spec ^
    --distpath build\dist --workpath build\work --noconfirm
```

The result is `build\dist\claude-wrapper.exe` (Windows) / `build/dist/claude-wrapper`
(Linux). Run it exactly like the `python -m` form:

```bash
build\dist\claude-wrapper.exe --port 9000 --root C:\projects --token s3cret
```

## MCP tools

- `claude_health` — readiness probe; reports `cli_version`, `node_version`,
  `authenticated`, and `ready`.
- `claude_prompt` — run a prompt; `working_dir` is required and pins the
  session's sandbox. Optional `json_schema` (a JSON Schema object) forces
  structured output — the parsed object is returned in the `structured` field
  alongside the prose `text`.
- `claude_session_new` — start a fresh conversation and run its first turn,
  returning a `session_id` to pass to `claude_prompt` for follow-ups. Convenience
  over letting the first `claude_prompt` mint the id.
- `claude_chat` — send a message in **this connection's** ongoing conversation.
  The wrapper keeps one Claude session per connected MCP client and resumes it
  automatically, so the caller never handles a `session_id`. Two simultaneous
  clients get two isolated conversations — ideal for a relay/mailbox consumer.
- `claude_prompt_stream` — same inputs/result as `claude_prompt`, but text
  deltas are streamed to the client as **progress notifications** (delta in the
  `message` field, cumulative char count in `progress`) while Claude generates.

## Authentication (optional)

If a token is configured (`--token`, `CLAUDE_WRAPPER_TOKEN`, or the TOML
`token`), every request must present it as `Authorization: Bearer <token>`
(or an `X-Wrapper-Token` header); otherwise the server replies `401
unauthorized`. With no token set, the loopback bind is the only gate.

## Configuration

Precedence: **CLI flag > env var > TOML file > default**. See spec §4.2 and the
sample `wrapper.toml` in the spec.

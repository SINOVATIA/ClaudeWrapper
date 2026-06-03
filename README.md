# Claude Wrapper


## POUR LES DEBUTANTS : suivre ce guide pas à pas :
> 🟢 **Débutant ?** Suis le **[Guide de démarrage pas à pas](docs/GUIDE-DEMARRAGE.md)**
> (français) : installation complète + utilisation depuis opencode, expliqué de zéro.

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

Check the installed version any time:

```bash
.venv\Scripts\python -m claude_wrapper --version   # -> claude-wrapper 0.2.0
```

The version also appears in the startup banner and in the `claude_health` tool
(`wrapper_version`). See [`CHANGELOG.md`](CHANGELOG.md) for what changed.

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
  The wrapper keeps one Claude session per connected MCP client **and per
  `working_dir`**, resuming it automatically, so the caller never handles a
  `session_id`. Changing `working_dir` mid-dialogue switches to that directory's
  own conversation (fresh the first time, resumed on return). Two simultaneous
  clients get isolated conversations — ideal for a relay/mailbox consumer.
- `claude_prompt_stream` — same inputs/result as `claude_prompt`, but text
  deltas are streamed to the client as **progress notifications** (delta in the
  `message` field, cumulative char count in `progress`) while Claude generates.

## Use it from opencode (relay / mailbox)

The most common setup: let [opencode](https://opencode.ai) act as a thin relay so
you chat with Claude through the wrapper. Ready-to-copy files live in
[`examples/opencode/`](examples/opencode/):

1. Copy [`examples/opencode/opencode.json`](examples/opencode/opencode.json) to
   your opencode config (project root, or `~/.config/opencode/opencode.json`) —
   it registers the wrapper as a remote MCP server.
2. Copy [`examples/opencode/agent/claude-agent.md`](examples/opencode/agent/claude-agent.md)
   to `~/.config/opencode/agent/claude.md` (or `.opencode/agent/claude.md`) —
   **save it as `claude.md`** (the filename becomes the opencode agent name). It
   is a "mailbox" agent that forwards every message to `claude_chat` verbatim;
   edit the default working dir inside it.
3. In opencode, press **Tab** to select the `claude` agent and just talk. Use
   `cd <path>` to switch the working dir mid-chat (each dir keeps its own memory).

**Relay model** (the small model opencode uses to forward — the real engine is
still Claude Opus 4.8 in the wrapper). Tested, in order of reliability:

| Model | Cost | Note |
|---|---|---|
| **Nemotron 3 Super (Free)** | free | ⭐ best at following the "just relay" rule |
| **Mistral Small 4** | ~€0.01 / 25 relayed messages | very reliable, negligible cost |
| **DeepSeek V4 Flash (Free)** | free | works, occasionally chatty |

See the [step-by-step guide](docs/GUIDE-DEMARRAGE.md) for the full walkthrough.

## Authentication (optional)

If a token is configured (`--token`, `CLAUDE_WRAPPER_TOKEN`, or the TOML
`token`), every request must present it as `Authorization: Bearer <token>`
(or an `X-Wrapper-Token` header); otherwise the server replies `401
unauthorized`. With no token set, the loopback bind is the only gate.

## Configuration

Precedence: **CLI flag > env var > TOML file > default**. See spec §4.2 and the
sample `wrapper.toml` in the spec.

# Claude Wrapper — Specification

> An MCP server that wraps the **Claude Code CLI** (`claude -p`) and exposes it
> as a callable service, so any application on the local machine can send a
> prompt and receive Claude's text response.

- **Status:** Draft v0.1
- **Date:** 2026-06-02
- **Author:** ffert290771@gmail.com
- **Verified environment:** Claude Code `2.1.160`, Node `v22.18.0`, Python `3.13.9` (Windows 11)

---

## 1. Purpose & Scope

### 1.1 Goal
Make the Claude Code CLI usable **from inside other applications** without each
app having to shell out to `claude` itself, manage sessions, or parse CLI
output. The wrapper centralizes that logic behind a stable MCP interface.

### 1.2 Direction of the architecture
This is the **inverse** of normal MCP usage. Normally Claude Code is the MCP
*client* and MCP servers provide tools to it. Here, Claude Code is the
**engine**, and the wrapper exposes it to consumers:

```
┌──────────────┐   MCP over HTTP   ┌─────────────────┐  subprocess   ┌──────────────┐   HTTPS   ┌────────────┐
│ Consumer app │ ────────────────► │  Claude Wrapper │ ────────────► │  claude -p   │ ────────► │ Anthropic  │
│ (any client) │ ◄──────────────── │  (this server)  │ ◄──────────── │  (CLI, Node) │ ◄──────── │    API     │
└──────────────┘   text / JSON     └─────────────────┘    stdout     └──────────────┘           └────────────┘
```

### 1.3 In scope
- A long-running local MCP server (Windows + Linux).
- One-shot prompt execution via `claude -p`.
- Multi-turn conversations via Claude Code session IDs.
- Streaming responses (token-by-token) as an option.
- Per-call control of model, permissions, allowed tools, and working directory.

### 1.4 Out of scope (v1)
- Hosting Claude itself (the CLI + Node + auth remain external prerequisites).
- Authentication/authorization of consumer apps beyond a local bind + optional shared token.
- Remote/multi-machine deployment, TLS, load balancing.
- A GUI.

---

## 2. Prerequisites (host machine)

These are **unavoidable** regardless of the wrapper's implementation language —
the wrapper is a thin layer over the real Claude Code install:

| Requirement | Notes |
|---|---|
| Node.js | `v22.18.0` confirmed present. Required by Claude Code. |
| Claude Code CLI | `claude` `2.1.160` on `PATH`. |
| Authentication | `ANTHROPIC_API_KEY` env var **or** a logged-in Claude subscription (OAuth). See §7. |
| Python | `3.13.9` confirmed (only if Python implementation is chosen). |

**Cost note:** every wrapper call spawns a real Claude Code turn and consumes
API credits / subscription quota.

---

## 3. Technology Choice

### 3.1 Decision: Python
| Option | MCP SDK | Drives CLI | → binary | Verdict |
|---|---|---|---|---|
| **Python** ✅ | official `mcp` (`FastMCP`) | `subprocess` → `claude -p` | PyInstaller | **Chosen** — fastest, both sides first-class |
| TypeScript/Node | official `@modelcontextprotocol/sdk` | child_process | node SEA | Viable; closest to Claude Code's own runtime |
| Delphi | none (hand-roll JSON-RPC) | spawn process + pipes | native exe | Only if a Delphi consumer dominates |

**Rationale:** the wrapper drives the CLI as a subprocess (not the Agent SDK),
so language matters mainly for the MCP layer — where Python's official
`FastMCP` is the least-effort, cross-platform path.

### 3.2 Packaging
- Development: run as `python -m claude_wrapper`.
- Distribution: **PyInstaller** one-file build per OS (`claude-wrapper.exe` on
  Windows, ELF binary on Linux). The binary still requires Node + Claude Code on
  the host (§2).

---

## 4. Transport & Interface

### 4.1 Transport: Streamable HTTP
A single long-running server that **multiple** apps connect to → **Streamable
HTTP**, bound to loopback by default:

```
http://127.0.0.1:8787/mcp
```

(stdio transport is explicitly **not** used — it only fits the case where the
client launches the server as its own child process.)

### 4.2 Configuration

Everything is configurable. **Precedence (highest wins):**
`CLI startup flag` → `environment variable` → `config file` → `built-in default`.

| Setting | CLI flag | Env var | Default |
|---|---|---|---|
| Bind host | `--host` | `CLAUDE_WRAPPER_HOST` | `127.0.0.1` |
| Bind port | `--port` | `CLAUDE_WRAPPER_PORT` | `8787` |
| Shared auth token (optional) | `--token` | `CLAUDE_WRAPPER_TOKEN` | _(none)_ |
| `claude` executable path | `--cli` | `CLAUDE_WRAPPER_CLI` | `claude` (from `PATH`) |
| Default model | `--model` | `CLAUDE_WRAPPER_MODEL` | _(CLI default)_ |
| Default permission mode | `--permission-mode` | `CLAUDE_WRAPPER_PERMISSION_MODE` | `default` |
| Optional confinement root | `--root` | `CLAUDE_WRAPPER_ROOT` | _(none — any path allowed)_ |
| Per-call timeout (s) | `--timeout` | `CLAUDE_WRAPPER_TIMEOUT` | `300` |
| Max concurrent CLI processes | `--max-concurrency` | `CLAUDE_WRAPPER_MAX_CONCURRENCY` | `4` |
| Config file path | `--config` | `CLAUDE_WRAPPER_CONFIG` | _(none)_ |
| **Enable danger zone** | `--dangerous` | `CLAUDE_WRAPPER_DANGEROUS` | `false` (off) |

> **Working directory is not a server setting — it is supplied per call** (see
> §5.1 `working_dir`). The optional `--root` only constrains *where* those
> per-call paths may live (defense in depth); by default any valid path is
> accepted and becomes that session's sandbox.

The **config file is TOML** and may set any of the above so the server can be
launched with a single `--config path` argument. CLI flags still override
individual values from the file.

### 4.3 Startup examples

```bash
# Safe default: loopback, conservative permissions, no danger zone.
# working_dir comes from each call.
claude-wrapper

# Custom port + token; restrict all call paths to live under one root
claude-wrapper --port 9000 --token s3cret --root C:\projects

# Load everything from a config file
claude-wrapper --config C:\config\wrapper.toml

# DANGER ZONE explicitly enabled at startup (see §7.4)
claude-wrapper --dangerous --root C:\sandbox --token s3cret
```

**Example `wrapper.toml`:**
```toml
host            = "127.0.0.1"
port            = 8787
token           = "s3cret"
model           = "opus"
permission_mode = "default"
root            = "C:\\projects"   # optional confinement (§7.3)
timeout         = 300
max_concurrency = 4
dangerous       = false
```

### 4.4 The `--dangerous` startup flag (danger zone)

`--dangerous` is a **server-level gate**, not a per-call setting. It does *not*
change default behavior — it only **unlocks** the ability for a call to request
`permission_mode = bypassPermissions` (which maps the CLI's
`--dangerously-skip-permissions`). Without `--dangerous` at startup, any call
requesting `bypassPermissions` is **rejected**.

| Server started with | Call requests `bypassPermissions` | Result |
|---|---|---|
| _(default)_ | yes | **Rejected** with `danger_zone_disabled` error |
| `--dangerous` | yes | Allowed — Claude runs with all permission checks skipped |
| `--dangerous` | no | Normal — uses the call's `permission_mode` |

This two-layer design means an operator must make a deliberate choice at launch
*and* a consumer must opt in per call. See §7.4 for the safety rationale.

---

## 5. MCP Tools

### 5.1 `claude_prompt` — one-shot or resumable prompt
Run a single prompt and return the full text result.

**Input**
| Field | Type | Required | Description |
|---|---|---|---|
| `prompt` | string | yes | The user prompt. |
| `working_dir` | string | **yes** | Absolute path Claude operates in. Becomes the **session sandbox** (subprocess cwd); the session is pinned to it for its whole lifetime (§6.3, §7.3). |
| `model` | string | no | `sonnet`, `opus`, or full id (e.g. `claude-opus-4-8`). |
| `permission_mode` | enum | no | `default` \| `acceptEdits` \| `auto` \| `bypassPermissions` \| `dontAsk` \| `plan`. |
| `allowed_tools` | string[] | no | Maps to `--allowedTools` (e.g. `["Read","Bash(git *)"]`). |
| `disallowed_tools` | string[] | no | Maps to `--disallowedTools`. |
| `system_prompt_append` | string | no | Maps to `--append-system-prompt`. |
| `session_id` | string (uuid) | no | Resume an existing conversation (`--resume`). |
| `max_budget_usd` | number | no | Maps to `--max-budget-usd`. |
| `add_dirs` | string[] | no | Extra accessible dirs (`--add-dir`). |

**Output**
| Field | Type | Description |
|---|---|---|
| `text` | string | Final assistant text (`result` field of JSON output). |
| `session_id` | string | Session id for follow-up calls. |
| `is_error` | bool | Whether the CLI reported an error result. |
| `cost_usd` | number? | Reported cost if available. |
| `duration_ms` | number? | Wall-clock duration if available. |

**CLI mapping (canonical form)**
```bash
claude -p "<prompt>" \
  --output-format json \
  [--model <model>] \
  [--permission-mode <mode>] \
  [--allowedTools <...>] [--disallowedTools <...>] \
  [--append-system-prompt <text>] \
  [--resume <session_id>] \
  [--add-dir <...>] \
  [--max-budget-usd <amount>]
# subprocess cwd = working_dir
```

### 5.2 `claude_prompt_stream` — streaming variant
Same inputs as `claude_prompt`; streams incremental output to the MCP client as
it arrives.

**CLI mapping**
```bash
claude -p "<prompt>" --output-format stream-json --include-partial-messages [...]
```
The wrapper parses the NDJSON event stream and forwards text deltas. The final
event yields the same summary fields as §5.1.

### 5.3 `claude_session_new` — start a fresh session (optional)
Allocate a UUID and run the first turn with `--session-id <uuid>`, returning the
id for subsequent `claude_prompt` calls. (Convenience over letting the first
`claude_prompt` mint the id.)

### 5.4 `claude_health` — readiness probe
Returns `{ cli_version, node_version, authenticated: bool, ready: bool }`.
Implemented by invoking `claude --version` and a cheap auth check.

---

## 6. Session & Concurrency Model

### 6.1 One instance serves many apps — multiple instances are NOT required
A single wrapper process handles many simultaneous consumers:

```
                         ┌── claude -p  (app A, session 1)
 App A ─┐                │
 App B ─┼─► Wrapper ─────┼── claude -p  (app B, session 2)   ← run in parallel,
 App C ─┘   (1 process,  │                                     each its own OS process
            async HTTP)  └── claude -p  (app C, session 3)
                         (bounded by MAX_CONCURRENCY semaphore)
```

- The HTTP/MCP layer is **async**: one process accepts many concurrent
  connections on one port.
- Each call spawns an **independent `claude` subprocess**, so calls execute in
  true parallel — not serialized behind one another.
- A **semaphore** caps live subprocesses at `MAX_CONCURRENCY`. Calls beyond the
  cap wait in a queue (up to the per-call timeout), then run. This protects RAM,
  CPU, and API rate limits.

### 6.2 When you *would* run multiple instances
Only for **isolation**, never for throughput:
- Different `ANTHROPIC_API_KEY` / billing accounts per instance.
- Different default model or permission posture per consumer group.
- Separate ports/tokens for tenant separation.

### 6.3 Sessions
- **Sessions** map 1:1 to Claude Code session IDs. The wrapper is stateless
  about conversation content — Claude Code persists it on disk (unless
  `--no-session-persistence`). The wrapper only relays `session_id`.
- **Per-session serialization:** concurrent calls that resume the **same**
  `session_id` are serialized by an internal per-session lock — resuming one
  conversation from two callers at once would corrupt its history. Distinct
  sessions never block each other.
- **Path pinning:** the `working_dir` of a session's first call is recorded and
  becomes immutable. A `claude_prompt` that resumes a `session_id` with a
  *different* `working_dir` is rejected with `working_dir_mismatch`. This
  guarantees a conversation never escapes the path it was started in.
- **Resume semantics:** passing `session_id` → `--resume`; omitting it starts a
  new session. `--fork-session` is a future option for branching.

### 6.4 Timeouts
A per-call timeout kills the subprocess tree and returns a structured error;
the freed concurrency slot is handed to the next queued call.

---

## 7. Authentication & Safety

### 7.1 Claude Code auth (server → Anthropic)
- Preferred for headless/service use: `ANTHROPIC_API_KEY` in the server's env.
- Subscription/OAuth login also works but is interactive to set up.
- `--bare` mode forces API-key-only auth and skips hooks, plugins, and
  CLAUDE.md discovery — a candidate "clean/predictable" execution mode.

### 7.2 Consumer → wrapper auth
- Default bind is loopback (`127.0.0.1`) only.
- Optional `CLAUDE_WRAPPER_TOKEN`: if set, consumers must present it; requests
  without it are rejected.

### 7.3 Working-dir confinement (per-call sandbox)
The `working_dir` supplied on each call **is** the sandbox boundary for that
session. The wrapper enforces:
- **Pinned for the session's lifetime** — set as the subprocess cwd; a resume
  with a different path is rejected (`working_dir_mismatch`, §6.3).
- **Validated on entry** — must be an existing absolute directory; path
  traversal / symlink escape is normalized and rejected.
- **No widening** — the wrapper never adds `--add-dir` beyond `working_dir`, so
  the call cannot grant Claude access to sibling paths.
- **Optional `--root`** — if the operator set a confinement root at startup, the
  call's `working_dir` must resolve to a path *inside* `--root`, else rejected
  (`working_dir_forbidden`).

> **Confinement strength:** the wrapper guarantees *cwd pinning and no
> wrapper-side widening*. The Claude CLI itself, in non-interactive mode, does
> not provide OS-level jailing — for hard isolation (untrusted prompts), run the
> wrapper inside a container or OS sandbox whose filesystem is limited to the
> working dir. Default `permission_mode = default` keeps file/command execution
> from happening silently.

### 7.4 Danger zone — two-layer gate
Skipping all permission checks (`bypassPermissions` → CLI
`--dangerously-skip-permissions`) lets Claude run arbitrary shell commands and
edit files unattended. It is guarded by **two independent gates** that must both
be satisfied:

1. **Operator gate (startup):** the server must be launched with `--dangerous`
   (or `CLAUDE_WRAPPER_DANGEROUS=true`). Otherwise the capability is absent.
2. **Consumer gate (per call):** the call must explicitly set
   `permission_mode = bypassPermissions`.

Recommended hardening when danger zone is enabled:
- Pair it with a strict working-dir whitelist (`--allow-dir <sandbox>`).
- Require the shared `--token`.
- Keep the bind on loopback (never expose `--dangerous` on a public interface).
- Log every bypass-mode call (consumer, working dir, prompt hash) for audit.

> Rationale for the split: an operator's launch choice and a consumer's request
> are different trust boundaries. Requiring both prevents either a careless
> consumer *or* a default-launched server from silently gaining shell access.

---

## 8. Error Handling

| Condition | Behavior |
|---|---|
| `claude` not found on PATH | Fail fast at startup; `claude_health.ready=false`. |
| Not authenticated | Surface in `claude_health`; `claude_prompt` returns `is_error=true` with message. |
| Subprocess non-zero exit | Capture stderr, return structured error (no raw stack to consumer). |
| Timeout exceeded | Kill process tree, return `timeout` error. |
| Malformed JSON from CLI | Fall back to raw stdout in `text`, set `is_error=true`. |
| Concurrency limit | Queue; if queue wait exceeds timeout, return `busy` error. |
| `bypassPermissions` requested, server not `--dangerous` | Reject with `danger_zone_disabled` error. |
| `working_dir` missing / not an existing absolute dir | Reject with `invalid_working_dir` error. |
| `working_dir` outside `--root` (when set) | Reject with `working_dir_forbidden` error. |
| Resume with `working_dir` ≠ session's pinned path | Reject with `working_dir_mismatch` error. |
| Missing/invalid `--token` (when token set) | Reject with `unauthorized` error. |

---

## 9. Reference CLI Flags (verified, v2.1.160)

Relevant `claude -p` options confirmed present in this install:

- Output/IO: `--output-format text|json|stream-json`, `--input-format text|stream-json`,
  `--include-partial-messages`, `--replay-user-messages`, `--json-schema <schema>`
- Sessions: `--session-id <uuid>`, `-r/--resume`, `-c/--continue`, `--fork-session`,
  `--no-session-persistence`
- Model: `--model`, `--fallback-model`
- Permissions/tools: `--permission-mode`, `--allowedTools`, `--disallowedTools`,
  `--tools`, `--dangerously-skip-permissions`, `--allow-dangerously-skip-permissions`
- Context: `--add-dir`, `--system-prompt`, `--append-system-prompt`,
  `--mcp-config`, `--strict-mcp-config`, `--settings`, `--setting-sources`
- Budget/exec: `--max-budget-usd`, `--bare`, `--agent`, `--agents`

---

## 10. Project Layout (proposed)

```
Wrapper-Claude/
├─ claude_wrapper_specification.md   ← this file
├─ pyproject.toml                    ← deps: mcp, pydantic
├─ src/claude_wrapper/
│  ├─ __main__.py                    ← entrypoint, transport bootstrap
│  ├─ server.py                      ← FastMCP server + tool registration
│  ├─ cli.py                         ← claude subprocess builder/runner
│  ├─ sessions.py                    ← session id relay + concurrency pool
│  └─ config.py                      ← env-driven settings
├─ tests/
└─ build/                            ← PyInstaller spec + artifacts
```

---

## 11. Open Questions / Decisions Pending

**Resolved**
- ~~Concurrency~~ → single instance + per-call subprocess + semaphore (§6.1).
  Multiple instances only for isolation (§6.2).
- ~~Danger zone~~ → two-layer gate: `--dangerous` at startup + per-call opt-in (§7.4).
- ~~Configurability~~ → CLI flags > env > config file > defaults (§4.2).
- ~~Working-dir policy~~ → required per call, pinned for the session's lifetime,
  optional `--root` confinement (§6.3, §7.3).
- ~~Config file format~~ → **TOML**.
- ~~Streaming protocol detail~~ → **progress notifications**: each text delta is
  sent via the MCP progress channel (`progress` = cumulative char count,
  `message` = the delta). The CLI's `content_block_delta` `text_delta` events
  (`--output-format stream-json --include-partial-messages`) drive it; the
  terminal `result` event yields the §5.1 summary. Clients opt in by passing a
  progress token; the full aggregated text is always in the return value (§5.2).
- ~~Structured output~~ → **exposed** as an optional `json_schema` parameter on
  `claude_prompt` / `claude_prompt_stream`. It maps to the CLI `--json-schema`
  (inline JSON); the parsed `structured_output` is returned in a `structured`
  field, leaving the prose `text` intact.
- ~~Packaging target~~ → **both**: a PyInstaller one-file binary
  (`build/claude-wrapper.spec`) *and* documented `pip install -e .` +
  `python -m claude_wrapper` for development (§3.2, README).

**Still open**
- _(none — all decisions resolved)_

---

## 12. Milestones

1. **M1 — Walking skeleton:** FastMCP server over HTTP with `claude_health` +
   one-shot `claude_prompt` (json output). Manual test from an MCP client.
2. **M2 — Sessions:** resumable conversations via `session_id`.
3. **M3 — Streaming:** `claude_prompt_stream` with partial messages.
4. **M4 — Safety & config:** permission posture, working-dir policy, token auth,
   concurrency limits.
5. **M5 — Packaging:** PyInstaller binaries + run/install docs.

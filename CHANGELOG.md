# Changelog

All notable changes to **claude-wrapper** are documented here. The version is
shown by `claude-wrapper --version`, in the startup banner, and in the
`claude_health` tool (`wrapper_version`). This project aims to follow
[Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`.

## [0.2.0] — 2026-06-03

### Added
- **`claude_chat`** — connection-bound conversations: the wrapper keeps one
  Claude session **per connected MCP client and per `working_dir`**, resuming it
  automatically, so a relay/mailbox consumer never handles a `session_id`.
  Switching `working_dir` mid-dialogue switches to that directory's own
  conversation (per-directory memory). Two simultaneous clients stay isolated.
- **`claude_session_new`** — explicitly start a fresh conversation and return its
  `session_id`.
- **Structured output** — optional `json_schema` parameter on `claude_prompt` /
  `claude_prompt_stream`; the typed object is returned in a `structured` field.
- **Beginner documentation** — `docs/GUIDE-DEMARRAGE.md` (step-by-step, French)
  and copy-paste `examples/opencode/` (MCP config + relay agent), with a tested
  list of relay models.
- **`--version` flag** and a single source-of-truth version (dynamic, read from
  `src/claude_wrapper/__init__.py`); version now also appears in the banner.

## [0.1.0] — 2026-06-02

### Added
- Initial MCP server over Streamable HTTP wrapping the Claude Code CLI.
- Tools: `claude_health`, `claude_prompt` (one-shot/resumable, JSON output),
  `claude_prompt_stream` (text deltas via progress notifications).
- Multi-turn **sessions** with working-dir path pinning and per-session
  serialization; global concurrency cap.
- **Safety & config**: working-dir confinement (`--root`), two-layer danger-zone
  gate (`--dangerous` + per-call `bypassPermissions`), shared-token auth,
  precedence CLI > env > TOML > default.
- **Packaging**: PyInstaller one-file build (`build/claude-wrapper.spec`).
- `pytest` test suite.

[0.2.0]: #020--2026-06-03
[0.1.0]: #010--2026-06-02

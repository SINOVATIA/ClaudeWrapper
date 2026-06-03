"""CLI argv construction, auth probe, and subprocess result parsing.

``run_prompt`` / ``run_prompt_stream`` are exercised against fake subprocesses
(no real ``claude``, no credits) by monkeypatching ``create_subprocess_exec``.
"""

import asyncio

import pytest

import claude_wrapper.cli as cli_mod
from claude_wrapper.cli import (
    PromptOptions,
    build_command,
    check_authenticated,
    run_prompt,
    run_prompt_stream,
)
from claude_wrapper.config import Config
from claude_wrapper.errors import WrapperError


def _opts(**kw):
    base = dict(prompt="hi", working_dir="/wd")
    base.update(kw)
    return PromptOptions(**base)


# --- build_command ---------------------------------------------------------

def test_json_form_minimal():
    assert build_command(Config(), _opts())[:4] == ["claude", "-p", "--output-format", "json"]


def test_stream_form_flags():
    cmd = build_command(Config(), _opts(), stream=True)
    assert "stream-json" in cmd
    assert "--include-partial-messages" in cmd
    assert "--verbose" in cmd


def test_model_and_mode_mapping():
    cmd = build_command(Config(), _opts(model="opus", permission_mode="plan"))
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert cmd[cmd.index("--permission-mode") + 1] == "plan"


def test_default_mode_emits_no_flag():
    assert "--permission-mode" not in build_command(Config(), _opts(permission_mode="default"))


def test_bypass_maps_to_skip_flag():
    cmd = build_command(Config(), _opts(permission_mode="bypassPermissions"))
    assert "--dangerously-skip-permissions" in cmd
    assert "--permission-mode" not in cmd


def test_resume_vs_new_session():
    resume = build_command(Config(), _opts(session_id="abc"))
    assert resume[resume.index("--resume") + 1] == "abc"
    fresh = build_command(Config(), _opts(new_session_id="xyz"))
    assert fresh[fresh.index("--session-id") + 1] == "xyz"


def test_tools_budget_and_system_prompt():
    cmd = build_command(Config(), _opts(
        allowed_tools=["Read", "Bash(git *)"],
        disallowed_tools=["Write"],
        system_prompt_append="be terse",
        max_budget_usd=1.5,
    ))
    assert "--allowedTools" in cmd and "Bash(git *)" in cmd
    assert "--disallowedTools" in cmd and "Write" in cmd
    assert cmd[cmd.index("--append-system-prompt") + 1] == "be terse"
    assert cmd[cmd.index("--max-budget-usd") + 1] == "1.5"


# --- check_authenticated ---------------------------------------------------

def test_auth_via_env_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert check_authenticated() is True


def test_auth_via_credentials_file(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg_dir = tmp_path / ".claude"
    cfg_dir.mkdir()
    (cfg_dir / ".credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg_dir))
    assert check_authenticated() is True


def test_auth_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(empty))
    assert check_authenticated() is False


# --- run_prompt (json) -----------------------------------------------------

def _patch_exec(monkeypatch, proc):
    async def fake_exec(*a, **k):
        return proc
    monkeypatch.setattr(cli_mod.asyncio, "create_subprocess_exec", fake_exec)


class _JsonProc:
    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self._out, self._err, self.returncode = stdout, stderr, returncode

    async def communicate(self, input=None):
        return self._out, self._err

    def kill(self):
        pass

    async def wait(self):
        return self.returncode


def test_run_prompt_parses_result(monkeypatch):
    payload = (b'{"result":"hello","session_id":"sid","is_error":false,'
               b'"total_cost_usd":0.5,"duration_ms":123}')
    _patch_exec(monkeypatch, _JsonProc(stdout=payload))
    res = asyncio.run(run_prompt(Config(), _opts()))
    assert res.text == "hello"
    assert res.session_id == "sid"
    assert res.is_error is False
    assert res.cost_usd == 0.5
    assert res.duration_ms == 123


def test_run_prompt_malformed_json_falls_back(monkeypatch):
    _patch_exec(monkeypatch, _JsonProc(stdout=b"not json at all"))
    res = asyncio.run(run_prompt(Config(), _opts()))
    assert res.is_error is True
    assert res.text == "not json at all"


def test_run_prompt_nonzero_without_output_raises(monkeypatch):
    _patch_exec(monkeypatch, _JsonProc(stdout=b"", stderr=b"boom", returncode=2))
    with pytest.raises(WrapperError) as exc:
        asyncio.run(run_prompt(Config(), _opts()))
    assert exc.value.code == "cli_failed"


# --- run_prompt_stream (NDJSON) --------------------------------------------

class _StreamProc:
    def __init__(self, lines, stderr=b"", returncode=0):
        self._lines = lines
        self.returncode = returncode
        self.stdin = self._Stdin()
        self.stdout = self._Stdout(lines)
        self.stderr = self._Stderr(stderr)

    class _Stdin:
        def write(self, b):
            pass

        async def drain(self):
            pass

        def close(self):
            pass

    class _Stdout:
        def __init__(self, lines):
            self._lines = lines

        def __aiter__(self):
            self._it = iter(self._lines)
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration

    class _Stderr:
        def __init__(self, data):
            self._data = data

        async def read(self):
            return self._data

    def kill(self):
        pass

    async def wait(self):
        return self.returncode


def test_stream_collects_deltas_and_summary(monkeypatch):
    lines = [
        b'{"type":"system","subtype":"init","session_id":"sid"}\n',
        b'{"type":"stream_event","event":{"type":"content_block_delta",'
        b'"delta":{"type":"text_delta","text":"He"}}}\n',
        b'{"type":"stream_event","event":{"type":"content_block_delta",'
        b'"delta":{"type":"text_delta","text":"llo"}}}\n',
        b'{"type":"stream_event","event":{"type":"content_block_delta",'
        b'"delta":{"type":"thinking_delta","text":"IGNORE"}}}\n',
        b'{"type":"result","subtype":"success","is_error":false,"result":"Hello",'
        b'"total_cost_usd":0.1,"duration_ms":50,"session_id":"sid"}\n',
    ]
    _patch_exec(monkeypatch, _StreamProc(lines))

    deltas = []

    async def on_delta(t):
        deltas.append(t)

    res = asyncio.run(run_prompt_stream(Config(), _opts(), on_delta))
    assert deltas == ["He", "llo"]  # thinking_delta excluded
    assert res.text == "Hello"
    assert res.session_id == "sid"
    assert res.cost_usd == 0.1
    assert res.is_error is False


def test_stream_without_result_event_falls_back(monkeypatch):
    lines = [
        b'{"type":"system","subtype":"init","session_id":"sid"}\n',
        b'{"type":"stream_event","event":{"type":"content_block_delta",'
        b'"delta":{"type":"text_delta","text":"partial"}}}\n',
    ]
    _patch_exec(monkeypatch, _StreamProc(lines))

    async def on_delta(t):
        pass

    res = asyncio.run(run_prompt_stream(Config(), _opts(), on_delta))
    assert res.is_error is True
    assert res.text == "partial"  # accumulated deltas used as fallback

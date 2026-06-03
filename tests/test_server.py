"""Shared input validation / policy gates (spec §7, §8) via _prepare_options."""

import asyncio

import pytest

from claude_wrapper.config import Config
from claude_wrapper.errors import WrapperError
from claude_wrapper.server import _prepare_options
from claude_wrapper.sessions import SessionRegistry


def _prep(cfg, reg, **kw):
    base = dict(
        prompt="hi", working_dir=None, model=None, permission_mode=None,
        allowed_tools=None, disallowed_tools=None, system_prompt_append=None,
        session_id=None, max_budget_usd=None,
    )
    base.update(kw)
    return _prepare_options(cfg, reg, **base)


def test_invalid_permission_mode(tmp_path):
    with pytest.raises(WrapperError) as exc:
        _prep(Config(), SessionRegistry(2),
              working_dir=str(tmp_path), permission_mode="bogus")
    assert exc.value.code == "invalid_permission_mode"


def test_danger_gate_blocks_by_default(tmp_path):
    with pytest.raises(WrapperError) as exc:
        _prep(Config(dangerous=False), SessionRegistry(2),
              working_dir=str(tmp_path), permission_mode="bypassPermissions")
    assert exc.value.code == "danger_zone_disabled"


def test_danger_gate_allows_when_enabled(tmp_path):
    opts, _ = _prep(Config(dangerous=True), SessionRegistry(2),
                    working_dir=str(tmp_path), permission_mode="bypassPermissions")
    assert opts.permission_mode == "bypassPermissions"


def test_new_session_mints_id_and_slot_key(tmp_path):
    opts, slot_key = _prep(Config(), SessionRegistry(2), working_dir=str(tmp_path))
    assert opts.session_id is None
    assert opts.new_session_id is not None
    assert slot_key == opts.new_session_id


def test_resume_uses_session_id_as_slot_key(tmp_path):
    reg = SessionRegistry(2)
    asyncio.run(reg.pin("s1", str(tmp_path.resolve())))
    opts, slot_key = _prep(Config(), reg, working_dir=str(tmp_path), session_id="s1")
    assert opts.session_id == "s1"
    assert opts.new_session_id is None
    assert slot_key == "s1"


def test_resume_pin_mismatch_rejected(tmp_path):
    reg = SessionRegistry(2)
    asyncio.run(reg.pin("s1", str(tmp_path.resolve())))
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(WrapperError) as exc:
        _prep(Config(), reg, working_dir=str(other), session_id="s1")
    assert exc.value.code == "working_dir_mismatch"


def test_default_mode_inherited_from_config(tmp_path):
    opts, _ = _prep(Config(permission_mode="acceptEdits"), SessionRegistry(2),
                    working_dir=str(tmp_path))
    assert opts.permission_mode == "acceptEdits"

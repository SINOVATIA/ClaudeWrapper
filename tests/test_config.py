"""Config precedence and coercion (spec §4.2)."""

import os

from claude_wrapper.config import load_config


def _clear_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("CLAUDE_WRAPPER_"):
            monkeypatch.delenv(k, raising=False)


def test_defaults(monkeypatch):
    _clear_env(monkeypatch)
    cfg = load_config({})
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8787
    assert cfg.permission_mode == "default"
    assert cfg.dangerous is False


def test_env_over_default(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("CLAUDE_WRAPPER_PORT", "9999")
    monkeypatch.setenv("CLAUDE_WRAPPER_DANGEROUS", "true")
    cfg = load_config({})
    assert cfg.port == 9999
    assert cfg.dangerous is True


def test_cli_over_env(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("CLAUDE_WRAPPER_PORT", "9999")
    cfg = load_config({"port": 1234})
    assert cfg.port == 1234


def test_none_cli_overrides_are_ignored(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("CLAUDE_WRAPPER_PORT", "9999")
    # main() passes flags the user didn't set as None; they must not clobber env.
    cfg = load_config({"port": None})
    assert cfg.port == 9999


def test_full_precedence_chain(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    toml = tmp_path / "w.toml"
    toml.write_text('port = 5000\nmodel = "opus"\n', encoding="utf-8")

    # TOML is the lowest configurable source.
    cfg = load_config({}, config_path=str(toml))
    assert cfg.port == 5000
    assert cfg.model == "opus"

    # Env beats TOML.
    monkeypatch.setenv("CLAUDE_WRAPPER_PORT", "6000")
    assert load_config({}, config_path=str(toml)).port == 6000

    # CLI beats both.
    assert load_config({"port": 7000}, config_path=str(toml)).port == 7000


def test_bool_coercion(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("CLAUDE_WRAPPER_DANGEROUS", "off")
    assert load_config({}).dangerous is False
    monkeypatch.setenv("CLAUDE_WRAPPER_DANGEROUS", "yes")
    assert load_config({}).dangerous is True


def test_root_path_property():
    cfg = load_config({"root": str(os.getcwd())})
    assert cfg.root_path is not None
    assert cfg.root_path.is_absolute()

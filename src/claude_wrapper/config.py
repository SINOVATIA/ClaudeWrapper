"""Configuration with precedence: CLI flag > env var > TOML file > built-in default.

See spec §4.2.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

# Env var name for each config field.
_ENV = {
    "host": "CLAUDE_WRAPPER_HOST",
    "port": "CLAUDE_WRAPPER_PORT",
    "token": "CLAUDE_WRAPPER_TOKEN",
    "cli": "CLAUDE_WRAPPER_CLI",
    "model": "CLAUDE_WRAPPER_MODEL",
    "permission_mode": "CLAUDE_WRAPPER_PERMISSION_MODE",
    "root": "CLAUDE_WRAPPER_ROOT",
    "timeout": "CLAUDE_WRAPPER_TIMEOUT",
    "max_concurrency": "CLAUDE_WRAPPER_MAX_CONCURRENCY",
    "dangerous": "CLAUDE_WRAPPER_DANGEROUS",
}

# Fields parsed as int / bool when coming from env or TOML strings.
_INT_FIELDS = {"port", "timeout", "max_concurrency"}
_BOOL_FIELDS = {"dangerous"}

_TRUE = {"1", "true", "yes", "on"}


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8787
    token: str | None = None
    cli: str = "claude"
    model: str | None = None
    permission_mode: str = "default"
    root: str | None = None
    timeout: int = 300
    max_concurrency: int = 4
    dangerous: bool = False

    @property
    def root_path(self) -> Path | None:
        return Path(self.root).resolve() if self.root else None


def _coerce(name: str, value: object) -> object:
    if name in _BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _TRUE
    if name in _INT_FIELDS:
        return int(value)
    return value


def load_config(cli_overrides: dict[str, object], config_path: str | None = None) -> Config:
    """Build a Config applying precedence: CLI > env > TOML > default.

    ``cli_overrides`` should contain only flags the user actually passed
    (others omitted/None), so they don't clobber lower-precedence sources.
    """
    valid = {f.name for f in fields(Config)}
    values: dict[str, object] = {}

    # 3. TOML file (lowest of the configurable sources)
    if config_path:
        data = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
        for key, val in data.items():
            if key in valid:
                values[key] = _coerce(key, val)

    # 2. Environment
    for name, env_name in _ENV.items():
        raw = os.environ.get(env_name)
        if raw is not None and raw != "":
            values[name] = _coerce(name, raw)

    # 1. CLI overrides (highest)
    for name, val in cli_overrides.items():
        if val is not None and name in valid:
            values[name] = _coerce(name, val)

    return Config(**values)

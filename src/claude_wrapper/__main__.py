"""Entrypoint: parse CLI flags, build config (CLI > env > TOML > default),
start the FastMCP server over Streamable HTTP (spec §4)."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_config
from .server import build_server, run_http


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="claude-wrapper", description=__doc__)
    p.add_argument("--version", action="version",
                   version=f"claude-wrapper {__version__}")
    p.add_argument("--config", help="Path to a TOML config file.")
    p.add_argument("--host", help="Bind host (default 127.0.0.1).")
    p.add_argument("--port", type=int, help="Bind port (default 8787).")
    p.add_argument("--token", help="Shared auth token consumers must present.")
    p.add_argument("--cli", help="Path to the claude executable (default: claude on PATH).")
    p.add_argument("--model", help="Default model (e.g. sonnet, opus, full id).")
    p.add_argument("--permission-mode", dest="permission_mode",
                   help="Default permission mode (default|acceptEdits|auto|bypassPermissions|dontAsk|plan).")
    p.add_argument("--root", help="Confinement root: per-call working_dir must live inside it.")
    p.add_argument("--timeout", type=int, help="Per-call timeout in seconds (default 300).")
    p.add_argument("--max-concurrency", dest="max_concurrency", type=int,
                   help="Max concurrent claude subprocesses (default 4).")
    p.add_argument("--dangerous", action="store_true", default=None,
                   help="Unlock per-call bypassPermissions (danger zone, spec §7.4).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    overrides = {k: v for k, v in vars(args).items() if k != "config"}
    cfg = load_config(overrides, config_path=args.config)

    banner = (
        f"claude-wrapper {__version__} on http://{cfg.host}:{cfg.port}/mcp  "
        f"(model={cfg.model or 'cli-default'}, permission_mode={cfg.permission_mode}, "
        f"root={cfg.root or 'any'}, dangerous={'ON' if cfg.dangerous else 'off'}, "
        f"auth={'token' if cfg.token else 'none'})"
    )
    print(banner, file=sys.stderr, flush=True)

    server = build_server(cfg)
    run_http(cfg, server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

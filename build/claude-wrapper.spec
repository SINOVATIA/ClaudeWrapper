# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file spec for claude-wrapper (spec §3.2, §10).

Build (from the repo root, in the project venv with the ``build`` extra):

    pyinstaller build/claude-wrapper.spec \
        --distpath build/dist --workpath build/work --noconfirm

Produces ``build/dist/claude-wrapper.exe`` (Windows) or ``build/dist/claude-wrapper``
(Linux). The binary still requires Node + the Claude Code CLI on the host (§2).
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# uvicorn and mcp resolve several implementations via dynamic import (event
# loops, HTTP/WS protocols, lifespan, transports); pull their whole subtrees in.
# Skip ``mcp.cli`` — it's an optional Typer-based CLI we never use and importing
# it (which collect_submodules does) hard-fails without the ``typer`` extra.
def _keep(name: str) -> bool:
    return not name.startswith("mcp.cli")


hiddenimports: list[str] = []
for pkg in ("uvicorn", "mcp", "anyio", "starlette"):
    hiddenimports += collect_submodules(pkg, filter=_keep)

datas = collect_data_files("mcp")

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],  # noqa: F821 (SPECPATH injected by PyInstaller)
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="claude-wrapper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

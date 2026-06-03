"""Session path-pinning, per-session serialization, and concurrency limiting.

See spec §6 (concurrency model) and §7.3 (working-dir confinement).
"""

from __future__ import annotations

import asyncio
import uuid
import weakref
from pathlib import Path
from typing import Any

from .config import Config
from .errors import WrapperError


def validate_working_dir(cfg: Config, working_dir: str) -> str:
    """Resolve and validate a per-call working dir; return the canonical path.

    Enforces: existing absolute directory, and (if configured) inside --root.
    """
    if not working_dir:
        raise WrapperError("invalid_working_dir", "working_dir is required.")

    path = Path(working_dir)
    if not path.is_absolute():
        raise WrapperError("invalid_working_dir", "working_dir must be an absolute path.")

    resolved = path.resolve()
    if not resolved.is_dir():
        raise WrapperError(
            "invalid_working_dir", f"working_dir is not an existing directory: {resolved}"
        )

    root = cfg.root_path
    if root is not None and root not in resolved.parents and resolved != root:
        raise WrapperError(
            "working_dir_forbidden",
            f"working_dir {resolved} is outside the configured root {root}.",
        )

    return str(resolved)


class SessionRegistry:
    """Tracks session -> pinned path, serializes same-session calls, and caps
    total concurrent CLI subprocesses across all sessions."""

    def __init__(self, max_concurrency: int) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._paths: dict[str, str] = {}            # session_id -> pinned working_dir
        self._locks: dict[str, asyncio.Lock] = {}   # session_id -> serialization lock
        self._guard = asyncio.Lock()                # protects the maps above
        # MCP client connection -> Claude session_id. Weak-keyed so an entry
        # drops automatically when the client disconnects (its ServerSession is
        # garbage-collected). This is how each connection (e.g. one opencode
        # instance) gets its own continuous Claude conversation (spec §6.3).
        self._connections: "weakref.WeakKeyDictionary[Any, str]" = (
            weakref.WeakKeyDictionary()
        )

    async def _lock_for(self, session_id: str) -> asyncio.Lock:
        async with self._guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
            return lock

    def check_pin(self, session_id: str, working_dir: str) -> None:
        """Reject a resume whose working_dir differs from the session's pin."""
        pinned = self._paths.get(session_id)
        if pinned is not None and pinned != working_dir:
            raise WrapperError(
                "working_dir_mismatch",
                f"session {session_id} is pinned to {pinned}, not {working_dir}.",
            )

    async def pin(self, session_id: str, working_dir: str) -> None:
        async with self._guard:
            self._paths.setdefault(session_id, working_dir)

    def new_session_id(self) -> str:
        return str(uuid.uuid4())

    def connection_session(self, connection: Any) -> str | None:
        """Return the Claude session_id bound to this client connection, if any."""
        return self._connections.get(connection)

    def bind_connection(self, connection: Any, session_id: str) -> None:
        """Bind (once) a Claude session_id to a client connection for reuse."""
        self._connections.setdefault(connection, session_id)

    class _Slot:
        def __init__(self, registry: "SessionRegistry", session_lock: asyncio.Lock) -> None:
            self._registry = registry
            self._session_lock = session_lock

        async def __aenter__(self) -> None:
            await self._session_lock.acquire()
            await self._registry._semaphore.acquire()

        async def __aexit__(self, *exc: object) -> None:
            self._registry._semaphore.release()
            self._session_lock.release()

    async def slot(self, session_id: str) -> "_Slot":
        """Acquire a per-session lock + a global concurrency slot."""
        lock = await self._lock_for(session_id)
        return self._Slot(self, lock)

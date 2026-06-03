"""FastMCP server exposing the Claude Code CLI as MCP tools (spec §5).

M1 scope: ``claude_health`` + one-shot/resumable ``claude_prompt``, with the
working-dir sandbox, path pinning, concurrency limiting, and the danger-zone
gate wired in.
"""

from __future__ import annotations

import hmac
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from . import __version__
from .cli import (
    PromptOptions,
    check_authenticated,
    cli_version,
    node_version,
    run_prompt,
    run_prompt_stream,
)
from .config import Config
from .errors import WrapperError
from .sessions import SessionRegistry, validate_working_dir

_VALID_MODES = {
    "default", "acceptEdits", "auto", "bypassPermissions", "dontAsk", "plan",
}


def _prepare_options(
    cfg: Config,
    registry: SessionRegistry,
    *,
    prompt: str,
    working_dir: str,
    model: str | None,
    permission_mode: str | None,
    allowed_tools: list[str] | None,
    disallowed_tools: list[str] | None,
    system_prompt_append: str | None,
    session_id: str | None,
    max_budget_usd: float | None,
    json_schema: dict[str, Any] | None,
) -> tuple[PromptOptions, str]:
    """Validate inputs, enforce gates, and build PromptOptions + a slot key.

    Shared by ``claude_prompt`` and ``claude_prompt_stream``. Raises
    :class:`WrapperError` on any policy violation (spec §7, §8).
    """
    mode = permission_mode or cfg.permission_mode
    if mode not in _VALID_MODES:
        raise WrapperError("invalid_permission_mode", f"Unknown permission_mode: {mode}")
    if mode == "bypassPermissions" and not cfg.dangerous:
        raise WrapperError(
            "danger_zone_disabled",
            "bypassPermissions requires the server to be started with --dangerous.",
        )

    wd = validate_working_dir(cfg, working_dir)

    if session_id:
        registry.check_pin(session_id, wd)
        new_id = None
    else:
        new_id = registry.new_session_id()

    opts = PromptOptions(
        prompt=prompt,
        working_dir=wd,
        model=model,
        permission_mode=mode,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        system_prompt_append=system_prompt_append,
        session_id=session_id,
        new_session_id=new_id,
        max_budget_usd=max_budget_usd,
        json_schema=json_schema,
    )
    return opts, (session_id or new_id or wd)


def _ok(result: Any) -> dict[str, Any]:
    """Standard success payload shared by the prompt tools."""
    return {
        "text": result.text,
        "session_id": result.session_id,
        "is_error": result.is_error,
        "cost_usd": result.cost_usd,
        "duration_ms": result.duration_ms,
        "structured": result.structured,
    }


def _err(session_id: str | None, exc: WrapperError) -> dict[str, Any]:
    """Standard error payload (a WrapperError surfaced to the consumer)."""
    return {"text": "", "session_id": session_id, "is_error": True,
            "error_code": exc.code, "error": exc.message}


def build_server(cfg: Config) -> FastMCP:
    mcp = FastMCP("claude-wrapper", host=cfg.host, port=cfg.port)
    registry = SessionRegistry(cfg.max_concurrency)

    @mcp.tool()
    async def claude_health() -> dict[str, Any]:
        """Readiness probe (spec §5.4): CLI/Node versions, auth state, readiness."""
        version = await cli_version(cfg)
        node = await node_version()
        authenticated = check_authenticated()
        return {
            "wrapper_version": __version__,
            "cli_version": version,
            "node_version": node,
            "authenticated": authenticated,
            "ready": version is not None and authenticated,
            "dangerous_enabled": cfg.dangerous,
            "root": cfg.root,
            "max_concurrency": cfg.max_concurrency,
        }

    @mcp.tool()
    async def claude_prompt(
        prompt: str,
        working_dir: str,
        model: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        system_prompt_append: str | None = None,
        session_id: str | None = None,
        max_budget_usd: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a prompt through Claude Code and return its text result.

        ``working_dir`` is required and becomes the session's sandbox; it is
        pinned for the session's lifetime. Pass ``session_id`` to continue a
        prior conversation (the path must match). ``permission_mode`` =
        'bypassPermissions' requires the server to be started with --dangerous.
        Pass ``json_schema`` (a JSON Schema object) to force structured output;
        the parsed object is returned in the ``structured`` field (``text`` still
        carries Claude's prose).
        """
        try:
            opts, slot_key = _prepare_options(
                cfg, registry,
                prompt=prompt, working_dir=working_dir, model=model,
                permission_mode=permission_mode, allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
                system_prompt_append=system_prompt_append,
                session_id=session_id, max_budget_usd=max_budget_usd,
                json_schema=json_schema,
            )

            slot = await registry.slot(slot_key)
            async with slot:
                result = await run_prompt(cfg, opts)

            if result.session_id:
                await registry.pin(result.session_id, opts.working_dir)

            return _ok(result)
        except WrapperError as exc:
            return _err(session_id, exc)

    @mcp.tool()
    async def claude_session_new(
        prompt: str,
        working_dir: str,
        model: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        system_prompt_append: str | None = None,
        max_budget_usd: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start a fresh conversation and run its first turn (spec §5.3).

        Convenience over ``claude_prompt``: it never resumes (no ``session_id``
        input) and always mints a new session, pinned to ``working_dir``. The
        returned ``session_id`` is then passed to ``claude_prompt`` /
        ``claude_prompt_stream`` to continue the conversation.
        """
        try:
            opts, slot_key = _prepare_options(
                cfg, registry,
                prompt=prompt, working_dir=working_dir, model=model,
                permission_mode=permission_mode, allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
                system_prompt_append=system_prompt_append,
                session_id=None, max_budget_usd=max_budget_usd,
                json_schema=json_schema,
            )

            slot = await registry.slot(slot_key)
            async with slot:
                result = await run_prompt(cfg, opts)

            if result.session_id:
                await registry.pin(result.session_id, opts.working_dir)

            return _ok(result)
        except WrapperError as exc:
            return _err(None, exc)

    @mcp.tool()
    async def claude_prompt_stream(
        prompt: str,
        working_dir: str,
        ctx: Context,
        model: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        system_prompt_append: str | None = None,
        session_id: str | None = None,
        max_budget_usd: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Streaming variant of ``claude_prompt`` (spec §5.2).

        Identical inputs and final result. As Claude generates, each text delta
        is forwarded to the client as a progress notification (the delta in the
        notification's ``message`` field; ``progress`` is the cumulative
        character count). The return value carries the full aggregated text and
        the same summary fields as ``claude_prompt`` (including ``structured``
        when ``json_schema`` is supplied).
        """
        try:
            opts, slot_key = _prepare_options(
                cfg, registry,
                prompt=prompt, working_dir=working_dir, model=model,
                permission_mode=permission_mode, allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
                system_prompt_append=system_prompt_append,
                session_id=session_id, max_budget_usd=max_budget_usd,
                json_schema=json_schema,
            )

            sent = 0

            async def on_delta(chunk: str) -> None:
                nonlocal sent
                sent += len(chunk)
                await ctx.report_progress(progress=sent, total=None, message=chunk)

            slot = await registry.slot(slot_key)
            async with slot:
                result = await run_prompt_stream(cfg, opts, on_delta)

            if result.session_id:
                await registry.pin(result.session_id, opts.working_dir)

            return _ok(result)
        except WrapperError as exc:
            return _err(session_id, exc)

    @mcp.tool()
    async def claude_chat(
        prompt: str,
        working_dir: str,
        ctx: Context,
        model: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        system_prompt_append: str | None = None,
        max_budget_usd: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a message in THIS connection's ongoing conversation (spec §6.3).

        The wrapper keeps one Claude session per connected MCP client: the first
        call on a connection starts a fresh session (pinned to ``working_dir``);
        every later call on the SAME connection automatically resumes it — the
        caller never handles a ``session_id``. Two simultaneous clients (e.g.
        two opencode instances) therefore get two independent, isolated
        conversations, even in the same ``working_dir``. Ideal for a relay where
        the consumer is just a mailbox forwarding the user's messages.
        """
        connection = ctx.session  # stable per-connection identity (one per client)
        bound = registry.connection_session(connection)
        try:
            opts, slot_key = _prepare_options(
                cfg, registry,
                prompt=prompt, working_dir=working_dir, model=model,
                permission_mode=permission_mode, allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
                system_prompt_append=system_prompt_append,
                session_id=bound, max_budget_usd=max_budget_usd,
                json_schema=json_schema,
            )

            slot = await registry.slot(slot_key)
            async with slot:
                result = await run_prompt(cfg, opts)

            if result.session_id:
                await registry.pin(result.session_id, opts.working_dir)
                registry.bind_connection(connection, result.session_id)

            return _ok(result)
        except WrapperError as exc:
            return _err(bound, exc)

    return mcp


class TokenAuthMiddleware:
    """Pure ASGI middleware enforcing the shared token (spec §7.2, §8).

    Consumers present the token as ``Authorization: Bearer <token>`` or the
    ``X-Wrapper-Token`` header. Missing/invalid → HTTP 401 ``unauthorized``.
    Implemented at the ASGI layer (not Starlette's BaseHTTPMiddleware) so it
    does not buffer or break the Streamable HTTP response stream. Non-HTTP
    scopes (lifespan, websocket) pass straight through.
    """

    def __init__(self, app: Any, token: str) -> None:
        self._app = app
        self._token = token

    @staticmethod
    def _presented(scope: dict[str, Any]) -> str:
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if auth[:7].lower() == "bearer ":
            return auth[7:].strip()
        return headers.get(b"x-wrapper-token", b"").decode("latin-1").strip()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        if not hmac.compare_digest(self._presented(scope), self._token):
            body = b'{"error_code":"unauthorized","error":"Missing or invalid token."}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self._app(scope, receive, send)


def run_http(cfg: Config, mcp: FastMCP) -> None:
    """Serve the FastMCP app over Streamable HTTP, gated by the token if set."""
    import uvicorn

    app: Any = mcp.streamable_http_app()
    if cfg.token:
        app = TokenAuthMiddleware(app, cfg.token)

    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.host, port=cfg.port, log_level="info")
    )
    server.run()

"""Working-dir validation + session registry (spec §6, §7.3)."""

import asyncio

import pytest

from claude_wrapper.config import Config
from claude_wrapper.errors import WrapperError
from claude_wrapper.sessions import SessionRegistry, validate_working_dir


def test_validate_requires_absolute():
    with pytest.raises(WrapperError) as exc:
        validate_working_dir(Config(), "relative/path")
    assert exc.value.code == "invalid_working_dir"


def test_validate_existing_dir(tmp_path):
    assert validate_working_dir(Config(), str(tmp_path)) == str(tmp_path.resolve())


def test_validate_missing_dir(tmp_path):
    with pytest.raises(WrapperError) as exc:
        validate_working_dir(Config(), str(tmp_path / "nope"))
    assert exc.value.code == "invalid_working_dir"


def test_root_confinement(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "sub"
    inside.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()
    cfg = Config(root=str(root))

    assert validate_working_dir(cfg, str(inside)) == str(inside.resolve())
    assert validate_working_dir(cfg, str(root)) == str(root.resolve())  # root itself ok
    with pytest.raises(WrapperError) as exc:
        validate_working_dir(cfg, str(outside))
    assert exc.value.code == "working_dir_forbidden"


def test_pin_and_mismatch():
    reg = SessionRegistry(2)
    asyncio.run(reg.pin("s1", "/a"))
    reg.check_pin("s1", "/a")  # matching -> no raise
    with pytest.raises(WrapperError) as exc:
        reg.check_pin("s1", "/b")
    assert exc.value.code == "working_dir_mismatch"


def test_check_pin_unknown_session_is_noop():
    SessionRegistry(2).check_pin("never-seen", "/anywhere")  # must not raise


def test_new_session_id_is_unique_uuid():
    reg = SessionRegistry(1)
    a, b = reg.new_session_id(), reg.new_session_id()
    assert a != b
    assert len(a) == 36 and a.count("-") == 4


def test_same_session_calls_serialize():
    async def run():
        reg = SessionRegistry(4)
        order = []

        async def task(n):
            slot = await reg.slot("same")
            async with slot:
                order.append(("start", n))
                await asyncio.sleep(0.01)
                order.append(("end", n))

        await asyncio.gather(task(1), task(2))
        return order

    order = run_async(run())
    # A serialized pair never interleaves: first start is immediately followed
    # by its own end before the second start.
    assert order[0][0] == "start"
    assert order[1][0] == "end"
    assert order[2][0] == "start"


def test_global_concurrency_cap():
    async def run():
        reg = SessionRegistry(1)  # cap of 1 across distinct sessions
        live = peak = 0

        async def task(sid):
            nonlocal live, peak
            slot = await reg.slot(sid)
            async with slot:
                live += 1
                peak = max(peak, live)
                await asyncio.sleep(0.01)
                live -= 1

        await asyncio.gather(task("a"), task("b"), task("c"))
        return peak

    assert run_async(run()) == 1


class _Conn:
    """Stand-in for an MCP client connection (a ServerSession is weak-refable)."""


def test_connection_binding_is_per_connection():
    reg = SessionRegistry(2)
    a, b = _Conn(), _Conn()
    assert reg.connection_session(a) is None
    reg.bind_connection(a, "sid-a")
    reg.bind_connection(b, "sid-b")
    assert reg.connection_session(a) == "sid-a"
    assert reg.connection_session(b) == "sid-b"


def test_connection_binding_is_stable_once_set():
    reg = SessionRegistry(2)
    a = _Conn()
    reg.bind_connection(a, "first")
    reg.bind_connection(a, "second")  # setdefault: must not overwrite
    assert reg.connection_session(a) == "first"


def test_connection_binding_drops_on_gc():
    import gc

    reg = SessionRegistry(2)
    a = _Conn()
    reg.bind_connection(a, "sid")
    assert len(dict(reg._connections)) == 1
    del a
    gc.collect()
    assert len(dict(reg._connections)) == 0


def run_async(coro):
    return asyncio.run(coro)

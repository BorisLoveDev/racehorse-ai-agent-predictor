import pytest
from pathlib import Path

import services.stake.pipeline.checkpointer as cp_mod
from services.stake.pipeline.checkpointer import (
    init_checkpointer, get_checkpointer, shutdown_checkpointer,
)


@pytest.fixture(autouse=True)
async def _reset_singleton():
    """Ensure each test starts with no active checkpointer."""
    cp_mod._checkpointer = None
    cp_mod._checkpointer_cm = None
    yield
    # Teardown: if test forgot, clean up
    if cp_mod._checkpointer is not None:
        await shutdown_checkpointer()


@pytest.mark.asyncio
async def test_init_returns_checkpointer(tmp_path: Path):
    cp = await init_checkpointer(str(tmp_path / "cp.db"))
    assert cp is not None
    assert get_checkpointer() is cp
    await shutdown_checkpointer()


@pytest.mark.asyncio
async def test_init_is_idempotent(tmp_path: Path):
    cp1 = await init_checkpointer(str(tmp_path / "cp.db"))
    cp2 = await init_checkpointer(str(tmp_path / "cp.db"))
    assert cp1 is cp2
    await shutdown_checkpointer()


@pytest.mark.asyncio
async def test_get_without_init_raises(tmp_path: Path):
    with pytest.raises(RuntimeError):
        get_checkpointer()


@pytest.mark.asyncio
async def test_shutdown_clears_singleton(tmp_path: Path):
    await init_checkpointer(str(tmp_path / "cp.db"))
    await shutdown_checkpointer()
    with pytest.raises(RuntimeError):
        get_checkpointer()


@pytest.mark.asyncio
async def test_shutdown_noop_when_not_initialised():
    # Must not raise even when nothing was initialised.
    await shutdown_checkpointer()


@pytest.mark.asyncio
async def test_checkpointer_has_async_api(tmp_path: Path):
    cp = await init_checkpointer(str(tmp_path / "cp.db"))
    # AsyncSqliteSaver should expose aput/aget_tuple — smoke check.
    assert hasattr(cp, "aput")
    assert hasattr(cp, "aget_tuple")
    await shutdown_checkpointer()

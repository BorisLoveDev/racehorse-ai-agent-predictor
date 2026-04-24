"""AsyncSqliteSaver singleton for LangGraph graph state persistence.

The bot opens one AsyncSqliteSaver at startup (from services.stake.main.build_runtime)
and closes it at shutdown. One thread_id per race (`race:{race_id}:{user_id}`)
namespaces each race's checkpoints.

Why a module-level singleton: AsyncSqliteSaver is an async context manager
that holds an open aiosqlite connection. We cannot recreate it per graph
invocation without paying connection-open latency on every race AND losing
the in-flight state for any interrupt-resume round trip.
"""
from typing import Any, Optional

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


_checkpointer_cm: Optional[Any] = None
_checkpointer: Optional[AsyncSqliteSaver] = None


async def init_checkpointer(db_path: str) -> AsyncSqliteSaver:
    """Open (or reuse) the singleton AsyncSqliteSaver backed by `db_path`.

    Idempotent: a second call with any db_path returns the already-open saver.
    Callers who need a different path must call shutdown_checkpointer() first.
    """
    global _checkpointer_cm, _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    _checkpointer_cm = AsyncSqliteSaver.from_conn_string(db_path)
    _checkpointer = await _checkpointer_cm.__aenter__()
    return _checkpointer


async def shutdown_checkpointer() -> None:
    """Close the singleton AsyncSqliteSaver; no-op if not initialised."""
    global _checkpointer_cm, _checkpointer
    if _checkpointer_cm is not None:
        await _checkpointer_cm.__aexit__(None, None, None)
    _checkpointer_cm = None
    _checkpointer = None


def get_checkpointer() -> AsyncSqliteSaver:
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer not initialised; call init_checkpointer(db_path) at bot startup."
        )
    return _checkpointer

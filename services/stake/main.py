"""
Stake Racing Advisor Bot — Entry Point

Starts the aiogram bot with RedisStorage for FSM state persistence.
Registers all command and pipeline routers. Per D-01, D-02, PIPELINE-04.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import ErrorEvent, Message, Update
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from services.stake.settings import get_stake_settings
from services.stake.handlers.commands import router as commands_router
from services.stake.handlers.pipeline import router as pipeline_router
from services.stake.handlers.callbacks import router as callbacks_router
from services.stake.handlers.results import router as results_router
from src.logging_config import setup_logging

# Configure root logger so aiogram errors are visible
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")

logger = setup_logging("stake")


async def main() -> None:
    """Start the Stake Advisor Bot with Redis FSM storage.

    Loads settings, initializes Redis + aiogram Dispatcher, registers
    routers, and starts long-polling.
    """
    settings = get_stake_settings()

    # Redis for FSM persistence (PIPELINE-04 / D-24)
    redis_client = aioredis.from_url(settings.redis.url)
    storage = RedisStorage(
        redis=redis_client,
        state_ttl=settings.redis.state_ttl,
        data_ttl=settings.redis.data_ttl
    )

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=storage)

    # Debug middleware — log ALL incoming updates
    class DebugMiddleware(BaseMiddleware):
        async def __call__(self, handler, event, data):
            if isinstance(event, Message):
                logger.info(f"[MIDDLEWARE] Message from {event.from_user.id}: text_len={len(event.text or '')} content_type={event.content_type}")
            else:
                logger.info(f"[MIDDLEWARE] Update type: {type(event).__name__}")
            return await handler(event, data)

    dp.message.middleware(DebugMiddleware())

    # Global error handler — catch ALL handler exceptions and log them
    @dp.errors()
    async def on_error(event: ErrorEvent):
        logger.error(f"Handler error: {event.exception}", exc_info=event.exception)

    # Register routers — order matters: callbacks before pipeline (pipeline has catch-all F.text)
    # results router must come before pipeline router (state-specific handlers take priority)
    dp.include_router(commands_router)
    dp.include_router(callbacks_router)
    dp.include_router(results_router)   # Before pipeline — handles awaiting_result states
    dp.include_router(pipeline_router)  # Must be LAST (catches F.text)

    logger.info("Stake Racing Advisor bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


# ============================================================================
# Phase 1 runtime — wires config + invariants + checkpointer + graph.
# The legacy main() above continues to use the pre-Phase-1 graph; Phase 2
# will flip the entrypoint once the real LLM adapters are wired.
# ============================================================================

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from services.stake.audit.traces_repo import AuditTracesRepository
from services.stake.bankroll.migrations import apply_migrations
from services.stake.bankroll.repository import BankrollRepository
from services.stake.calibration.samples import CalibrationSamplesRepository
from services.stake.config import PhaseOneSettings, load_config
from services.stake.invariants.checker import InvariantChecker
from services.stake.pipeline.checkpointer import (
    init_checkpointer, shutdown_checkpointer,
)
from services.stake.pipeline.graph import compile_race_graph
from services.stake.probability.calibration import (
    CalibratorRegistry, IdentityCalibrator,
)


@dataclass
class StakeRuntime:
    settings: PhaseOneSettings
    checker: InvariantChecker
    graph: Any
    bankroll_repo: BankrollRepository
    samples_repo: CalibrationSamplesRepository
    traces_repo: AuditTracesRepository
    reflection_writer: Any
    _data_conn: sqlite3.Connection

    _shutdown_done: bool = False

    async def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        await shutdown_checkpointer()
        try:
            self._data_conn.close()
        except Exception:
            pass


async def _default_stub_parse_node(state):
    raise RuntimeError("parse_node not wired; inject via build_runtime(parse_node=...)")


async def _default_stub_research_node(state):
    raise RuntimeError("research_node not wired; inject via build_runtime(research_node=...)")


async def _default_stub_analyst_llm(payload):
    raise RuntimeError("analyst_llm not wired; inject via build_runtime(analyst_llm=...)")


async def build_runtime(
    *,
    config_path: Path = Path("config/config.yaml"),
    parse_node=None,
    research_node=None,
    analyst_llm=None,
    reflection_writer=None,
) -> StakeRuntime:
    """Assemble Phase-1 runtime: config, invariants, repos, checkpointer, graph.

    Callers inject LLM adapters (parse_node/research_node/analyst_llm) and
    reflection_writer. Default stubs raise on invocation — Phase 1 tests
    pass AsyncMock / MagicMock; Phase 2 will wire real adapters.

    Raises InvariantViolation(I1) if config attempts mode=live.
    """
    settings = load_config(config_path)  # may raise InvariantViolation
    checker = InvariantChecker(settings)
    checker.run_startup()

    # Data DB — one connection for the runtime's repos. Checkpointer uses its
    # own async connection (AsyncSqliteSaver owns it).
    db_path = os.environ.get("STAKE_DATABASE_PATH", "races.db")
    data_conn = sqlite3.connect(db_path)
    apply_migrations(data_conn)

    bankroll_repo = BankrollRepository(db_path)
    samples_repo = CalibrationSamplesRepository(data_conn)
    traces_repo = AuditTracesRepository(data_conn)

    cp_path = os.environ.get("STAKE_CHECKPOINTER_PATH", settings.checkpointer_path)
    checkpointer = await init_checkpointer(cp_path)

    graph = compile_race_graph(
        settings=settings, checker=checker, checkpointer=checkpointer,
        parse_node=parse_node or _default_stub_parse_node,
        research_node=research_node or _default_stub_research_node,
        analyst_llm=analyst_llm or _default_stub_analyst_llm,
        samples_repo=samples_repo,
        bankroll_repo=bankroll_repo,
        results_evaluator=None,
        calibrator_registry=CalibratorRegistry(default=IdentityCalibrator()),
        reflection_writer=reflection_writer,
        traces_repo=traces_repo,
        recorder_provider=None,  # TelegramGraphRunner supplies this at run time
    )

    return StakeRuntime(
        settings=settings, checker=checker, graph=graph,
        bankroll_repo=bankroll_repo, samples_repo=samples_repo,
        traces_repo=traces_repo, reflection_writer=reflection_writer,
        _data_conn=data_conn,
    )

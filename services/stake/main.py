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

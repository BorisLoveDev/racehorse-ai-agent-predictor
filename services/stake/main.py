"""
Stake Racing Advisor Bot — Entry Point

Starts the aiogram bot with RedisStorage for FSM state persistence.
Registers all command and pipeline routers. Per D-01, D-02, PIPELINE-04.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from services.stake.settings import get_stake_settings
from services.stake.handlers.commands import router as commands_router
from src.logging_config import setup_logging

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

    # Register routers
    dp.include_router(commands_router)
    # Pipeline router will be added in Plan 05

    logger.info("Stake Racing Advisor bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

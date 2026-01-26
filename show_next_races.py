#!/usr/bin/env python3
"""
Показать список ближайших заездов
"""

import asyncio
from tabtouch_parser import (
    RaceTracker,
    SOURCE_TIMEZONE,
    CLIENT_TIMEZONE,
    now_client,
    now_source
)


async def main():
    tracker = RaceTracker(headless=True)

    print("=" * 80)
    print("БЛИЖАЙШИЕ ЗАЕЗДЫ")
    print("=" * 80)
    print(f"Source timezone: {SOURCE_TIMEZONE}")
    print(f"Client timezone: {CLIENT_TIMEZONE}")
    print(f"Current time: {now_client().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("\nПолучаем данные...\n")

    races = await tracker.get_upcoming_races(limit=15)

    if not races:
        print("Заезды не найдены")
        return

    print(f"Найдено заездов: {len(races)}\n")

    for i, race in enumerate(races, 1):
        print(f"{i}. {race.time_client} (через {race.time_until}) | {race.location} | {race.race_number} | {race.distance}")
        print(f"   Тип: {race.race_type} | {race.channel or 'N/A'}")
        print(f"   URL: {race.url}")
        print()


if __name__ == "__main__":
    asyncio.run(main())

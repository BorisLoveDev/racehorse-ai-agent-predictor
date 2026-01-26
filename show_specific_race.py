#!/usr/bin/env python3
"""
Показать детали конкретного заезда
"""

import asyncio
import sys
from tabtouch_parser import RaceTracker


async def main():
    if len(sys.argv) < 2:
        print("Usage: python show_specific_race.py <race_url>")
        return

    url = sys.argv[1]
    tracker = RaceTracker(headless=True)

    print("=" * 80)
    print("ДЕТАЛИ ЗАЕЗДА")
    print("=" * 80)
    print(f"\nURL: {url}\n")
    print("Получаем данные...\n")

    details = await tracker.get_race_details(url)

    if not details:
        print("Не удалось получить данные о заезде")
        return

    print(f"Локация: {details.location}")
    print(f"Дата: {details.date}")
    print(f"Название: {details.race_name}")
    print(f"Заезд: R{details.race_number}")
    print(f"Дистанция: {details.distance}")
    print(f"Тип: {details.race_type}")
    print(f"Покрытие: {details.track_condition}")
    print(f"Старт: {details.start_time}")
    print(f"\nКоличество участников: {len(details.runners)}")

    if details.pool_totals:
        print(f"\nПулы:")
        for pool_name, total in details.pool_totals.items():
            print(f"  {pool_name}: {total}")

    print(f"\n{'=' * 80}")
    print("УЧАСТНИКИ (отсортировано по коэффициентам)")
    print('=' * 80)

    # Сортируем по коэффициентам
    runners = sorted(details.runners, key=lambda x: x.fixed_win if x.fixed_win > 0 else 999)

    for runner in runners:
        print(f"\n#{runner.number} {runner.name}")
        if runner.form:
            print(f"  Форма: {runner.form}")
        if runner.jockey:
            print(f"  Жокей: {runner.jockey}")
        if runner.trainer:
            print(f"  Тренер: {runner.trainer}")
        if runner.barrier:
            print(f"  Барьер: {runner.barrier}")
        if runner.weight:
            print(f"  Вес: {runner.weight}")
        if runner.rating:
            print(f"  Рейтинг: {runner.rating}")

        # Коэффициенты
        odds_parts = []
        if runner.fixed_win > 0:
            odds_parts.append(f"Fixed Win: {runner.fixed_win:.2f}")
        if runner.fixed_place > 0:
            odds_parts.append(f"Place: {runner.fixed_place:.2f}")
        if runner.tote_win > 0:
            odds_parts.append(f"Tote Win: {runner.tote_win:.2f}")
        if runner.tote_place > 0:
            odds_parts.append(f"Tote Place: {runner.tote_place:.2f}")

        if odds_parts:
            print(f"  Коэффициенты: {' | '.join(odds_parts)}")


if __name__ == "__main__":
    asyncio.run(main())

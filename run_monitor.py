#!/usr/bin/env python3
"""
Скрипт для непрерывного мониторинга заездов

Использование:
    python run_monitor.py                    # Мониторинг ближайшего заезда
    python run_monitor.py --url <race_url>   # Мониторинг конкретного заезда
    python run_monitor.py --continuous       # Непрерывный мониторинг всех заездов
"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from tabtouch_parser import (
    RaceTracker,
    RaceDetails,
    RaceResult,
    format_race_for_analysis,
    export_to_json,
    SOURCE_TIMEZONE,
    CLIENT_TIMEZONE,
    now_client
)


class RaceMonitor:
    """Мониторинг заездов с сохранением данных"""

    def __init__(self, output_dir: str = "race_data"):
        self.tracker = RaceTracker(headless=True)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def _save_race_data(self, race: RaceDetails):
        """Сохранить данные заезда"""
        filename = f"{race.location}_{race.race_number}_{race.date.replace(' ', '_')}.json"
        filepath = self.output_dir / "upcoming" / filename

        filepath.parent.mkdir(exist_ok=True)

        data = format_race_for_analysis(race)
        data["url"] = race.url
        data["scraped_at"] = race.scraped_at

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Saved: {filepath}")
        return filepath

    def _save_result_data(self, race_url: str, result: RaceResult):
        """Сохранить результаты заезда"""
        filename = f"{result.location}_{result.race_number}_{result.date.replace(' ', '_')}_result.json"
        filepath = self.output_dir / "results" / filename

        filepath.parent.mkdir(exist_ok=True)

        data = {
            "race_info": {
                "location": result.location,
                "date": result.date,
                "race_name": result.race_name,
                "race_number": result.race_number,
                "distance": result.distance
            },
            "finishing_order": result.finishing_order,
            "dividends": result.dividends,
            "pool_totals": result.pool_totals,
            "url": race_url,
            "scraped_at": result.scraped_at
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Saved: {filepath}")
        return filepath

    async def monitor_single_race(self, url: str, check_interval: int = 60):
        """
        Мониторинг одного заезда до получения результатов

        Args:
            url: URL заезда
            check_interval: Интервал проверки в секундах
        """
        print(f"\n{'='*60}")
        print(f"Monitoring race: {url}")
        print(f"Check interval: {check_interval}s")
        print(f"Source timezone: {SOURCE_TIMEZONE}")
        print(f"Client timezone: {CLIENT_TIMEZONE}")
        print(f"Current time: {now_client().strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"{'='*60}\n")

        # Сначала получаем детали заезда
        race_details = await self.tracker.get_race_details(url)
        if race_details:
            self._save_race_data(race_details)
            print(f"\nRace: {race_details.race_name}")
            print(f"Location: {race_details.location}")
            print(f"Start time: {race_details.start_time_client} (in {race_details.time_until})")
            print(f"Runners: {len(race_details.runners)}")

            print("\nOdds snapshot:")
            for r in sorted(race_details.runners, key=lambda x: x.fixed_win if x.fixed_win > 0 else 999):
                print(f"  #{r.number} {r.name}: {r.fixed_win:.2f}")

        # Мониторим до результата
        print("\nWaiting for results...")
        attempts = 0

        while True:
            attempts += 1
            print(f"\n[{now_client().strftime('%H:%M:%S %Z')}] Check #{attempts}")

            result = await self.tracker.check_race_result(url)

            if result and result.finishing_order:
                print("\n" + "="*60)
                print("RACE FINISHED!")
                print("="*60)

                self._save_result_data(url, result)

                print(f"\nResults for {result.race_name}:")
                for pos in result.finishing_order:
                    print(f"  {pos['position']}: #{pos['number']} {pos['name']} (Tote: ${pos.get('tote_win', 'N/A')})")

                print(f"\nDividends:")
                for div_type, div_data in result.dividends.items():
                    combo = div_data.get('combination', '')
                    amount = div_data.get('amount', '')
                    print(f"  {div_type}: {combo} = {amount}")

                return result

            print(f"  No results yet. Next check in {check_interval}s...")
            await asyncio.sleep(check_interval)

    async def monitor_continuous(self, check_interval: int = 120):
        """
        Непрерывный мониторинг всех заездов

        Получает ближайшие заезды, мониторит их до результатов,
        затем переходит к следующим заездам.
        """
        print(f"\n{'='*60}")
        print("CONTINUOUS RACE MONITOR")
        print(f"Check interval: {check_interval}s")
        print(f"Source timezone: {SOURCE_TIMEZONE}")
        print(f"Client timezone: {CLIENT_TIMEZONE}")
        print(f"Current time: {now_client().strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"{'='*60}\n")

        monitored_urls = set()  # Уже отслеженные заезды

        while True:
            try:
                # Получаем ближайшие заезды
                print(f"\n[{now_client().strftime('%H:%M:%S %Z')}] Fetching next races...")
                next_races = await self.tracker.get_upcoming_races(limit=10)

                if not next_races:
                    print("No upcoming races found. Waiting...")
                    await asyncio.sleep(check_interval)
                    continue

                print(f"Found {len(next_races)} upcoming races")

                # Обрабатываем каждый заезд
                for race in next_races:
                    if race.url in monitored_urls:
                        continue

                    print(f"\n--- Processing: {race.location} {race.race_number} at {race.time_client} (in {race.time_until}) ---")

                    # Получаем детали
                    details = await self.tracker.get_race_details(race.url)
                    if details:
                        self._save_race_data(details)

                    # Проверяем результаты
                    result = await self.tracker.check_race_result(race.url)

                    if result and result.finishing_order:
                        print(f"Results available for {race.location} {race.race_number}")
                        self._save_result_data(race.url, result)
                        monitored_urls.add(race.url)
                    else:
                        print(f"Race not finished yet: {race.location} {race.race_number}")

                await asyncio.sleep(check_interval)

            except KeyboardInterrupt:
                print("\nMonitoring stopped by user")
                break
            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(30)

    async def get_next_race_for_analysis(self) -> dict:
        """
        Получить данные ближайшего заезда для AI анализа

        Returns:
            dict с данными заезда готовыми для AI агента
        """
        details = await self.tracker.get_next_race_details()

        if not details:
            return {"error": "No upcoming races found"}

        self._save_race_data(details)

        return {
            "success": True,
            "race_url": details.url,
            "data": format_race_for_analysis(details)
        }


async def main():
    parser = argparse.ArgumentParser(description="TabTouch Race Monitor")
    parser.add_argument("--url", type=str, help="URL of specific race to monitor")
    parser.add_argument("--continuous", action="store_true", help="Continuous monitoring mode")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--output", type=str, default="race_data", help="Output directory")

    args = parser.parse_args()

    monitor = RaceMonitor(output_dir=args.output)

    if args.url:
        # Мониторинг конкретного заезда
        await monitor.monitor_single_race(args.url, check_interval=args.interval)

    elif args.continuous:
        # Непрерывный мониторинг
        await monitor.monitor_continuous(check_interval=args.interval)

    else:
        # По умолчанию - получить ближайший заезд для анализа
        print("Fetching next race for analysis...")
        result = await monitor.get_next_race_for_analysis()

        if result.get("success"):
            print(f"\nRace URL: {result['race_url']}")
            print(f"\nRace data saved to: {args.output}/upcoming/")
            print("\nData for AI analysis:")
            print(json.dumps(result['data'], indent=2, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())

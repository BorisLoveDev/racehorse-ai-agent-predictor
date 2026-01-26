"""
TabTouch Racing Data Parser
Парсер для сбора данных о скачках с tabtouch.mobi

Функционал:
- Получение списка ближайших заездов
- Парсинг деталей заезда (участники, коэффициенты, жокеи, тренеры)
- Парсинг результатов прошедших заездов
- Сохранение в JSON и SQLite
"""

import asyncio
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright, Page, Browser
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Timezone configuration
# TabTouch operates in Australia/Perth timezone (UTC+8)
SOURCE_TIMEZONE = ZoneInfo(os.getenv("SOURCE_TIMEZONE", "Australia/Perth"))
# Client timezone for display
CLIENT_TIMEZONE = ZoneInfo(os.getenv("CLIENT_TIMEZONE", "Australia/Perth"))


# ============== Timezone Helpers ==============

def now_utc() -> datetime:
    """Get current time in UTC"""
    return datetime.now(timezone.utc)

def now_source() -> datetime:
    """Get current time in source timezone (TabTouch/Perth)"""
    return datetime.now(SOURCE_TIMEZONE)

def now_client() -> datetime:
    """Get current time in client timezone"""
    return datetime.now(CLIENT_TIMEZONE)

def parse_race_time(time_str: str, date_str: str = None) -> datetime:
    """
    Parse race time from TabTouch (always in Perth timezone)

    Args:
        time_str: Time string like "05:12" or "5:12 AM"
        date_str: Optional date string like "Sun 26 Jan"

    Returns:
        Timezone-aware datetime in SOURCE_TIMEZONE
    """
    try:
        # Parse time
        time_str = time_str.strip()

        # Handle 24h format (e.g., "05:12")
        if ":" in time_str and len(time_str) <= 5:
            hour, minute = map(int, time_str.split(":"))
        # Handle 12h format (e.g., "5:12 AM")
        elif "AM" in time_str.upper() or "PM" in time_str.upper():
            time_obj = datetime.strptime(time_str.upper(), "%I:%M %p")
            hour, minute = time_obj.hour, time_obj.minute
        else:
            # Fallback - try to extract numbers
            parts = re.findall(r'\d+', time_str)
            if len(parts) >= 2:
                hour, minute = int(parts[0]), int(parts[1])
            else:
                return None

        # Use today's date in source timezone if not provided
        today = datetime.now(SOURCE_TIMEZONE)

        # Create datetime with source timezone
        dt = today.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If the time is in the past (more than 12 hours ago), it might be tomorrow
        if (datetime.now(SOURCE_TIMEZONE) - dt).total_seconds() > 12 * 3600:
            dt = dt + timedelta(days=1)

        return dt

    except Exception as e:
        print(f"Error parsing race time '{time_str}': {e}")
        return None

def convert_to_client_time(dt: datetime) -> datetime:
    """Convert datetime to client timezone"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume source timezone if naive
        dt = dt.replace(tzinfo=SOURCE_TIMEZONE)
    return dt.astimezone(CLIENT_TIMEZONE)

def format_time_for_display(dt: datetime, include_tz: bool = True) -> str:
    """Format datetime for display in client timezone"""
    if dt is None:
        return ""
    client_dt = convert_to_client_time(dt)
    if include_tz:
        return client_dt.strftime("%H:%M %Z")
    return client_dt.strftime("%H:%M")

def get_time_until_race(race_time: datetime) -> str:
    """Get human-readable time until race starts"""
    if race_time is None:
        return "Unknown"

    now = datetime.now(SOURCE_TIMEZONE)
    if race_time.tzinfo is None:
        race_time = race_time.replace(tzinfo=SOURCE_TIMEZONE)

    diff = race_time - now
    total_seconds = diff.total_seconds()

    if total_seconds < 0:
        return "Started"
    elif total_seconds < 60:
        return f"{int(total_seconds)}s"
    elif total_seconds < 3600:
        return f"{int(total_seconds // 60)}m"
    else:
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


# ============== Data Models ==============

@dataclass
class NextRace:
    """Ближайший заезд из списка next-events"""
    time: str  # Original time string from TabTouch (Perth timezone)
    location: str
    race_number: str
    distance: str
    channel: Optional[str]
    url: str
    race_type: str = ""  # races/trots/dogs
    time_parsed: Optional[datetime] = None  # Timezone-aware datetime

    @property
    def time_client(self) -> str:
        """Time formatted for client timezone"""
        return format_time_for_display(self.time_parsed) if self.time_parsed else self.time

    @property
    def time_until(self) -> str:
        """Time until race starts"""
        return get_time_until_race(self.time_parsed)


@dataclass
class Runner:
    """Участник заезда (лошадь/собака)"""
    number: int
    name: str
    form: str = ""
    barrier: int = 0
    weight: str = ""
    jockey: str = ""
    trainer: str = ""
    rating: int = 0
    fixed_win: float = 0.0
    fixed_place: float = 0.0
    tote_win: float = 0.0
    tote_place: float = 0.0


@dataclass
class RaceDetails:
    """Полные детали заезда"""
    location: str
    date: str
    track_condition: str
    race_name: str
    race_number: int
    distance: str
    race_type: str
    start_time: str  # Original time string (Perth timezone)
    url: str
    runners: list[Runner] = field(default_factory=list)
    pool_totals: dict = field(default_factory=dict)
    scraped_at: str = ""
    start_time_parsed: Optional[datetime] = None  # Timezone-aware datetime
    scraped_at_utc: Optional[datetime] = None  # UTC timestamp

    @property
    def start_time_client(self) -> str:
        """Start time formatted for client timezone"""
        return format_time_for_display(self.start_time_parsed) if self.start_time_parsed else self.start_time

    @property
    def time_until(self) -> str:
        """Time until race starts"""
        return get_time_until_race(self.start_time_parsed)


@dataclass
class RaceResult:
    """Результаты завершившегося заезда"""
    location: str
    date: str
    race_name: str
    race_number: int
    distance: str
    finishing_order: list[dict] = field(default_factory=list)  # [{position, number, name, jockey, trainer, tote_win, fixed_win, fixed_place, sp_win, sp_place}]
    dividends: dict = field(default_factory=dict)  # {quinella, exacta, trifecta, first4, double, quaddie}
    pool_totals: dict = field(default_factory=dict)
    url: str = ""
    scraped_at: str = ""
    scraped_at_utc: Optional[datetime] = None  # UTC timestamp


# ============== Parser Class ==============

class TabTouchParser:
    """Основной класс парсера TabTouch"""

    BASE_URL = "https://www.tabtouch.mobi"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Запуск браузера"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        # Use SOURCE_TIMEZONE for browser to get times in source timezone
        # This ensures consistent parsing regardless of server location
        self.context = await self.browser.new_context(
            viewport={"width": 430, "height": 932},  # Mobile viewport
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            locale='en-AU',
            timezone_id=str(SOURCE_TIMEZONE),  # Use configured source timezone
        )
        # Hide webdriver
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        self.page = await self.context.new_page()
        self.page.set_default_timeout(60000)  # 60 seconds default timeout

    async def close(self):
        """Закрытие браузера"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _wait_for_content(self, timeout: int = 10000):
        """Ожидание загрузки контента"""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
        except:
            await asyncio.sleep(2)

    # ============== Next Races ==============

    async def get_next_races(self, race_type: str = "all") -> list[NextRace]:
        """
        Получить список ближайших заездов

        Args:
            race_type: "all", "races" (лошади), "trots" (рысаки), "dogs" (собаки)
        """
        await self.page.goto(f"{self.BASE_URL}/next-events", wait_until="domcontentloaded", timeout=60000)
        await self._wait_for_content(timeout=15000)

        # Фильтр по типу (если нужен)
        if race_type != "all":
            try:
                filter_btn = self.page.locator(f'button:has-text("{race_type}")')
                if await filter_btn.count() > 0:
                    await filter_btn.click()
                    await asyncio.sleep(1)
            except:
                pass

        races = []
        items = self.page.locator('ul > li > a[href*="/tote/meetings/"]')
        count = await items.count()

        for i in range(count):
            item = items.nth(i)
            try:
                href = await item.get_attribute("href")
                text = await item.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]

                # Парсинг текста: "05:12 SHEPPARTON R1 390m Sky TV 1"
                time_str = lines[0] if lines else ""
                location = lines[1] if len(lines) > 1 else ""
                race_info = lines[2] if len(lines) > 2 else ""
                distance = lines[3] if len(lines) > 3 else ""
                channel = lines[4] if len(lines) > 4 else None

                # Извлечь номер заезда
                race_match = re.search(r'R(\d+)', race_info)
                race_number = race_match.group(0) if race_match else race_info

                races.append(NextRace(
                    time=time_str,
                    location=location,
                    race_number=race_number,
                    distance=distance,
                    channel=channel,
                    url=f"{self.BASE_URL}{href}" if href.startswith("/") else href,
                    race_type=race_type,
                    time_parsed=parse_race_time(time_str)
                ))
            except Exception as e:
                print(f"Error parsing race item {i}: {e}")
                continue

        return races

    # ============== Race Details ==============

    async def get_race_details(self, url: str) -> Optional[RaceDetails]:
        """
        Получить детали конкретного заезда

        Args:
            url: URL заезда (например, https://www.tabtouch.mobi/tote/meetings/srx/1?date=2026-01-26)
        """
        await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await self._wait_for_content(timeout=15000)

        try:
            # Информация о месте и дате
            location_btn = self.page.locator('nav button').first
            location = await location_btn.inner_text() if await location_btn.count() > 0 else ""
            location = location.split("\n")[0].strip()

            # Дата и состояние трека
            date_elem = self.page.locator('nav time').first
            date_str = await date_elem.inner_text() if await date_elem.count() > 0 else ""

            track_condition = ""
            track_elem = self.page.locator('nav >> text=/Good|Soft|Heavy|Firm/i').first
            if await track_elem.count() > 0:
                track_condition = await track_elem.inner_text()

            # Название заезда
            race_name_elem = self.page.locator('h2').first
            race_name = await race_name_elem.inner_text() if await race_name_elem.count() > 0 else ""

            # Дистанция и тип
            distance_elem = self.page.locator('h2 + div').first
            distance_info = await distance_elem.inner_text() if await distance_elem.count() > 0 else ""
            parts = distance_info.split("·")
            distance = parts[0].strip() if parts else ""
            race_type = parts[1].strip() if len(parts) > 1 else ""

            # Номер заезда из URL
            race_num_match = re.search(r'/(\d+)\?', url)
            race_number = int(race_num_match.group(1)) if race_num_match else 0

            # Время старта
            time_elem = self.page.locator(r'div:has(h2) + div >> text=/\d{1,2}:\d{2}/').first
            start_time = ""
            if await time_elem.count() > 0:
                start_time = await time_elem.inner_text()

            # Парсинг участников
            runners = await self._parse_runners()

            # Pool totals
            pool_totals = await self._parse_pool_totals()

            # Parse start time with timezone
            start_time_parsed = parse_race_time(start_time) if start_time else None
            scraped_at_utc = now_utc()

            return RaceDetails(
                location=location,
                date=date_str,
                track_condition=track_condition,
                race_name=race_name,
                race_number=race_number,
                distance=distance,
                race_type=race_type,
                start_time=start_time,
                url=url,
                runners=runners,
                pool_totals=pool_totals,
                scraped_at=scraped_at_utc.isoformat(),
                start_time_parsed=start_time_parsed,
                scraped_at_utc=scraped_at_utc
            )

        except Exception as e:
            print(f"Error getting race details: {e}")
            return None

    async def _parse_runners(self) -> list[Runner]:
        """Парсинг списка участников заезда"""
        runners = []

        # Находим список участников (listitem внутри основного списка)
        runner_items = self.page.locator('ul > li:has(button:has-text(".00"))')
        count = await runner_items.count()

        for i in range(count):
            try:
                item = runner_items.nth(i)
                text = await item.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]

                if not lines:
                    continue

                # Номер участника (первая строка - число)
                number = 0
                name = ""
                for j, line in enumerate(lines):
                    if line.isdigit():
                        number = int(line)
                        # Имя обычно следующее
                        if j + 1 < len(lines):
                            name = lines[j + 1].replace("*", "").strip()
                        break

                if not number:
                    continue

                # Парсинг характеристик из текста
                form = ""
                barrier = 0
                weight = ""
                jockey = ""
                trainer = ""
                rating = 0

                for line in lines:
                    if line.startswith("F:"):
                        form = line.replace("F:", "").strip()
                    elif line.startswith("Br:"):
                        try:
                            barrier = int(line.replace("Br:", "").strip())
                        except:
                            pass
                    elif line.startswith("W:"):
                        weight = line.replace("W:", "").strip()
                    elif line.startswith("J:"):
                        jockey = line.replace("J:", "").strip()
                    elif line.startswith("T:"):
                        trainer = line.replace("T:", "").strip()

                # Рейтинг (число в конце, обычно 2-3 цифры)
                for line in reversed(lines):
                    if line.isdigit() and 10 <= int(line) <= 100:
                        rating = int(line)
                        break

                # Коэффициенты (ищем кнопки с числами)
                odds_buttons = item.locator('button:has-text(".")')
                fixed_win, fixed_place = 0.0, 0.0
                tote_win, tote_place = 0.0, 0.0

                if await odds_buttons.count() >= 1:
                    # Первая кнопка - Fixed odds
                    first_btn = await odds_buttons.nth(0).inner_text()
                    odds = re.findall(r'[\d.]+', first_btn)
                    if len(odds) >= 2:
                        fixed_win = float(odds[0])
                        fixed_place = float(odds[1])

                if await odds_buttons.count() >= 2:
                    # Вторая кнопка - Tote odds
                    second_btn = await odds_buttons.nth(1).inner_text()
                    odds = re.findall(r'[\d.]+', second_btn)
                    if len(odds) >= 2:
                        tote_win = float(odds[0])
                        tote_place = float(odds[1])

                runners.append(Runner(
                    number=number,
                    name=name,
                    form=form,
                    barrier=barrier,
                    weight=weight,
                    jockey=jockey,
                    trainer=trainer,
                    rating=rating,
                    fixed_win=fixed_win,
                    fixed_place=fixed_place,
                    tote_win=tote_win,
                    tote_place=tote_place
                ))

            except Exception as e:
                print(f"Error parsing runner {i}: {e}")
                continue

        return runners

    async def _parse_pool_totals(self) -> dict:
        """Парсинг общих сумм пулов"""
        pool_totals = {}

        try:
            pool_section = self.page.locator('h3:has-text("Pool Totals") + ul')
            if await pool_section.count() > 0:
                items = pool_section.locator('li')
                count = await items.count()

                for i in range(count):
                    text = await items.nth(i).inner_text()
                    lines = text.split("\n")
                    if len(lines) >= 2:
                        key = lines[0].strip().lower().replace(" ", "_")
                        value = lines[-1].strip()
                        pool_totals[key] = value
        except:
            pass

        return pool_totals

    # ============== Race Results ==============

    async def get_race_results(self, url: str) -> Optional[RaceResult]:
        """
        Получить результаты завершившегося заезда

        Args:
            url: URL заезда
        """
        await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await self._wait_for_content(timeout=15000)

        try:
            # Проверяем есть ли результаты
            results_indicator = self.page.locator(r'text=/Results.*\d+-\d+/')
            if await results_indicator.count() == 0:
                print("No results available for this race")
                return None

            # Информация о заезде
            location_btn = self.page.locator('nav button').first
            location = await location_btn.inner_text() if await location_btn.count() > 0 else ""
            location = location.split("\n")[0].strip()

            date_elem = self.page.locator('nav time').first
            date_str = await date_elem.inner_text() if await date_elem.count() > 0 else ""

            race_name_elem = self.page.locator('h2').first
            race_name = await race_name_elem.inner_text() if await race_name_elem.count() > 0 else ""

            distance_elem = self.page.locator('h2 + div').first
            distance_info = await distance_elem.inner_text() if await distance_elem.count() > 0 else ""
            distance = distance_info.split("·")[0].strip()

            race_num_match = re.search(r'/(\d+)\?', url)
            race_number = int(race_num_match.group(1)) if race_num_match else 0

            # Парсинг финишного порядка
            finishing_order = await self._parse_finishing_order()

            # Парсинг дивидендов
            dividends = await self._parse_dividends()

            # Pool totals
            pool_totals = await self._parse_pool_totals()

            scraped_at_utc = now_utc()

            return RaceResult(
                location=location,
                date=date_str,
                race_name=race_name,
                race_number=race_number,
                distance=distance,
                finishing_order=finishing_order,
                dividends=dividends,
                pool_totals=pool_totals,
                url=url,
                scraped_at=scraped_at_utc.isoformat(),
                scraped_at_utc=scraped_at_utc
            )

        except Exception as e:
            print(f"Error getting race results: {e}")
            return None

    async def _parse_finishing_order(self) -> list[dict]:
        """Парсинг финишного порядка"""
        order = []

        positions = ["1ST", "2ND", "3RD", "4TH"]

        for pos in positions:
            try:
                item = self.page.locator(f'li:has-text("{pos}")').first
                if await item.count() == 0:
                    continue

                text = await item.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]

                # Найти номер и имя
                number = 0
                name = ""
                jockey = ""
                trainer = ""

                for j, line in enumerate(lines):
                    if line.isdigit() and int(line) < 30:  # Номер участника
                        number = int(line)
                        if j + 1 < len(lines) and not lines[j+1].startswith(("J:", "T:")):
                            name = lines[j + 1]
                    elif line.startswith("J:"):
                        jockey = line.replace("J:", "").strip()
                    elif line.startswith("T:"):
                        trainer = line.replace("T:", "").strip()

                # Коэффициенты
                odds = re.findall(r'[\d.]+', text)
                tote_win = float(odds[0]) if odds else 0.0

                order.append({
                    "position": pos,
                    "number": number,
                    "name": name,
                    "jockey": jockey,
                    "trainer": trainer,
                    "tote_win": tote_win
                })

            except Exception as e:
                print(f"Error parsing position {pos}: {e}")
                continue

        return order

    async def _parse_dividends(self) -> dict:
        """Парсинг дивидендов"""
        dividends = {}

        div_types = ["Quinella", "Exacta", "Trifecta", "First 4", "Double", "Quaddie"]

        for div_type in div_types:
            try:
                item = self.page.locator(f'li:has-text("{div_type}")').first
                if await item.count() > 0:
                    text = await item.inner_text()
                    # Ищем сумму (формат $XX.XX или $X,XXX.XX)
                    amount_match = re.search(r'\$[\d,]+\.?\d*', text)
                    # Ищем комбинацию (формат X-X-X)
                    combo_match = re.search(r'\d+-\d+(?:-\d+)*', text)

                    dividends[div_type.lower().replace(" ", "_")] = {
                        "combination": combo_match.group() if combo_match else "",
                        "amount": amount_match.group() if amount_match else ""
                    }
            except:
                continue

        return dividends


# ============== Database Storage ==============

class RaceDatabase:
    """SQLite хранилище для данных о заездах"""

    def __init__(self, db_path: str = "races.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Инициализация таблиц БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Таблица заездов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                location TEXT,
                date TEXT,
                track_condition TEXT,
                race_name TEXT,
                race_number INTEGER,
                distance TEXT,
                race_type TEXT,
                start_time TEXT,
                status TEXT DEFAULT 'upcoming',
                scraped_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица участников
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER,
                number INTEGER,
                name TEXT,
                form TEXT,
                barrier INTEGER,
                weight TEXT,
                jockey TEXT,
                trainer TEXT,
                rating INTEGER,
                fixed_win REAL,
                fixed_place REAL,
                tote_win REAL,
                tote_place REAL,
                FOREIGN KEY (race_id) REFERENCES races(id)
            )
        """)

        # Таблица результатов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER UNIQUE,
                finishing_order TEXT,
                dividends TEXT,
                pool_totals TEXT,
                scraped_at TEXT,
                FOREIGN KEY (race_id) REFERENCES races(id)
            )
        """)

        conn.commit()
        conn.close()

    def save_race(self, race: RaceDetails) -> int:
        """Сохранить данные заезда"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO races
                (url, location, date, track_condition, race_name, race_number,
                 distance, race_type, start_time, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                race.url, race.location, race.date, race.track_condition,
                race.race_name, race.race_number, race.distance, race.race_type,
                race.start_time, race.scraped_at
            ))

            race_id = cursor.lastrowid

            # Сохранить участников
            cursor.execute("DELETE FROM runners WHERE race_id = ?", (race_id,))

            for runner in race.runners:
                cursor.execute("""
                    INSERT INTO runners
                    (race_id, number, name, form, barrier, weight, jockey, trainer,
                     rating, fixed_win, fixed_place, tote_win, tote_place)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    race_id, runner.number, runner.name, runner.form, runner.barrier,
                    runner.weight, runner.jockey, runner.trainer, runner.rating,
                    runner.fixed_win, runner.fixed_place, runner.tote_win, runner.tote_place
                ))

            conn.commit()
            return race_id

        finally:
            conn.close()

    def save_result(self, race_url: str, result: RaceResult) -> bool:
        """Сохранить результаты заезда"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Найти race_id
            cursor.execute("SELECT id FROM races WHERE url = ?", (race_url,))
            row = cursor.fetchone()

            if not row:
                print(f"Race not found: {race_url}")
                return False

            race_id = row[0]

            cursor.execute("""
                INSERT OR REPLACE INTO results
                (race_id, finishing_order, dividends, pool_totals, scraped_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                race_id,
                json.dumps(result.finishing_order),
                json.dumps(result.dividends),
                json.dumps(result.pool_totals),
                result.scraped_at
            ))

            # Обновить статус заезда
            cursor.execute(
                "UPDATE races SET status = 'finished' WHERE id = ?",
                (race_id,)
            )

            conn.commit()
            return True

        finally:
            conn.close()

    def get_upcoming_races(self) -> list[dict]:
        """Получить предстоящие заезды"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM races
            WHERE status = 'upcoming'
            ORDER BY date, start_time
        """)

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_race_with_runners(self, race_id: int) -> Optional[dict]:
        """Получить заезд с участниками"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM races WHERE id = ?", (race_id,))
        race = cursor.fetchone()

        if not race:
            conn.close()
            return None

        cursor.execute("SELECT * FROM runners WHERE race_id = ?", (race_id,))
        runners = cursor.fetchall()

        cursor.execute("SELECT * FROM results WHERE race_id = ?", (race_id,))
        result = cursor.fetchone()

        conn.close()

        return {
            "race": dict(race),
            "runners": [dict(r) for r in runners],
            "result": dict(result) if result else None
        }


# ============== High-Level API ==============

class RaceTracker:
    """
    Высокоуровневый API для отслеживания заездов

    Использование:
        tracker = RaceTracker()

        # Получить ближайшие заезды
        next_races = await tracker.get_upcoming_races()

        # Получить детали ближайшего заезда
        race = await tracker.get_next_race_details()

        # Проверить результаты
        result = await tracker.check_race_result(race_url)
    """

    def __init__(self, db_path: str = "races.db", headless: bool = True):
        self.db = RaceDatabase(db_path)
        self.headless = headless

    async def get_upcoming_races(self, limit: int = 10) -> list[NextRace]:
        """Получить список ближайших заездов"""
        async with TabTouchParser(headless=self.headless) as parser:
            races = await parser.get_next_races()
            return races[:limit]

    async def get_next_race_details(self) -> Optional[RaceDetails]:
        """Получить детали ближайшего заезда"""
        async with TabTouchParser(headless=self.headless) as parser:
            races = await parser.get_next_races()

            if not races:
                return None

            # Берем первый заезд
            next_race = races[0]
            details = await parser.get_race_details(next_race.url)

            if details:
                self.db.save_race(details)

            return details

    async def get_race_details(self, url: str) -> Optional[RaceDetails]:
        """Получить детали конкретного заезда"""
        async with TabTouchParser(headless=self.headless) as parser:
            details = await parser.get_race_details(url)

            if details:
                self.db.save_race(details)

            return details

    async def check_race_result(self, url: str) -> Optional[RaceResult]:
        """Проверить результаты заезда"""
        async with TabTouchParser(headless=self.headless) as parser:
            result = await parser.get_race_results(url)

            if result:
                self.db.save_result(url, result)

            return result

    async def monitor_race(self, url: str, check_interval: int = 60) -> RaceResult:
        """
        Мониторинг заезда до появления результатов

        Args:
            url: URL заезда
            check_interval: Интервал проверки в секундах
        """
        print(f"Monitoring race: {url}")

        while True:
            result = await self.check_race_result(url)

            if result and result.finishing_order:
                print("Race finished! Results available.")
                return result

            print(f"Race not finished yet. Checking again in {check_interval}s...")
            await asyncio.sleep(check_interval)


# ============== Utility Functions ==============

def export_to_json(data, filename: str):
    """Экспорт данных в JSON"""
    def convert(obj):
        if hasattr(obj, '__dict__'):
            return asdict(obj) if hasattr(obj, '__dataclass_fields__') else obj.__dict__
        return str(obj)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=convert, ensure_ascii=False)
    print(f"Data exported to {filename}")


def format_race_for_analysis(race: RaceDetails) -> dict:
    """
    Форматирование данных заезда для AI анализа

    Возвращает структурированные данные для передачи AI агенту
    """
    return {
        "race_info": {
            "location": race.location,
            "date": race.date,
            "track_condition": race.track_condition,
            "race_name": race.race_name,
            "distance": race.distance,
            "race_type": race.race_type,
            "start_time_source": race.start_time,  # Original time (Perth)
            "start_time_client": race.start_time_client,  # Client timezone
            "start_time_utc": race.start_time_parsed.astimezone(timezone.utc).isoformat() if race.start_time_parsed else None,
            "time_until_start": race.time_until,
            "source_timezone": str(SOURCE_TIMEZONE),
            "client_timezone": str(CLIENT_TIMEZONE),
        },
        "runners": [
            {
                "number": r.number,
                "name": r.name,
                "form": r.form,
                "barrier": r.barrier,
                "weight": r.weight,
                "jockey": r.jockey,
                "trainer": r.trainer,
                "rating": r.rating,
                "odds": {
                    "fixed_win": r.fixed_win,
                    "fixed_place": r.fixed_place,
                    "tote_win": r.tote_win,
                    "tote_place": r.tote_place
                }
            }
            for r in race.runners
        ],
        "pool_totals": race.pool_totals,
        "metadata": {
            "scraped_at_utc": race.scraped_at,
            "source_timezone": str(SOURCE_TIMEZONE),
            "client_timezone": str(CLIENT_TIMEZONE),
        }
    }


# ============== CLI Entry Point ==============

async def main():
    """Пример использования парсера"""

    print("=" * 60)
    print("TabTouch Racing Parser")
    print("=" * 60)
    print(f"Source timezone: {SOURCE_TIMEZONE}")
    print(f"Client timezone: {CLIENT_TIMEZONE}")
    print(f"Current time (client): {now_client().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Current time (source): {now_source().strftime('%Y-%m-%d %H:%M:%S %Z')}")

    tracker = RaceTracker(headless=True)

    # 1. Получить ближайшие заезды
    print("\n[1] Fetching next races...")
    next_races = await tracker.get_upcoming_races(limit=5)

    print(f"Found {len(next_races)} upcoming races:")
    for race in next_races:
        print(f"  - {race.time_client} (in {race.time_until}) | {race.location} | {race.race_number} | {race.distance}")

    if not next_races:
        print("No races found")
        return

    # 2. Получить детали первого заезда
    print(f"\n[2] Fetching details for: {next_races[0].location} {next_races[0].race_number}")
    details = await tracker.get_race_details(next_races[0].url)

    if details:
        print(f"Race: {details.race_name}")
        print(f"Distance: {details.distance}")
        print(f"Track: {details.track_condition}")
        print(f"Start time: {details.start_time_client} (in {details.time_until})")
        print(f"\nRunners ({len(details.runners)}):")

        for r in details.runners:
            print(f"  #{r.number} {r.name}")
            print(f"      Jockey: {r.jockey} | Trainer: {r.trainer}")
            print(f"      Form: {r.form} | Barrier: {r.barrier} | Weight: {r.weight}")
            print(f"      Fixed: {r.fixed_win}/{r.fixed_place} | Rating: {r.rating}")

        # Экспорт в JSON
        export_to_json(format_race_for_analysis(details), "race_data.json")

    # 3. Пример проверки результатов (для прошедшего заезда)
    print("\n[3] Example: Checking results for a past race...")
    past_url = "https://www.tabtouch.mobi/tote/meetings/SR/1?date=2026-01-25"
    result = await tracker.check_race_result(past_url)

    if result and result.finishing_order:
        print(f"Results for {result.race_name}:")
        for pos in result.finishing_order:
            print(f"  {pos['position']}: #{pos['number']} {pos['name']}")
        print(f"\nDividends:")
        for div_type, div_data in result.dividends.items():
            print(f"  {div_type}: {div_data.get('combination', '')} - {div_data.get('amount', '')}")
    else:
        print("No results available yet")

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a horse racing data analysis system that scrapes race data from TabTouch (tabtouch.mobi), monitors live races, and provides a structured interface for AI-powered race analysis and predictions.

## Core Architecture

### Main Components

1. **TabTouchParser** (`tabtouch_parser.py:226-1102`)
   - Core web scraper using Playwright for async browser automation
   - Handles three main operations: fetching next races, scraping race details, parsing race results
   - Manages timezone conversions (TabTouch is in Australia/Perth timezone)
   - Stores data in SQLite database (`races.db`)

2. **Data Models** (`tabtouch_parser.py:137-222`)
   - `NextRace`: Upcoming race preview with time, location, race number
   - `Runner`: Individual horse/greyhound participant data
   - `RaceDetails`: Complete race information with all participants, odds, conditions
   - `RaceResult`: Post-race results including finishing order and dividends

3. **RaceTracker** (`tabtouch_parser.py`)
   - High-level wrapper around TabTouchParser
   - Provides simplified async methods for monitoring races

4. **RaceMonitor** (`run_monitor.py:29-90`)
   - Production monitoring loop that periodically checks for race updates
   - Saves race data to JSON files organized by status (upcoming/results)

### Timezone Architecture

Critical to understand: The system handles three timezone contexts:
- **SOURCE_TIMEZONE** (Australia/Perth): Where TabTouch operates - used for parsing race times from the website
- **CLIENT_TIMEZONE**: User's local timezone - used for display and analysis
- **UTC**: Standard timestamp storage in database

All race time parsing uses `parse_race_time()` which creates timezone-aware datetimes in SOURCE_TIMEZONE. The `format_time_for_display()` function converts to CLIENT_TIMEZONE for output.

## Common Development Tasks

### Running Scripts

```bash
# Install dependencies
python -m pip install -r requirements.txt
# or
python -m playwright install  # for Playwright browsers

# Show next races
python show_next_races.py

# Show details for specific race
python show_race_details.py

# Show specific race by URL
python show_specific_race.py

# Monitor a single race (waits for results)
python run_monitor.py --url "https://www.tabtouch.mobi/..."

# Continuous monitoring of all races
python run_monitor.py --continuous

# AI analysis example
python ai_analysis_example.py
```

### Setting Up Environment

Key `.env` variables:
- `SOURCE_TIMEZONE=Australia/Perth` (TabTouch's timezone, don't change)
- `CLIENT_TIMEZONE=Asia/Kuala_Lumpur` (set to user's local timezone)
- `ODDS_API_KEY=...` (for future odds API integration)
- `RACING_API_USERNAME/PASSWORD=...` (for TheRacingAPI integration)

### Data Flow

1. **Scraping**: Playwright browser navigates to TabTouch, waits for page load, parses HTML with locators
2. **Storage**: Data saved to SQLite via `export_to_json()` function
3. **File Output**: Race JSON files stored in `race_data/upcoming/` and `race_data/results/`
4. **AI Integration**: Use `format_race_for_analysis()` to prepare data for Claude/AI analysis

## Key Technical Details

### Browser Automation (Playwright)

- Mobile viewport (430x932) used to match TabTouch's responsive layout
- Uses stealth mode to avoid detection
- 60-second default page timeout
- Network idle wait ensures all dynamic content loads

### Database

The `races.db` SQLite database stores:
- Complete race information and results
- Historical data for future analysis
- Indexed by location, date, race number

### Data Export Format

`format_race_for_analysis()` creates a structured dict with:
- `race_info`: Location, distance, track condition, race type
- `runners`: List with number, name, form, barrier, weight, jockey, trainer, rating, odds
- Pool totals and dividends

This format is designed for AI analysis - it's what you'd feed to Claude for race predictions.

## Important Implementation Notes

- All race time parsing assumes SOURCE_TIMEZONE (Perth). Never parse race times in the browser's local timezone.
- Database transactions use atomic writes - check `export_to_json()` for the pattern
- Playwright contexts are reused across page navigations to maintain cookies/state
- The HTML parsing uses XPath/CSS selectors via Playwright's `.locator()` API - check specific race detail parsing at `tabtouch_parser.py:347-450`
- Race monitoring runs on configurable intervals (default 60s) - balance between API load and data freshness

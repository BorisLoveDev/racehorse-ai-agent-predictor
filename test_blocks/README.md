# Test Blocks - Progressive Testing Suite

This directory contains a progressive testing suite for the horse racing analysis system. Each test builds on the previous one, allowing you to verify each component independently.

## Test Structure

### Step 1: Get Next Race
**File**: `test_step1_next_race.py`

Tests the basic race fetching functionality.

- Uses `RaceTracker.get_upcoming_races(limit=1)`
- Displays: time, location, race number, distance, URL
- Saves URL to `last_race_url.txt` for next steps

**Run**:
```bash
python test_blocks/test_step1_next_race.py
```

**Expected Output**:
- Race location and details
- Start time in client timezone
- Time until race starts
- Race URL

---

### Step 2: Get Race Details
**File**: `test_step2_race_details.py`

Tests race detail fetching and formatting for AI analysis.

- Uses URL from Step 1 (or fetches new race)
- Calls `RaceTracker.get_race_details(url)`
- Formats via `format_race_for_analysis()`
- Displays: race_info, runners with odds, pool totals
- Saves to `last_race_data.json` for next steps

**Run**:
```bash
python test_blocks/test_step2_race_details.py
```

**Expected Output**:
- Complete race information
- Table of all runners with jockey and odds
- Pool totals
- JSON structure preview

---

### Step 3: Get Raw Agent Responses
**File**: `test_step3_raw_response.py`

Tests raw text analysis from AI agents without structured output.

- Uses race data from Step 2
- Initializes Gemini and Grok agents
- Calls workflow nodes directly to get raw analysis text
- Displays full text analysis from both agents
- Saves to `gemini_raw_analysis.txt` and `grok_raw_analysis.txt`

**Run**:
```bash
python test_blocks/test_step3_raw_response.py
```

**Expected Output**:
- Raw text analysis from Gemini agent
- Raw text analysis from Grok agent
- Each analysis includes form analysis, odds evaluation, race dynamics

**Note**: This step requires valid API keys in `.env`:
- `OPENROUTER_API_KEY` - for LLM access
- `TAVILY_API_KEY` - for web search (optional)

---

### Step 4: Get Structured Output
**File**: `test_step4_structured.py`

Tests the full agent workflow to generate structured bet recommendations.

- Uses race data from Step 2
- Calls `agent.analyze_race(race_data)` - full workflow
- Displays `StructuredBetOutput` with all bet recommendations
- Saves to `gemini_structured_output.json` and `grok_structured_output.json`

**Run**:
```bash
python test_blocks/test_step4_structured.py
```

**Expected Output**:
- Confidence score (0.0-1.0)
- Risk level (low/medium/high)
- Key factors list
- Bet recommendations by type (Win, Place, Exacta, Quinella, Trifecta, First4, QPS)
- Reasoning for each bet
- Overall reasoning summary

**Note**: This step requires the same API keys as Step 3.

---

## Quick Start

Run all steps in sequence:

```bash
# Make sure venv is activated and dependencies installed
source venv/bin/activate
pip install -r requirements.txt

# Run tests in order
python test_blocks/test_step1_next_race.py
python test_blocks/test_step2_race_details.py
python test_blocks/test_step3_raw_response.py
python test_blocks/test_step4_structured.py
```

## Output Files

After running all tests, you'll have:

- `last_race_url.txt` - URL of the race being tested
- `last_race_data.json` - Formatted race data for AI analysis
- `gemini_raw_analysis.txt` - Raw analysis from Gemini
- `grok_raw_analysis.txt` - Raw analysis from Grok
- `gemini_structured_output.json` - Structured bets from Gemini
- `grok_structured_output.json` - Structured bets from Grok

## Verification Checklist

- **Step 1**: ✓ Output contains time, location, URL
- **Step 2**: ✓ Output contains race_info dict and runners list with odds
- **Step 3**: ✓ Output contains text analysis from both agents
- **Step 4**: ✓ Output contains StructuredBetOutput with confidence_score and bet recommendations

## Troubleshooting

**"No upcoming races found"**
- TabTouch may not have races available at the moment
- Try changing `race_type` parameter ("races", "trots", "dogs")

**"Failed to initialize agent"**
- Check `.env` file has `OPENROUTER_API_KEY`
- Verify API key is valid and has credits

**"Playwright browser not installed"**
```bash
python -m playwright install
```

**"Module not found" errors**
```bash
pip install -r requirements.txt
```

## Development Notes

- All race times are handled with timezone awareness (Perth → Client TZ)
- Playwright runs in headless mode by default
- Tests are idempotent - safe to run multiple times
- Each test can run independently (Steps 2-4 will fetch new race if needed)

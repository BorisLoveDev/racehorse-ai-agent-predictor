"""
Step 2: Get race details for agents
Tests RaceTracker.get_race_details() and format_race_for_analysis().
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from tabtouch_parser import RaceTracker, format_race_for_analysis


async def main():
    print("=" * 80)
    print("STEP 2: Fetching Race Details and Formatting for Analysis")
    print("=" * 80)
    print()

    # Check if URL file exists from Step 1
    url_file = Path("test_blocks/last_race_url.txt")
    if url_file.exists():
        url = url_file.read_text().strip()
        print(f"📄 Using URL from Step 1: {url}")
    else:
        print("⚠️  No saved URL found. Getting next race...")
        tracker = RaceTracker(headless=True)
        races = await tracker.get_upcoming_races(limit=1, race_type="races")
        if not races:
            print("❌ No upcoming races found")
            return
        url = races[0].url
        print(f"📄 Using URL: {url}")

    print()

    # Initialize RaceTracker
    tracker = RaceTracker(headless=True)

    try:
        # Get race details
        print("Fetching race details...")
        race_details = await tracker.get_race_details(url)

        if not race_details:
            print("❌ Failed to fetch race details")
            return

        print("✅ Race details fetched successfully")
        print()

        # Format for AI analysis
        race_data = format_race_for_analysis(race_details)

        # Display race_info
        print("=" * 80)
        print("RACE INFO")
        print("=" * 80)
        race_info = race_data["race_info"]
        print(f"Location:         {race_info['location']}")
        print(f"Date:             {race_info['date']}")
        print(f"Race Name:        {race_info['race_name']}")
        print(f"Distance:         {race_info['distance']}")
        print(f"Race Type:        {race_info['race_type']}")
        print(f"Track Condition:  {race_info['track_condition']}")
        print(f"Start Time:       {race_info['start_time_client']}")
        print(f"Time Until:       {race_info['time_until_start']}")
        print()

        # Display runners summary
        print("=" * 80)
        print("RUNNERS SUMMARY")
        print("=" * 80)
        runners = race_data["runners"]
        print(f"Total Runners: {len(runners)}")
        print()
        print(f"{'No':<4} {'Name':<25} {'Jockey':<20} {'Win':<8} {'Place':<8}")
        print("-" * 80)
        for runner in runners:
            num = runner['number']
            name = runner['name'][:24]
            jockey = runner['jockey'][:19]
            win_odds = runner['odds']['fixed_win'] or runner['odds']['tote_win'] or '-'
            place_odds = runner['odds']['fixed_place'] or runner['odds']['tote_place'] or '-'
            print(f"{num:<4} {name:<25} {jockey:<20} {win_odds:<8} {place_odds:<8}")
        print()

        # Display pool totals if available
        if race_data.get("pool_totals"):
            print("=" * 80)
            print("POOL TOTALS")
            print("=" * 80)
            for pool_type, amount in race_data["pool_totals"].items():
                print(f"{pool_type}: ${amount:,.2f}")
            print()

        # Save formatted data for next steps
        output_file = Path("test_blocks/last_race_data.json")
        with open(output_file, "w") as f:
            json.dump(race_data, f, indent=2)
        print("✅ Race data saved to test_blocks/last_race_data.json for next steps")
        print()

        # Show snippet of JSON structure
        print("=" * 80)
        print("JSON STRUCTURE (first 2 runners)")
        print("=" * 80)
        sample_data = {
            "race_info": race_data["race_info"],
            "runners": race_data["runners"][:2],
            "pool_totals": race_data["pool_totals"]
        }
        print(json.dumps(sample_data, indent=2))

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

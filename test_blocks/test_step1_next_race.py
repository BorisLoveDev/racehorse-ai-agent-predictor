"""
Step 1: Get the next upcoming race
Tests RaceTracker.get_upcoming_races() to fetch the nearest race.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from tabtouch_parser import RaceTracker


async def main():
    print("=" * 80)
    print("STEP 1: Fetching Next Upcoming Race")
    print("=" * 80)
    print()

    # Initialize RaceTracker
    tracker = RaceTracker(headless=True)

    try:
        # Get the next upcoming race
        print("Fetching upcoming races...")
        races = await tracker.get_upcoming_races(limit=1, race_type="races")

        if not races:
            print("❌ No upcoming races found")
            return

        next_race = races[0]

        # Display race information
        print("✅ Next Race Found:")
        print("-" * 80)
        print(f"Location:       {next_race.location}")
        print(f"Race Number:    {next_race.race_number}")
        print(f"Distance:       {next_race.distance}")
        print(f"Start Time:     {next_race.time_client}")
        print(f"Time Until:     {next_race.time_until}")
        print(f"Race Type:      {next_race.race_type}")
        if next_race.channel:
            print(f"Channel:        {next_race.channel}")
        print(f"URL:            {next_race.url}")
        print("-" * 80)
        print()

        # Save URL for next steps
        with open("test_blocks/last_race_url.txt", "w") as f:
            f.write(next_race.url)
        print("✅ URL saved to test_blocks/last_race_url.txt for next steps")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

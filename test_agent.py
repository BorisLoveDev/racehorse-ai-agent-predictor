"""
Test script for running AI agents on a specific race.
Usage: python3 test_agent.py <race_url>
"""

import asyncio
import json
import sys
from datetime import datetime

from tabtouch_parser import TabTouchParser
from src.agents.gemini_agent import GeminiAgent
from src.agents.grok_agent import GrokAgent
from src.config.settings import get_settings


async def test_agent(race_url: str, agent_type: str = "both"):
    """Test AI agent on a specific race."""

    print(f"\n{'='*60}")
    print(f"🏇 Testing AI Agent on Race")
    print(f"{'='*60}\n")

    # Initialize parser
    parser = TabTouchParser(headless=True)

    async with parser:
        print(f"📥 Fetching race data from: {race_url}")
        race_details = await parser.get_race_details(race_url)

        if not race_details or not race_details.runners:
            print("❌ Failed to fetch race details or no runners found")
            return

        print(f"✅ Race loaded: {race_details.location} R{race_details.race_number}")
        print(f"   {len(race_details.runners)} runners")
        print(f"   Distance: {race_details.distance}")
        print(f"   Track: {race_details.track_condition}")
        print()

        # Format race data
        race_data = {
            "race_info": {
                "location": race_details.location,
                "date": race_details.date,
                "race_number": race_details.race_number,
                "race_name": race_details.race_name,
                "distance": race_details.distance,
                "track_condition": race_details.track_condition,
                "race_type": race_details.race_type,
                "start_time": race_details.start_time,
                "url": race_details.url
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
                    "fixed_win": r.fixed_win,
                    "fixed_place": r.fixed_place,
                    "tote_win": r.tote_win,
                    "tote_place": r.tote_place
                }
                for r in race_details.runners
            ],
            "pool_totals": race_details.pool_totals
        }

        # Test agents
        if agent_type in ["both", "gemini"]:
            await test_gemini(race_data)

        if agent_type in ["both", "grok"]:
            await test_grok(race_data)


async def test_gemini(race_data: dict):
    """Test Gemini agent."""
    print(f"\n{'='*60}")
    print(f"🤖 Testing Gemini Agent")
    print(f"{'='*60}\n")

    try:
        agent = GeminiAgent()
        print("⏳ Running analysis (this may take 30-60 seconds)...")

        start_time = datetime.now()
        structured_bet = await agent.analyze_race(race_data)
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"✅ Analysis complete in {elapsed:.1f}s\n")
        print_prediction(structured_bet)

    except Exception as e:
        print(f"❌ Gemini agent failed: {e}")
        import traceback
        traceback.print_exc()


async def test_grok(race_data: dict):
    """Test Grok agent."""
    print(f"\n{'='*60}")
    print(f"🤖 Testing Grok Agent")
    print(f"{'='*60}\n")

    try:
        agent = GrokAgent()
        print("⏳ Running analysis with high reasoning (this may take 60-90 seconds)...")

        start_time = datetime.now()
        structured_bet = await agent.analyze_race(race_data)
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"✅ Analysis complete in {elapsed:.1f}s\n")
        print_prediction(structured_bet)

    except Exception as e:
        print(f"❌ Grok agent failed: {e}")
        import traceback
        traceback.print_exc()


def print_prediction(structured_bet):
    """Pretty print a structured bet prediction."""

    print(f"📊 PREDICTION SUMMARY")
    print(f"{'─'*60}")
    print(f"Race: {structured_bet.race_location} R{structured_bet.race_number}")
    print(f"Confidence: {structured_bet.confidence_score:.1%}")
    print(f"Risk Level: {structured_bet.risk_level.upper()}")
    print()

    print(f"📝 ANALYSIS")
    print(f"{'─'*60}")
    print(structured_bet.analysis_summary)
    print()

    # Print bets
    bets = structured_bet.get_all_bets()
    if bets:
        print(f"💰 RECOMMENDED BETS")
        print(f"{'─'*60}")

        for bet_type, bet in bets.items():
            if bet_type == "win":
                print(f"✓ Win Bet: #{bet.horse_number} - ${bet.amount:.0f}")
                if bet.reasoning:
                    print(f"  Reason: {bet.reasoning}")

            elif bet_type == "place":
                print(f"✓ Place Bet: #{bet.horse_number} - ${bet.amount:.0f}")
                if bet.reasoning:
                    print(f"  Reason: {bet.reasoning}")

            elif bet_type == "exacta":
                print(f"✓ Exacta: {bet.first}-{bet.second} - ${bet.amount:.0f}")
                if bet.reasoning:
                    print(f"  Reason: {bet.reasoning}")

            elif bet_type == "quinella":
                horses = "/".join(map(str, sorted(bet.horses)))
                print(f"✓ Quinella: {horses} - ${bet.amount:.0f}")
                if bet.reasoning:
                    print(f"  Reason: {bet.reasoning}")

            elif bet_type == "trifecta":
                print(f"✓ Trifecta: {bet.first}-{bet.second}-{bet.third} - ${bet.amount:.0f}")
                if bet.reasoning:
                    print(f"  Reason: {bet.reasoning}")

            elif bet_type == "first4":
                order = "-".join(map(str, bet.horses))
                print(f"✓ First4: {order} - ${bet.amount:.0f}")
                if bet.reasoning:
                    print(f"  Reason: {bet.reasoning}")

            elif bet_type == "qps":
                horses = "/".join(map(str, sorted(bet.horses)))
                print(f"✓ QPS: {horses} - ${bet.amount:.0f}")
                if bet.reasoning:
                    print(f"  Reason: {bet.reasoning}")

            print()

        print(f"Total Bet Amount: ${structured_bet.total_bet_amount():.2f}")
        print()

    # Print key factors
    if structured_bet.key_factors:
        print(f"🔑 KEY FACTORS")
        print(f"{'─'*60}")
        for i, factor in enumerate(structured_bet.key_factors, 1):
            print(f"{i}. {factor}")
        print()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 test_agent.py <race_url> [gemini|grok|both]")
        print("\nExample:")
        print("  python3 test_agent.py https://www.tabtouch.mobi/racing/... both")
        sys.exit(1)

    race_url = sys.argv[1]
    agent_type = sys.argv[2] if len(sys.argv) > 2 else "both"

    if agent_type not in ["gemini", "grok", "both"]:
        print(f"❌ Invalid agent type: {agent_type}")
        print("Valid options: gemini, grok, both")
        sys.exit(1)

    # Check configuration
    settings = get_settings()
    openrouter_key = settings.api_keys.openrouter_api_key.get_secret_value()

    if not openrouter_key:
        print("❌ OpenRouter API key not configured!")
        print("Please set RACEHORSE_API_KEYS__OPENROUTER_API_KEY in your .env file")
        sys.exit(1)

    # Run test
    asyncio.run(test_agent(race_url, agent_type))


if __name__ == "__main__":
    main()

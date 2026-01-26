"""
Startup test script for Horse Racing Betting Agent.
Tests all components before launching the full system.
"""

import asyncio
import sys
from datetime import datetime
from typing import Optional

from aiogram import Bot
from tabtouch_parser import TabTouchParser
from src.config.settings import get_settings
from src.agents.gemini_agent import GeminiAgent
from src.agents.grok_agent import GrokAgent


async def test_telegram_connection(bot: Bot, chat_id: str) -> bool:
    """Test Telegram bot connection."""
    try:
        print("📱 Testing Telegram connection...")
        bot_info = await bot.get_me()
        print(f"✅ Telegram bot connected: @{bot_info.username}")

        # Send test message
        message = (
            "🤖 <b>Horse Racing Agent - System Startup</b>\n\n"
            "✅ Bot connected successfully!\n"
            "⏳ Running startup checks...\n"
        )
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        return True
    except Exception as e:
        print(f"❌ Telegram connection failed: {e}")
        return False


async def warmup_agent(agent, agent_name: str) -> Optional[str]:
    """Warmup agent with a test prompt."""
    try:
        print(f"🔥 Warming up {agent_name} agent...")

        # Create a simple test prompt
        from langchain_core.messages import HumanMessage
        from src.agents.base import AgentState

        # Simple hello test
        test_state: AgentState = {
            "race_data": {
                "race_info": {
                    "location": "Test",
                    "race_number": 1,
                    "distance": "1200m",
                    "track_condition": "Good"
                },
                "runners": [
                    {
                        "number": 1,
                        "name": "Test Horse",
                        "jockey": "Test Jockey",
                        "trainer": "Test Trainer",
                        "form": "111",
                        "barrier": 1,
                        "weight": 58.0,
                        "fixed_win": 3.5
                    }
                ]
            },
            "messages": [HumanMessage(content="Hello! Are you ready for race analysis?")],
            "search_queries": [],
            "search_results": [],
            "analysis": "",
            "structured_bet": None
        }

        # Test the LLM directly with a simple prompt
        response = await agent.llm.ainvoke([HumanMessage(content="Hello! Please respond with a brief greeting.")])

        response_text = response.content if hasattr(response, 'content') else str(response)
        print(f"✅ {agent_name} agent warmed up")
        print(f"   Response: {response_text[:100]}...")

        return response_text

    except Exception as e:
        print(f"❌ {agent_name} agent warmup failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def get_next_race_info() -> Optional[dict]:
    """Get information about the next upcoming horse race."""
    try:
        print("🏇 Fetching next horse race information...")

        parser = TabTouchParser(headless=True)
        async with parser:
            # Only get horse races (not greyhounds or harness)
            races = await parser.get_next_races(race_type="races")

            if not races:
                print("⚠️  No upcoming races found")
                return None

            # Get the closest race (first one)
            next_race = races[0]
            print(f"✅ Found next race: {next_race.location} {next_race.race_number}")

            return {
                "location": next_race.location,
                "race_number": next_race.race_number,
                "time": next_race.time,
                "time_until": next_race.time_until,
                "race_type": next_race.race_type,
                "url": next_race.url
            }

    except Exception as e:
        print(f"❌ Failed to fetch race info: {e}")
        import traceback
        traceback.print_exc()
        return None


async def send_startup_report(
    bot: Bot,
    chat_id: str,
    gemini_response: Optional[str],
    grok_response: Optional[str],
    next_race: Optional[dict]
):
    """Send comprehensive startup report to Telegram."""
    try:
        # Build report message
        message = "🏇 <b>Horse Racing Agent - Startup Report</b>\n\n"

        # Gemini status
        message += "🤖 <b>Gemini Agent Status:</b>\n"
        if gemini_response:
            message += "   ✅ Warmed up and ready\n"
            message += f"   💬 Response: <i>{gemini_response[:80]}...</i>\n\n"
        else:
            message += "   ❌ Warmup failed\n\n"

        # Grok status
        message += "🤖 <b>Grok Agent Status:</b>\n"
        if grok_response:
            message += "   ✅ Warmed up and ready\n"
            message += f"   💬 Response: <i>{grok_response[:80]}...</i>\n\n"
        else:
            message += "   ❌ Warmup failed\n\n"

        # Next race info
        message += "🏁 <b>Next Race Information:</b>\n"
        if next_race:
            message += f"   📍 Location: {next_race['location']}\n"
            message += f"   🏇 Race: R{next_race['race_number']}\n"
            message += f"   🕐 Time: {next_race['time']}\n"
            message += f"   ⏱ In: {next_race['time_until']}\n"
            message += f"   🏆 Type: {next_race['race_type']}\n\n"
        else:
            message += "   ⚠️ No upcoming races found\n\n"

        # System status
        message += "🔧 <b>System Status:</b>\n"
        all_ok = gemini_response and grok_response and next_race
        if all_ok:
            message += "   ✅ All systems operational\n"
            message += "   🚀 Ready to start monitoring!\n"
        else:
            message += "   ⚠️ Some components need attention\n"
            message += "   🔍 Check logs for details\n"

        await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        print("✅ Startup report sent to Telegram")

    except Exception as e:
        print(f"❌ Failed to send startup report: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main startup test flow."""
    print("\n" + "="*70)
    print("🏇 Horse Racing Betting Agent - Startup Test")
    print("="*70 + "\n")

    # Load configuration
    try:
        settings = get_settings()
        print("✅ Configuration loaded")
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return False

    # Initialize Telegram bot
    telegram_token = settings.api_keys.telegram_bot_token.get_secret_value()
    telegram_chat_id = settings.api_keys.telegram_chat_id

    if not telegram_token or telegram_token == "YOUR_TELEGRAM_BOT_TOKEN":
        print("❌ Telegram bot token not configured!")
        return False

    if not telegram_chat_id or telegram_chat_id == "YOUR_CHAT_ID":
        print("❌ Telegram chat ID not configured!")
        return False

    bot = Bot(token=telegram_token)

    # Test Telegram connection
    telegram_ok = await test_telegram_connection(bot, telegram_chat_id)
    if not telegram_ok:
        await bot.session.close()
        return False

    # Warmup agents in parallel
    print("\n🔥 Warming up AI agents...\n")

    try:
        gemini_agent = GeminiAgent()
        grok_agent = GrokAgent()

        results = await asyncio.gather(
            warmup_agent(gemini_agent, "Gemini"),
            warmup_agent(grok_agent, "Grok"),
            return_exceptions=True
        )

        gemini_response = results[0] if not isinstance(results[0], Exception) else None
        grok_response = results[1] if not isinstance(results[1], Exception) else None

    except Exception as e:
        print(f"❌ Failed to initialize agents: {e}")
        gemini_response = None
        grok_response = None

    # Get next race info
    print()
    next_race = await get_next_race_info()

    # Send comprehensive report to Telegram
    print()
    await send_startup_report(bot, telegram_chat_id, gemini_response, grok_response, next_race)

    # Close bot session
    await bot.session.close()

    # Summary
    print("\n" + "="*70)
    print("📊 Startup Test Summary")
    print("="*70)
    print(f"Telegram: {'✅' if telegram_ok else '❌'}")
    print(f"Gemini:   {'✅' if gemini_response else '❌'}")
    print(f"Grok:     {'✅' if grok_response else '❌'}")
    print(f"Next Race: {'✅' if next_race else '⚠️'}")
    print("="*70 + "\n")

    all_ok = telegram_ok and gemini_response and grok_response
    if all_ok:
        print("✅ All systems ready! You can now start the full system with: ./build.sh")
        return True
    else:
        print("⚠️  Some components need attention. Check the errors above.")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

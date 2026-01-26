"""
Step 3: Get raw responses from AI agents
Tests calling agents to get raw text analysis without structured output.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from src.agents.gemini_agent import GeminiAgent
from src.agents.grok_agent import GrokAgent


async def get_raw_analysis(agent, race_data: dict) -> str:
    """
    Get raw text analysis from an agent without structured output.
    Runs workflow up to deep_analysis node.
    """
    initial_state = {
        "race_data": race_data,
        "search_queries": [],
        "search_results": [],
        "analysis": "",
        "structured_bet": None,
        "messages": []
    }

    # Run workflow nodes sequentially
    state = agent._generate_search_queries(initial_state)
    state = agent._web_search(state)
    state = agent._deep_analysis(state)

    return state["analysis"]


async def main():
    print("=" * 80)
    print("STEP 3: Getting Raw Responses from AI Agents")
    print("=" * 80)
    print()

    # Load race data from Step 2
    data_file = Path("test_blocks/last_race_data.json")
    if not data_file.exists():
        print("❌ No race data found. Please run test_step2_race_details.py first")
        return

    with open(data_file, "r") as f:
        race_data = json.load(f)

    print(f"✅ Loaded race data: {race_data['race_info']['location']} R{race_data['race_info'].get('race_name', 'N/A')}")
    print(f"   Runners: {len(race_data['runners'])}")
    print()

    # Initialize agents
    print("Initializing agents...")
    try:
        gemini_agent = GeminiAgent()
        print("✅ Gemini agent initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Gemini agent: {e}")
        gemini_agent = None

    try:
        grok_agent = GrokAgent()
        print("✅ Grok agent initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Grok agent: {e}")
        grok_agent = None

    print()

    # Get raw analysis from Gemini
    if gemini_agent:
        print("=" * 80)
        print("GEMINI AGENT - RAW ANALYSIS")
        print("=" * 80)
        print()
        try:
            print("🔄 Generating analysis (this may take 30-60 seconds)...")
            gemini_analysis = await get_raw_analysis(gemini_agent, race_data)
            print()
            print(gemini_analysis)
            print()

            # Save to file
            with open("test_blocks/gemini_raw_analysis.txt", "w") as f:
                f.write(gemini_analysis)
            print("✅ Saved to test_blocks/gemini_raw_analysis.txt")

        except Exception as e:
            print(f"❌ Error getting Gemini analysis: {e}")
            import traceback
            traceback.print_exc()
        print()

    # Get raw analysis from Grok
    if grok_agent:
        print("=" * 80)
        print("GROK AGENT - RAW ANALYSIS")
        print("=" * 80)
        print()
        try:
            print("🔄 Generating analysis (this may take 30-60 seconds)...")
            grok_analysis = await get_raw_analysis(grok_agent, race_data)
            print()
            print(grok_analysis)
            print()

            # Save to file
            with open("test_blocks/grok_raw_analysis.txt", "w") as f:
                f.write(grok_analysis)
            print("✅ Saved to test_blocks/grok_raw_analysis.txt")

        except Exception as e:
            print(f"❌ Error getting Grok analysis: {e}")
            import traceback
            traceback.print_exc()
        print()

    print("=" * 80)
    print("STEP 3 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

"""
Step 4: Get structured output from AI agents
Tests the full agent workflow to generate StructuredBetOutput.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from src.agents.gemini_agent import GeminiAgent
from src.agents.grok_agent import GrokAgent


def display_structured_output(output, agent_name: str):
    """Display structured bet output in a readable format."""
    print("=" * 80)
    print(f"{agent_name.upper()} AGENT - STRUCTURED OUTPUT")
    print("=" * 80)
    print()

    print(f"Agent Name:        {output.agent_name}")
    print(f"Confidence Score:  {output.confidence_score:.2f}")
    print(f"Risk Level:        {output.risk_level}")
    print()

    print("KEY FACTORS:")
    for i, factor in enumerate(output.key_factors, 1):
        print(f"  {i}. {factor}")
    print()

    if output.win_bets:
        print("WIN BETS:")
        for bet in output.win_bets:
            print(f"  Horse #{bet.horse_number} - ${bet.amount:.2f}")
            print(f"    Reasoning: {bet.reasoning}")
        print()

    if output.place_bets:
        print("PLACE BETS:")
        for bet in output.place_bets:
            print(f"  Horse #{bet.horse_number} - ${bet.amount:.2f}")
            print(f"    Reasoning: {bet.reasoning}")
        print()

    if output.exacta_bets:
        print("EXACTA BETS:")
        for bet in output.exacta_bets:
            print(f"  {bet.first}-{bet.second} - ${bet.amount:.2f}")
            print(f"    Reasoning: {bet.reasoning}")
        print()

    if output.quinella_bets:
        print("QUINELLA BETS:")
        for bet in output.quinella_bets:
            print(f"  {bet.horses} - ${bet.amount:.2f}")
            print(f"    Reasoning: {bet.reasoning}")
        print()

    if output.trifecta_bets:
        print("TRIFECTA BETS:")
        for bet in output.trifecta_bets:
            print(f"  {bet.first}-{bet.second}-{bet.third} - ${bet.amount:.2f}")
            print(f"    Reasoning: {bet.reasoning}")
        print()

    if output.first4_bets:
        print("FIRST4 BETS:")
        for bet in output.first4_bets:
            print(f"  {bet.first}-{bet.second}-{bet.third}-{bet.fourth} - ${bet.amount:.2f}")
            print(f"    Reasoning: {bet.reasoning}")
        print()

    if output.qps_bets:
        print("QPS BETS:")
        for bet in output.qps_bets:
            print(f"  {bet.horses} - ${bet.amount:.2f}")
            print(f"    Reasoning: {bet.reasoning}")
        print()

    print("REASONING SUMMARY:")
    print(f"{output.reasoning}")
    print()


async def main():
    print("=" * 80)
    print("STEP 4: Getting Structured Output from AI Agents")
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

    # Get structured output from Gemini
    if gemini_agent:
        try:
            print("🔄 Running Gemini agent analysis (this may take 60-90 seconds)...")
            gemini_output = await gemini_agent.analyze_race(race_data)
            print()
            display_structured_output(gemini_output, "Gemini")

            # Save to JSON
            output_dict = gemini_output.model_dump()
            with open("test_blocks/gemini_structured_output.json", "w") as f:
                json.dump(output_dict, f, indent=2)
            print("✅ Saved to test_blocks/gemini_structured_output.json")
            print()

        except Exception as e:
            print(f"❌ Error getting Gemini structured output: {e}")
            import traceback
            traceback.print_exc()
        print()

    # Get structured output from Grok
    if grok_agent:
        try:
            print("🔄 Running Grok agent analysis (this may take 60-90 seconds)...")
            grok_output = await grok_agent.analyze_race(race_data)
            print()
            display_structured_output(grok_output, "Grok")

            # Save to JSON
            output_dict = grok_output.model_dump()
            with open("test_blocks/grok_structured_output.json", "w") as f:
                json.dump(output_dict, f, indent=2)
            print("✅ Saved to test_blocks/grok_structured_output.json")
            print()

        except Exception as e:
            print(f"❌ Error getting Grok structured output: {e}")
            import traceback
            traceback.print_exc()
        print()

    print("=" * 80)
    print("STEP 4 COMPLETE")
    print("=" * 80)
    print()
    print("All agent outputs saved to test_blocks/")


if __name__ == "__main__":
    asyncio.run(main())

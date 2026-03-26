"""
End-to-end pipeline test: raw race text -> parse -> calc -> skip check -> research -> analysis -> sizing -> format.

Uses gemini-flash-lite for ALL LLM calls (cheap).
Research is mocked (no API credits wasted on web search).
Everything else runs for real: parsing, math, analysis LLM, sizing, formatting.

This is THE critical test — validates the entire Phase 2 pipeline produces
real bet recommendations from raw Stake.com race text.
"""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

# Sample Stake.com race text (realistic format)
SAMPLE_RACE_TEXT = """
Ankara Hipodromu
Race 4 - 1400m Turf
Date: 26 Mar 2026

Runners:
1. Daglarkaya - Win: 21.00 - Place: 5.50 - Jockey: A. Kaya - Trainer: M. Demir - Form: 5-8-3-6
2. Emir Ilyas - Win: 2.10 - Place: 1.35 - Jockey: B. Yilmaz - Trainer: S. Ozturk - Form: 1-1-2-1
3. Ferman Yazar - Win: 5.50 - Place: 2.10 - Jockey: C. Arslan - Trainer: H. Aksoy - Form: 3-2-5-4
4. Hep Birlikte - Win: 11.00 - Place: 3.20 - Jockey: D. Celik - Trainer: A. Kurt - Form: 4-6-7-2
5. Simsekkiran - Win: 4.80 - Place: 1.95 - Jockey: E. Sahin - Trainer: T. Yildiz - Form: 2-3-1-5
6. Kivilcim Atesi - Win: 15.00 - Place: 4.00 - Jockey: F. Dogan - Trainer: N. Acar - Form: 7-4-8-3

Bet types: Win, Place

Balance: 100.00 USDT
"""

# Fake research results — no API calls needed
MOCK_RESEARCH_OUTPUT = {
    "runners": [
        {
            "runner_name": "Daglarkaya",
            "data_quality": "sparse",
            "form_summary": "Poor recent form, no wins in last 6 starts",
            "trainer_stats": "Low strike rate trainer",
            "expert_opinion": "No expert backing",
            "external_odds": None,
            "confidence_notes": "Limited data available",
        },
        {
            "runner_name": "Emir Ilyas",
            "data_quality": "rich",
            "form_summary": "Dominant form — 3 wins from last 4 starts, all convincing",
            "trainer_stats": "S. Ozturk: 35% win rate this season",
            "expert_opinion": "Strong favorite, tipped by multiple experts",
            "external_odds": "1.30 at competitor books",
            "confidence_notes": "High confidence — consistent data across sources",
        },
        {
            "runner_name": "Ferman Yazar",
            "data_quality": "rich",
            "form_summary": "Consistent placer, 2nd in last start at similar distance",
            "trainer_stats": "H. Aksoy: solid with middle-distance runners",
            "expert_opinion": "Value each-way contender per racing analysts",
            "external_odds": "6.00 elsewhere",
            "confidence_notes": "Good data quality",
        },
        {
            "runner_name": "Hep Birlikte",
            "data_quality": "sparse",
            "form_summary": "Mixed form, recent 2nd suggests improvement",
            "trainer_stats": "Limited trainer data",
            "expert_opinion": "Outsider with potential",
            "external_odds": None,
            "confidence_notes": "Sparse data — treat with caution",
        },
        {
            "runner_name": "Simsekkiran",
            "data_quality": "rich",
            "form_summary": "Won 2 starts ago, consistent performer on turf",
            "trainer_stats": "T. Yildiz: good record at Ankara",
            "expert_opinion": "Each-way chance, dangerous runner",
            "external_odds": "5.50 at competitor",
            "confidence_notes": "Reliable data",
        },
        {
            "runner_name": "Kivilcim Atesi",
            "data_quality": "none",
            "form_summary": "No relevant data found",
            "trainer_stats": "Unknown",
            "expert_opinion": "No coverage",
            "external_odds": None,
            "confidence_notes": "No data — high uncertainty",
        },
    ],
    "overall_notes": "Competitive turf race at Ankara. Emir Ilyas is a clear standout on form. "
    "Ferman Yazar and Simsekkiran offer place value. Rest are speculative.",
}

# Use the cheapest model for all LLM calls in this test
CHEAP_MODEL = "google/gemini-2.0-flash-lite-001"


def _create_test_db(path: str, balance: float = 100.0) -> None:
    """Create a minimal bankroll DB for testing."""
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS stake_bankroll (
            id INTEGER PRIMARY KEY,
            balance_usdt REAL NOT NULL DEFAULT 0,
            stake_pct REAL NOT NULL DEFAULT 0.02,
            updated_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    conn.execute(
        "INSERT OR REPLACE INTO stake_bankroll (id, balance_usdt) VALUES (1, ?)",
        (balance,),
    )
    conn.commit()
    conn.close()


def _setup_env(db_path: str) -> None:
    """Set env vars for cheap models and temp DB, then force-reset settings."""
    os.environ["STAKE_PARSER__MODEL"] = CHEAP_MODEL
    os.environ["STAKE_PARSER__TEMPERATURE"] = "0.0"
    os.environ["STAKE_ANALYSIS__MODEL"] = CHEAP_MODEL
    os.environ["STAKE_ANALYSIS__TEMPERATURE"] = "0.3"
    os.environ["STAKE_ANALYSIS__MAX_TOKENS"] = "4000"
    os.environ["STAKE_DATABASE_PATH"] = db_path
    # Ensure API key is available (may be OPENROUTER_API_KEY or STAKE_OPENROUTER_API_KEY)
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("STAKE_OPENROUTER_API_KEY", "")
    if api_key:
        os.environ["STAKE_OPENROUTER_API_KEY"] = api_key
    # Force-reset the settings singleton so it picks up new env vars
    from services.stake.settings import get_stake_settings
    get_stake_settings.cache_clear()
    # Verify settings are correct
    s = get_stake_settings()
    assert s.openrouter_api_key, "OPENROUTER_API_KEY not set — cannot run e2e test"
    assert s.parser.model == CHEAP_MODEL, f"Parser model mismatch: {s.parser.model}"


def _cleanup_env(db_path: str) -> None:
    """Remove env vars and temp DB."""
    os.unlink(db_path)
    for key in [
        "STAKE_PARSER__MODEL",
        "STAKE_PARSER__TEMPERATURE",
        "STAKE_ANALYSIS__MODEL",
        "STAKE_ANALYSIS__TEMPERATURE",
        "STAKE_ANALYSIS__MAX_TOKENS",
        "STAKE_DATABASE_PATH",
        "STAKE_OPENROUTER_API_KEY",
    ]:
        os.environ.pop(key, None)
    from services.stake.settings import get_stake_settings
    get_stake_settings.cache_clear()


@pytest.mark.asyncio
async def test_full_pipeline_end_to_end():
    """Full pipeline: raw text -> parse -> calc -> skip check -> research (mocked) -> analysis -> sizing -> format.

    Uses gemini-flash-lite for parse + analysis. Research mocked.
    Asserts we get actual recommendation_text at the end.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    _create_test_db(db_path, balance=100.0)

    try:
        _setup_env(db_path)

        from services.stake.pipeline.graph import build_analysis_graph, build_pipeline_graph

        # ── Phase 1: Parse ──
        parse_graph = build_pipeline_graph()
        parse_result = await parse_graph.ainvoke({"raw_input": SAMPLE_RACE_TEXT})

        # Verify parse succeeded
        assert parse_result.get("error") is None, f"Parse error: {parse_result.get('error')}"
        assert parse_result.get("parsed_race") is not None, "No parsed_race in result"
        assert len(parse_result.get("enriched_runners", [])) >= 5, (
            f"Expected >=5 enriched runners, got {len(parse_result.get('enriched_runners', []))}"
        )
        assert parse_result.get("overround_active") is not None, "No overround_active"

        print(f"\n[PARSE] {len(parse_result['enriched_runners'])} runners enriched")
        print(f"  Overround: {parse_result['overround_active']:.4f}")
        print(f"  Margin: {(parse_result['overround_active'] - 1) * 100:.1f}%")

        # ── Phase 2: Analysis pipeline (research mocked) ──
        initial_state = {
            "parsed_race": parse_result["parsed_race"],
            "enriched_runners": parse_result.get("enriched_runners", []),
            "overround_active": parse_result.get("overround_active"),
            "overround_raw": parse_result.get("overround_raw"),
        }

        # Mock research_node to return fake research without API calls
        async def mock_research_node(state):
            return {
                "research_results": MOCK_RESEARCH_OUTPUT,
                "research_error": None,
            }

        with patch(
            "services.stake.pipeline.graph.research_node",
            mock_research_node,
        ):
            analysis_graph = build_analysis_graph()
            result = await analysis_graph.ainvoke(initial_state)

        # ── Assertions ──
        assert result.get("error") is None, f"Pipeline error: {result.get('error')}"

        rec_text = result.get("recommendation_text")
        assert rec_text is not None, "No recommendation_text in result"
        assert len(rec_text) > 20, f"recommendation_text too short: {rec_text!r}"

        print(f"\n[ANALYSIS] Pipeline completed")

        skip_signal = result.get("skip_signal", False)

        if skip_signal:
            print(f"  Result: SKIP — {result.get('skip_reason', '?')}")
            assert "SKIP" in rec_text, "Skip result should contain 'SKIP'"
        else:
            final_bets = result.get("final_bets", [])
            print(f"  Result: {len(final_bets)} bet(s) recommended")
            for bet in final_bets:
                print(
                    f"    #{bet.get('runner_number')} {bet.get('runner_name')} "
                    f"| {bet.get('bet_type')} {bet.get('usdt_amount', 0):.2f} USDT "
                    f"| EV {bet.get('ev', 0):+.3f} | Kelly {bet.get('kelly_pct', 0):.1f}%"
                )

            # If we got bets, verify constraints
            if final_bets:
                win_count = sum(1 for b in final_bets if b.get("bet_type") == "win")
                assert win_count <= 2, f"Too many win bets: {win_count}"

                for bet in final_bets:
                    amount = bet.get("usdt_amount", 0)
                    assert amount >= 1.0, f"Bet below minimum 1 USDT: {amount}"
                    assert amount <= 3.0, f"Bet exceeds 3% cap: {amount}"

                total = sum(b.get("usdt_amount", 0) for b in final_bets)
                assert total <= 5.0, f"Total exposure exceeds 5%: {total}"

                print(f"  Total exposure: {total:.2f} USDT ({total:.1f}% of bankroll)")

            analysis_result = result.get("analysis_result")
            assert analysis_result is not None, "No analysis_result"
            assert "recommendations" in analysis_result, "No recommendations in analysis"

        print(f"\n[OUTPUT] Recommendation ({len(rec_text)} chars):")
        print(f"  {rec_text[:500]}")
        print("\nE2E PIPELINE TEST PASSED")

    finally:
        _cleanup_env(db_path)


@pytest.mark.asyncio
async def test_pipeline_skip_on_high_margin():
    """Test Tier 1 skip: when overround is too high, pipeline skips without LLM calls."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    _create_test_db(db_path, balance=100.0)

    try:
        os.environ["STAKE_DATABASE_PATH"] = db_path
        from services.stake.settings import get_stake_settings
        get_stake_settings.cache_clear()

        from services.stake.pipeline.graph import build_analysis_graph

        # State with very high overround (25% margin — should trigger skip)
        initial_state = {
            "parsed_race": None,
            "enriched_runners": [
                {"number": 1, "name": "Horse A", "decimal_odds": 2.0, "implied_prob": 0.5, "status": "active"},
                {"number": 2, "name": "Horse B", "decimal_odds": 2.0, "implied_prob": 0.5, "status": "active"},
            ],
            "overround_active": 1.25,  # 25% margin > 15% threshold
        }

        # Research and analysis should NOT be called on skip
        async def fail_research(state):
            raise AssertionError("research_node should not be called on skip")

        with patch("services.stake.pipeline.graph.research_node", fail_research):
            graph = build_analysis_graph()
            result = await graph.ainvoke(initial_state)

        assert result.get("skip_signal") is True
        assert result.get("skip_tier") == 1
        assert "recommendation_text" in result
        assert "SKIP" in result["recommendation_text"]

        print(f"\nTier 1 skip test passed: {result['skip_reason']}")

    finally:
        os.unlink(db_path)
        os.environ.pop("STAKE_DATABASE_PATH", None)
        from services.stake.settings import get_stake_settings
        get_stake_settings.cache_clear()

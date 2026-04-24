import pytest

from services.stake.pipeline.nodes.decision_maker import make_decision_maker_node


@pytest.mark.asyncio
async def test_empty_proposed_slips_skips_tier2():
    node = make_decision_maker_node()
    out = await node({"proposed_bet_slips": []})
    assert out["skip_signal"] is True
    assert out["skip_tier"] == 2
    assert out["decision_rationale"].startswith("phase1_no_viable")
    assert out["skip_reason"] == "no_intents_from_analyst"


@pytest.mark.asyncio
async def test_missing_proposed_slips_field_skips():
    # State without the key at all — treat as empty
    node = make_decision_maker_node()
    out = await node({})
    assert out["skip_signal"] is True
    assert out["skip_tier"] == 2


@pytest.mark.asyncio
async def test_all_zero_stakes_skips_tier2_with_caps_in_rationale():
    node = make_decision_maker_node()
    slip_a = {"stake": 0.0, "caps_applied": ["edge_below_threshold"]}
    slip_b = {"stake": 0.0, "caps_applied": ["per_bet_cap", "edge_below_threshold"]}
    out = await node({"proposed_bet_slips": [slip_a, slip_b]})
    assert out["skip_signal"] is True
    assert out["skip_tier"] == 2
    assert "edge_below_threshold" in out["decision_rationale"]
    assert out["skip_reason"] == "all_stakes_zero"


@pytest.mark.asyncio
async def test_all_zero_stakes_dedup_and_sort_caps_in_rationale():
    node = make_decision_maker_node()
    slip_a = {"stake": 0.0, "caps_applied": ["z", "a"]}
    slip_b = {"stake": 0.0, "caps_applied": ["a", "m"]}
    out = await node({"proposed_bet_slips": [slip_a, slip_b]})
    assert out["decision_rationale"] == "phase1_zero_stake:a,m,z"


@pytest.mark.asyncio
async def test_any_positive_stake_emits_auto_accept_with_only_positives():
    node = make_decision_maker_node()
    s1 = {"stake": 0.0, "caps_applied": ["edge_below_threshold"]}
    s2 = {"stake": 2.0, "caps_applied": []}
    s3 = {"stake": 0.5, "caps_applied": []}
    out = await node({"proposed_bet_slips": [s1, s2, s3]})
    assert out.get("skip_signal") is not True
    assert out["decision_rationale"] == "phase1_auto_accept"
    assert len(out["final_proposed_slips"]) == 2
    stakes = {s["stake"] for s in out["final_proposed_slips"]}
    assert stakes == {2.0, 0.5}


@pytest.mark.asyncio
async def test_caps_applied_missing_is_handled():
    """A slip without 'caps_applied' shouldn't break rationale building."""
    node = make_decision_maker_node()
    out = await node({"proposed_bet_slips": [{"stake": 0.0}, {"stake": 0.0}]})
    assert out["skip_signal"] is True
    assert out["decision_rationale"] == "phase1_zero_stake:"


@pytest.mark.asyncio
async def test_stake_as_int_still_counted_as_positive():
    # defensive — make sure we parse float correctly
    node = make_decision_maker_node()
    out = await node({"proposed_bet_slips": [{"stake": 1, "caps_applied": []}]})
    assert out.get("skip_signal") is not True
    assert len(out["final_proposed_slips"]) == 1

import pytest
from unittest.mock import AsyncMock

from services.stake.contracts import BetIntent, LLMAdjustment
from services.stake.pipeline.nodes.analyst import (
    _postprocess_llm_output, make_analyst_node,
)


def test_postprocess_rejects_probability_field():
    raw = {
        "intents": [
            {"market": "win", "selections": [3], "confidence": 0.6,
             "rationale_id": "r1", "edge_source": "p_model",
             "probability": 0.42},  # hallucinated
        ],
        "adjustments": [],
    }
    with pytest.raises(ValueError):
        _postprocess_llm_output(raw, paper_mode=True)


def test_postprocess_rejects_p_raw_field():
    raw = {
        "intents": [
            {"market": "win", "selections": [3], "confidence": 0.6,
             "rationale_id": "r1", "edge_source": "p_model",
             "p_raw": 0.5},
        ],
        "adjustments": [],
    }
    with pytest.raises(ValueError):
        _postprocess_llm_output(raw, paper_mode=True)


def test_postprocess_rejects_p_calibrated_field():
    raw = {
        "intents": [
            {"market": "win", "selections": [3], "confidence": 0.6,
             "rationale_id": "r1", "edge_source": "p_model",
             "p_calibrated": 0.5},
        ],
        "adjustments": [],
    }
    with pytest.raises(ValueError):
        _postprocess_llm_output(raw, paper_mode=True)


def test_postprocess_accepts_valid_shape():
    raw = {
        "intents": [
            {"market": "win", "selections": [3], "confidence": 0.6,
             "rationale_id": "r1", "edge_source": "p_model"},
        ],
        "adjustments": [
            {"target_horse_no": 3, "direction": "up", "magnitude": "small",
             "rationale": "form improving"},
        ],
    }
    intents, adjustments = _postprocess_llm_output(raw, paper_mode=True)
    assert len(intents) == 1
    assert intents[0].edge_source == "paper_only"  # rewritten in paper mode
    assert isinstance(intents[0], BetIntent)
    assert len(adjustments) == 1
    assert isinstance(adjustments[0], LLMAdjustment)


def test_paper_mode_rewrites_edge_source_on_all_intents():
    raw = {
        "intents": [
            {"market": "win", "selections": [3], "confidence": 0.6,
             "rationale_id": "r1", "edge_source": "p_model"},
            {"market": "win", "selections": [5], "confidence": 0.4,
             "rationale_id": "r2", "edge_source": "reflection:L42"},
            {"market": "place", "selections": [2], "confidence": 0.5,
             "rationale_id": "r3", "edge_source": "market_inefficiency"},
        ],
        "adjustments": [],
    }
    intents, _ = _postprocess_llm_output(raw, paper_mode=True)
    assert all(i.edge_source == "paper_only" for i in intents)


def test_non_paper_mode_preserves_edge_source():
    raw = {
        "intents": [
            {"market": "win", "selections": [3], "confidence": 0.6,
             "rationale_id": "r1", "edge_source": "p_model"},
        ],
        "adjustments": [],
    }
    intents, _ = _postprocess_llm_output(raw, paper_mode=False)
    assert intents[0].edge_source == "p_model"


def test_postprocess_empty_inputs_ok():
    intents, adjustments = _postprocess_llm_output({}, paper_mode=True)
    assert intents == []
    assert adjustments == []
    intents, adjustments = _postprocess_llm_output(
        {"intents": None, "adjustments": None}, paper_mode=True
    )
    assert intents == []
    assert adjustments == []


def test_postprocess_invalid_intent_raises():
    raw = {
        "intents": [
            {"market": "bogus_market", "selections": [3], "confidence": 0.6,
             "rationale_id": "r1", "edge_source": "p_model"},
        ],
        "adjustments": [],
    }
    with pytest.raises(Exception):  # pydantic.ValidationError
        _postprocess_llm_output(raw, paper_mode=True)


@pytest.mark.asyncio
async def test_node_invokes_llm_and_emits_dumped_dicts():
    llm_call = AsyncMock(return_value={
        "intents": [
            {"market": "win", "selections": [3], "confidence": 0.6,
             "rationale_id": "r1", "edge_source": "p_model"},
        ],
        "adjustments": [
            {"target_horse_no": 3, "direction": "up", "magnitude": "small",
             "rationale": "form"},
        ],
    })
    node = make_analyst_node(llm_call=llm_call, paper_mode=True)
    out = await node({
        "parsed_race": {"track": "T"},
        "enriched_runners": [{"number": 3, "win_odds": 2.0}],
        "research_results": {},
        "probabilities": [],
    })
    # LLM call was awaited once with the payload
    llm_call.assert_awaited_once()
    payload = llm_call.await_args.args[0]
    assert "race" in payload and "runners" in payload
    # BetIntent / LLMAdjustment are dumped
    assert isinstance(out["bet_intents"], list)
    assert out["bet_intents"][0]["edge_source"] == "paper_only"
    assert isinstance(out["llm_adjustments"], list)
    assert out["llm_adjustments"][0]["direction"] == "up"


@pytest.mark.asyncio
async def test_node_propagates_i2_violation():
    llm_call = AsyncMock(return_value={
        "intents": [
            {"market": "win", "selections": [3], "confidence": 0.6,
             "rationale_id": "r", "edge_source": "p_model",
             "probability": 0.42},
        ],
        "adjustments": [],
    })
    node = make_analyst_node(llm_call=llm_call, paper_mode=True)
    with pytest.raises(ValueError):
        await node({})

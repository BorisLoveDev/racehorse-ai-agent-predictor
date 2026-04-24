import pytest

from services.stake.telegram_bridge.resume_router import (
    encode_callback, decode_callback, build_resume_from_callback,
)


def test_gate_callback_within_64_bytes():
    data = encode_callback(kind="gate", decision="continue", race_id="R1234567890")
    assert len(data.encode("utf-8")) <= 64
    assert data.startswith("sg:continue:")


def test_approval_callback_with_slip_idx():
    data = encode_callback(kind="approval", decision="accept", race_id="R1", slip_idx=0)
    assert data.startswith("sa:accept:")
    assert data.endswith(":0")
    assert len(data.encode("utf-8")) <= 64


def test_result_callback():
    data = encode_callback(kind="result", decision="pending", race_id="R1")
    assert data.startswith("sr:pending:")


def test_unknown_kind_rejected():
    with pytest.raises(KeyError):
        encode_callback(kind="bogus", decision="x", race_id="R1")


def test_roundtrip_gate():
    data = encode_callback(kind="gate", decision="skip", race_id="R1")
    assert decode_callback(data) == {
        "kind": "gate", "decision": "skip", "race_id": "R1", "slip_idx": None,
    }


def test_roundtrip_approval():
    data = encode_callback(kind="approval", decision="edit", race_id="R1", slip_idx=2)
    assert decode_callback(data) == {
        "kind": "approval", "decision": "edit", "race_id": "R1", "slip_idx": 2,
    }


def test_decode_unknown_prefix_raises():
    with pytest.raises(ValueError):
        decode_callback("xx:bogus:R1")


def test_build_resume_gate_skip():
    cb = decode_callback(encode_callback(kind="gate", decision="skip", race_id="R1"))
    assert build_resume_from_callback(cb) == {"decision": "skip"}


def test_build_resume_approval_accept_with_details():
    cb = decode_callback(encode_callback(
        kind="approval", decision="accept", race_id="R1", slip_idx=1,
    ))
    r = build_resume_from_callback(cb)
    assert r["decision"] == "accept"
    assert r["details"] == {"slip_idx": 1}


def test_build_resume_no_slip_idx_no_details():
    cb = decode_callback(encode_callback(
        kind="approval", decision="kill", race_id="R1",
    ))
    r = build_resume_from_callback(cb)
    assert r == {"decision": "kill"}


def test_long_race_id_fails_fast():
    long_race = "R" * 64
    with pytest.raises(ValueError):
        encode_callback(kind="approval", decision="accept",
                        race_id=long_race, slip_idx=99)

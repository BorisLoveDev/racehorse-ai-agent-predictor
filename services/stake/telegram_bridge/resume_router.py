"""Encode/decode Telegram callback_data within the 64-byte limit.

Prefixes (short, per CLAUDE.md):
  sg: = Stake Gate        (sg:<decision>:<race_id>)
  sa: = Stake Approval    (sa:<decision>:<race_id>:<slip_idx>)
  sr: = Stake Result      (sr:<decision>:<race_id>)
"""
from typing import Optional


_KIND_PREFIX = {"gate": "sg", "approval": "sa", "result": "sr"}
_PREFIX_KIND = {v: k for k, v in _KIND_PREFIX.items()}


def encode_callback(
    *, kind: str, decision: str, race_id: str, slip_idx: Optional[int] = None,
) -> str:
    prefix = _KIND_PREFIX[kind]  # raises KeyError for unknown kind
    parts = [prefix, decision, race_id]
    if slip_idx is not None:
        parts.append(str(slip_idx))
    data = ":".join(parts)
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"callback_data exceeds 64 bytes ({len(data)}): {data}")
    return data


def decode_callback(data: str) -> dict:
    parts = data.split(":")
    prefix = parts[0]
    if prefix not in _PREFIX_KIND:
        raise ValueError(f"unknown callback prefix: {prefix}")
    kind = _PREFIX_KIND[prefix]
    decision = parts[1] if len(parts) > 1 else ""
    race_id = parts[2] if len(parts) > 2 else ""
    slip_idx = int(parts[3]) if len(parts) > 3 else None
    return {"kind": kind, "decision": decision, "race_id": race_id, "slip_idx": slip_idx}


def build_resume_from_callback(cb: dict) -> dict:
    out: dict = {"decision": cb["decision"]}
    if cb.get("slip_idx") is not None:
        out["details"] = {"slip_idx": cb["slip_idx"]}
    return out

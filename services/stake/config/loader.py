import os
from pathlib import Path
from typing import Optional

import yaml

from services.stake.config.models import PhaseOneSettings
from services.stake.invariants.rules import InvariantViolation


def load_config(path: Optional[Path] = None) -> PhaseOneSettings:
    data: dict = {}
    if path and Path(path).exists():
        data = yaml.safe_load(Path(path).read_text()) or {}
    else:
        env_mode = os.environ.get("STAKE_MODE", "paper")
        data = {"mode": env_mode}
    settings = PhaseOneSettings(**data)
    if settings.mode == "live":
        raise InvariantViolation("I1", "live mode is not permitted in Phase 1 (paper-only)")
    return settings

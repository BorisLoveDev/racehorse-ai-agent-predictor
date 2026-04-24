import os
from pathlib import Path
from typing import Optional, Union

import yaml

from services.stake.config.models import PhaseOneSettings
from services.stake.invariants.rules import InvariantViolation


class ConfigLoadError(RuntimeError):
    """Raised when config file exists but cannot be parsed or validated."""


def load_config(path: Optional[Union[Path, str]] = None) -> PhaseOneSettings:
    """Load PhaseOneSettings from YAML, falling back to env defaults.

    - If `path` is provided and the file exists, parse the YAML.
    - If `path` is None OR the file does not exist, fall back to env-based
      defaults (currently only STAKE_MODE).
    - If parsed mode is "live", raise InvariantViolation("I1", ...) —
      Phase 1 is paper-only.
    - Malformed YAML or schema violations are wrapped in ConfigLoadError.
    """
    data: dict
    if path is not None and Path(path).exists():
        try:
            raw = Path(path).read_text()
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ConfigLoadError(f"Malformed YAML at {path}: {e}") from e
        data = parsed or {}
    else:
        env_mode = os.environ.get("STAKE_MODE", "paper")
        data = {"mode": env_mode}
    try:
        settings = PhaseOneSettings(**data)
    except Exception as e:  # pydantic.ValidationError and similar
        # Invariant I1 must still fire BEFORE generic ConfigLoadError so the
        # rule_id is preserved. Pydantic's Literal validation will reject
        # mode="bogus" before we check mode=="live", so this branch is only
        # for schema/shape errors, not for I1.
        raise ConfigLoadError(f"Invalid config at {path}: {e}") from e
    if settings.mode == "live":
        raise InvariantViolation("I1", "live mode is not permitted in Phase 1 (paper-only)")
    return settings

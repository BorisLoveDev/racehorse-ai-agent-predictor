"""Post-parse validator enforcing invariant I3.

Invariant I3: every Phase 1 must-have field in ParsedRace must have a non-empty
raw_excerpt quoted from the input. Fields without an excerpt are added to
race.missing_fields so interrupt_gate (Task 10) can show the user a remediation
prompt.

The must-have list below is adapted to the existing ParsedRace schema. Task
Phase 2 (VLM) will add country, post_time, grade to ParsedRace proper and
extend this list accordingly.
"""
from dataclasses import dataclass

from services.stake.parser.models import ParsedRace


MUST_HAVE_FIELDS: tuple[str, ...] = (
    "track", "region", "race_number", "date", "distance", "snapshot_ts",
)


@dataclass
class ExcerptValidationResult:
    missing: list[str]

    @property
    def ok(self) -> bool:
        return not self.missing


def validate_excerpts(race: ParsedRace) -> ExcerptValidationResult:
    """Return which must-have fields lack a non-empty raw_excerpt.

    Also mutates race.missing_fields to include flagged fields (union-preserving;
    pre-existing flags are kept).
    """
    excerpts = race.raw_excerpts or {}
    missing: list[str] = []
    for field in MUST_HAVE_FIELDS:
        value = excerpts.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    existing = list(race.missing_fields or [])
    race.missing_fields = sorted(set(existing + missing))
    return ExcerptValidationResult(missing=missing)

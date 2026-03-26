"""
Append-only JSONL audit logger for the Stake Advisor pipeline.

Per D-27: every pipeline run logs to an append-only JSONL file.
Per D-28: audit entry includes raw input, parsed output, user confirmation.

Each line is a valid JSON object with timestamp, event name, and event-specific data.
The log is never truncated — reads are not supported; only appends.

Events logged:
    pipeline_start       — raw_input (first 500 chars)
    parse_complete       — parsed_race dict, overround values, ambiguous_fields
    parse_error          — error message
    user_confirmed       — empty data dict (user pressed Confirm)
    user_rejected        — empty data dict (user pressed Cancel)
    clarification_asked  — ambiguous_fields list and question strings
    clarification_received — user's clarification response text
    bankroll_set         — balance amount and source ("paste_detected" or "manual_input")
    recommendation       — final_bets, skip_signal, skip_reason, skip_tier, analysis_summary,
                           overround_active (D-16: recommendation data for this run)
    analysis_error       — error message if Phase 2 analysis pipeline fails

Exported:
    AuditLogger
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from services.stake.settings import get_stake_settings


class AuditLogger:
    """Append-only JSONL audit logger.

    Writes one JSON line per event to the configured audit log path.
    Creates parent directories on instantiation if they don't exist.

    Args:
        log_path: Path to the JSONL audit log file. If None, uses
                  the path from StakeSettings.audit.log_path.
    """

    def __init__(self, log_path: Optional[str] = None) -> None:
        settings = get_stake_settings()
        self.log_path = log_path or settings.audit.log_path
        # Ensure parent directory exists
        parent = os.path.dirname(self.log_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def log_entry(self, event: str, data: dict[str, Any]) -> None:
        """Append one JSON line to the audit log.

        Args:
            event: Event name string (e.g., "pipeline_start", "user_confirmed").
            data: Event-specific data dict. Values are serialized with str() fallback
                  for non-JSON-serializable types (e.g., Pydantic models, datetimes).
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

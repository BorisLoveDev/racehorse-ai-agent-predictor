"""
FSM state definitions for the Stake Advisor Bot pipeline.

States cover the full pipeline flow from raw paste input through
parsing, confirmation, bankroll management, and processing.
"""

from aiogram.fsm.state import State, StatesGroup


class PipelineStates(StatesGroup):
    """FSM states for the Stake Advisor pipeline.

    Flow:
        idle -> parsing -> awaiting_parse_confirm -> [awaiting_clarification |
            awaiting_bankroll_confirm | awaiting_bankroll_input] -> processing
    """

    idle = State()                        # Waiting for paste input
    parsing = State()                     # LLM parsing in progress
    awaiting_parse_confirm = State()      # User must confirm parsed race
    awaiting_clarification = State()      # PIPELINE-02: ambiguous data, asking user for clarification
    awaiting_bankroll_confirm = State()   # Balance found in paste, confirm
    awaiting_bankroll_input = State()     # No balance anywhere, user must enter
    awaiting_skip_confirm = State()       # High margin detected, user decides skip or continue
    processing = State()                  # Pipeline running (future phases)

    # Phase 3: result tracking states
    awaiting_placed_tracked = State()       # After recommendation — Placed/Tracked choice
    awaiting_result = State()               # Waiting for result text from user
    awaiting_result_clarification = State() # Ambiguous result — asking user for clarification
    confirming_result = State()             # User confirms parsed result before evaluation

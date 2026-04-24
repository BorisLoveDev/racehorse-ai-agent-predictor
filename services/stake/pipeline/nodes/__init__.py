from services.stake.bankroll.repository import BankrollRepository  # noqa: F401
from services.stake.pipeline.nodes.interrupt_gate import (
    classify_overround, make_interrupt_gate_node,
)
# Re-export legacy (pre-Phase-1-rewrite) node functions so existing imports
# like `from services.stake.pipeline.nodes import sizing_node` keep working
# now that `nodes.py` has become the `nodes/` package. `BankrollRepository`
# is re-exported above from its real home so that tests which patch
# `services.stake.pipeline.nodes.BankrollRepository` continue to intercept
# the calls inside `legacy.py` (which resolves the class via this package
# at call time — see `legacy._bankroll_repo_cls`).
from services.stake.pipeline.nodes.legacy import (
    _build_analysis_prompt,
    _build_lessons_block,
    analysis_node,
    calc_node,
    drawdown_check_node,
    format_recommendation_node,
    parse_node,
    pre_skip_check_node,
    sizing_node,
)

__all__ = [
    "classify_overround",
    "make_interrupt_gate_node",
    "analysis_node",
    "calc_node",
    "drawdown_check_node",
    "format_recommendation_node",
    "parse_node",
    "pre_skip_check_node",
    "sizing_node",
    "_build_lessons_block",
    "_build_analysis_prompt",
]

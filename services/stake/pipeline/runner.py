"""Helper for running or resuming the race super-graph.

Usage from the Telegram bridge (Task 20):

    result = await run_or_resume(graph, thread_id="race:R1:42",
                                 initial_state={"race_id": "R1", ...})
    # result contains '__interrupt__' if the graph paused.
    # When the user clicks a button, pass resume_value={"decision": "..."}:
    result = await run_or_resume(graph, thread_id="race:R1:42",
                                 resume_value={"decision": "skip"})
"""
from typing import Any, Optional

from langgraph.types import Command


async def run_or_resume(
    graph,
    *,
    thread_id: str,
    initial_state: Optional[dict] = None,
    resume_value: Optional[Any] = None,
) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    if resume_value is not None:
        return await graph.ainvoke(Command(resume=resume_value), config=config)
    return await graph.ainvoke(initial_state or {}, config=config)

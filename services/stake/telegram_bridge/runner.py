"""TelegramGraphRunner — owns compiled graph + routes interrupts.

Flow:
  1. start_race(user_id, race_id, raw_text): builds thread_id, invokes graph
     with initial state. Handles terminal state (skip) or interrupt (card).
  2. on_callback(user_id, cb): resumes graph with Command(resume={decision, ...}).
  3. on_result_positions(user_id, race_id, positions): resumes from result_recorder.

Per-race AuditTraceRecorder is instantiated on start_race and cleaned up on
terminal state. `recorder_provider(race_id)` is passed into the graph compile
so reflection_update can finalise and persist the trace.

cancel_race / drawdown fields are minimal in Phase 1 (Task 21 extends these).
"""
from datetime import datetime, timezone
from typing import Optional

from services.stake.audit.trace import AuditTraceRecorder
from services.stake.pipeline.runner import run_or_resume


class TelegramGraphRunner:
    def __init__(
        self, graph, *,
        send_card,
        send_skip,
        send_result_request,
    ):
        self.graph = graph
        self.send_card = send_card
        self.send_skip = send_skip
        self.send_result_request = send_result_request
        self._recorders: dict[str, AuditTraceRecorder] = {}
        self._drawdown_locked: bool = False
        self.expected_unlock_token: Optional[str] = None

    # --- audit recorder integration ---

    @property
    def active_races(self) -> set:
        return set(self._recorders.keys())

    def recorder_provider(self, race_id: str) -> Optional[AuditTraceRecorder]:
        return self._recorders.get(race_id)

    # --- graph drivers ---

    def _thread_id(self, user_id: int, race_id: str) -> str:
        return f"race:{race_id}:{user_id}"

    async def start_race(self, *, user_id: int, race_id: str, raw_text: str) -> None:
        self._recorders[race_id] = AuditTraceRecorder(
            race_id=race_id,
            thread_id=self._thread_id(user_id, race_id),
            started_at=datetime.now(timezone.utc),
        )
        result = await run_or_resume(
            self.graph,
            thread_id=self._thread_id(user_id, race_id),
            initial_state={
                "race_id": race_id, "user_id": user_id,
                "raw_input": raw_text, "source_type": "text",
            },
        )
        await self._dispatch(user_id=user_id, race_id=race_id, result=result)

    async def on_callback(self, *, user_id: int, cb: dict) -> None:
        race_id = cb["race_id"]
        resume: dict = {"decision": cb["decision"]}
        if cb.get("slip_idx") is not None:
            resume["details"] = {"slip_idx": cb["slip_idx"]}
        result = await run_or_resume(
            self.graph,
            thread_id=self._thread_id(user_id, race_id),
            resume_value=resume,
        )
        await self._dispatch(user_id=user_id, race_id=race_id, result=result)

    async def on_result_positions(
        self, *, user_id: int, race_id: str, positions: dict,
    ) -> None:
        result = await run_or_resume(
            self.graph,
            thread_id=self._thread_id(user_id, race_id),
            resume_value={"positions": positions},
        )
        await self._dispatch(user_id=user_id, race_id=race_id, result=result)

    async def _dispatch(self, *, user_id: int, race_id: str, result: dict) -> None:
        interrupts = result.get("__interrupt__") or []
        if not interrupts:
            # Terminal state — recorder is no longer needed.
            self._recorders.pop(race_id, None)
            if result.get("skip_signal"):
                await self.send_skip(
                    user_id=user_id, race_id=race_id,
                    reason=result.get("skip_reason") or "",
                )
            return
        for intr in interrupts:
            payload = intr.value if hasattr(intr, "value") else intr
            await self.send_card(user_id=user_id, payload=payload)

    # --- drawdown controls (Task 21 wires commands) ---

    @property
    def drawdown_locked(self) -> bool:
        return self._drawdown_locked

    def trip_drawdown(self, *, token: str) -> None:
        self._drawdown_locked = True
        self.expected_unlock_token = token

    def unlock(self) -> None:
        self._drawdown_locked = False
        self.expected_unlock_token = None

    async def cancel_race(self, race_id: str) -> None:
        """Phase-1 best-effort kill: drop the recorder so new runs can't bind it.

        Full cancel (resuming the current interrupt with synthetic kill) is
        deferred to a Phase 4 refactor; for Phase 1 paper mode this is OK
        because nothing real is at stake.
        """
        self._recorders.pop(race_id, None)

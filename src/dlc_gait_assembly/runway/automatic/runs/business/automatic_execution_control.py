"""Coordinate cancellation and explicit review decisions independently of Qt."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event

from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import (
    AutomaticReviewDecision,
    StageReview,
)
from dlc_gait_assembly.runway.automatic.review.business.automatic_review_rules import validate_review_decision


class AutomaticRunCancelled(Exception):
    """The user cancelled execution or declined the current review."""


@dataclass(frozen=True)
class AutomaticExecutionEvents:
    """Observer callbacks implemented by a GUI worker or another client."""

    stage_started: Callable[[int, str], None]
    stage_progress: Callable[[int, int, int, str], None]
    stage_skipped: Callable[[int, str], None]
    log_message: Callable[[str], None]
    review_requested: Callable[[int, StageReview], None]


class AutomaticExecutionControl:
    """A thread-safe review gate; cancellation also releases a waiting review."""

    def __init__(self):
        self._cancelled = Event()
        self._review_released = Event()
        self._decision = AutomaticReviewDecision.REJECT
        self.correction = None
        self.waiting_for_review = False
        self.current_stage = -1

    def request_cancel(self) -> None:
        self._cancelled.set()
        self._review_released.set()

    def decide_review(self, decision: AutomaticReviewDecision, correction=None) -> None:
        self.correction = correction
        self._decision = decision
        self._review_released.set()

    def check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise AutomaticRunCancelled()

    def review(self, request: StageReview, notify: Callable[[int, StageReview], None]) -> AutomaticReviewDecision:
        self._decision = AutomaticReviewDecision.REJECT
        self._review_released.clear()
        self.waiting_for_review = True
        try:
            self.check_cancelled()
            notify(int(request.stage), request)
            self._review_released.wait()
            self.check_cancelled()
            decision = validate_review_decision(request, self._decision)
            if decision in (AutomaticReviewDecision.REJECT, AutomaticReviewDecision.CANCEL):
                raise AutomaticRunCancelled()
            return decision
        finally:
            self.waiting_for_review = False

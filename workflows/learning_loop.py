"""
Learning loop state machine with guard conditions.

Branching transitions:
    QA ----------> DIAGNOSIS
                    |
            correct |     | wrong
                    v     v
               FEYNMAN   SOCRATIC
                  |         |
         score<60 |         | (unconditional)
                  v         v
              SOCRATIC   FEYNMAN
                  |         |
                  |    score>=60
                  |         v
                  +---> RECOMMENDATION ---> COMPLETED
                            |
                            +-------------> QA (restart)

Backend enforcement:
    Even if the frontend sends requests out of order, the state machine
    rejects invalid transitions. The machine is the single authority on
    what is allowed at each stage.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable

from workflows.state_machine import StateMachine, Transition, InvalidTransitionError
from schemas.common import LearningStage


# ================================================================
# Guard condition names
# ================================================================

class Guard(StrEnum):
    """Named guard conditions for learning-loop transitions."""
    DIAGNOSIS_PASSED = "diagnosis_passed"
    DIAGNOSIS_FAILED = "diagnosis_failed"
    FEYNMAN_PASS = "feynman_pass"
    FEYNMAN_WEAK = "feynman_weak"


# ================================================================
# Guard predicates (pure functions of context dict)
# ================================================================

def _ctx_diagnosis_passed(ctx: dict) -> bool:
    return ctx.get("diagnosis_is_correct") is True


def _ctx_diagnosis_failed(ctx: dict) -> bool:
    return ctx.get("diagnosis_is_correct") is False


def _ctx_feynman_pass(ctx: dict) -> bool:
    score = ctx.get("feynman_total_score")
    if score is None:
        return False
    threshold = ctx.get("feynman_pass_threshold", 60)  # 60/78 ~ 77%
    return score >= threshold


def _ctx_feynman_weak(ctx: dict) -> bool:
    score = ctx.get("feynman_total_score")
    if score is None:
        return False
    threshold = ctx.get("feynman_pass_threshold", 60)
    return score < threshold


GUARD_PREDICATES: dict[Guard, Callable[[dict], bool]] = {
    Guard.DIAGNOSIS_PASSED: _ctx_diagnosis_passed,
    Guard.DIAGNOSIS_FAILED: _ctx_diagnosis_failed,
    Guard.FEYNMAN_PASS: _ctx_feynman_pass,
    Guard.FEYNMAN_WEAK: _ctx_feynman_weak,
}


# ================================================================
# Transition table
#   {from_stage: {to_stage: guard_name | None}}
#   None = unconditional transition
# ================================================================

TRANSITION_TABLE: dict[LearningStage, dict[LearningStage, Guard | None]] = {
    LearningStage.QA: {
        LearningStage.DIAGNOSIS: None,
    },

    LearningStage.DIAGNOSIS: {
        LearningStage.SOCRATIC: Guard.DIAGNOSIS_FAILED,
        LearningStage.FEYNMAN: Guard.DIAGNOSIS_PASSED,
    },

    LearningStage.SOCRATIC: {
        LearningStage.FEYNMAN: None,
    },

    LearningStage.FEYNMAN: {
        LearningStage.SOCRATIC: Guard.FEYNMAN_WEAK,
        LearningStage.RECOMMENDATION: Guard.FEYNMAN_PASS,
    },

    LearningStage.RECOMMENDATION: {
        LearningStage.COMPLETED: None,
        LearningStage.QA: None,              # Start a fresh round
    },

    # Terminal state — only allow restart
    LearningStage.COMPLETED: {
        LearningStage.QA: None,
    },
}

# Legacy alias
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    from_stage.value: [to.value for to in targets]
    for from_stage, targets in TRANSITION_TABLE.items()
}


# ================================================================
# Transition descriptions (for UI and debugging)
# ================================================================

TRANSITION_LABELS: dict[tuple[str, str], str] = {
    ("qa", "diagnosis"):             "Start self-test",
    ("diagnosis", "socratic"):       "Answer wrong — begin guided tutoring",
    ("diagnosis", "feynman"):        "Answer correct — skip to explanation",
    ("socratic", "feynman"):         "Tutoring complete — explain in your own words",
    ("feynman", "socratic"):         "Explanation weak — return to guided tutoring",
    ("feynman", "recommendation"):   "Explanation solid — generate learning path",
    ("recommendation", "completed"): "Learning path ready",
    ("recommendation", "qa"):        "Start a new topic",
    ("completed", "qa"):             "Start a new topic",
}


# ================================================================
# Factory
# ================================================================

def _build_transitions() -> list[Transition]:
    """Build Transition objects from TRANSITION_TABLE + GUARD_PREDICATES."""
    result: list[Transition] = []
    for from_stage, targets in TRANSITION_TABLE.items():
        for to_stage, guard in targets.items():
            key = (from_stage.value, to_stage.value)
            result.append(Transition(
                from_state=from_stage.value,
                to_state=to_stage.value,
                name=TRANSITION_LABELS.get(key, ""),
                guard=guard.value if guard else None,
                condition=GUARD_PREDICATES.get(guard) if guard else None,
            ))
    return result


def create_learning_loop_machine(user_id: str = "student_test_01") -> StateMachine:
    """Create a fresh state machine at the QA stage."""
    return StateMachine(
        initial_state=LearningStage.QA.value,
        transitions=_build_transitions(),
        context={
            "user_id": user_id,
            "current_knowledge_id": "K001",
            "current_question_id": "Q001",
            "current_chain_id": "C001",
            "current_socratic_id": "S001",
            "current_feynman_id": "F001",
            "feynman_pass_threshold": 60,
        },
    )


# ================================================================
# TransitionResult
# ================================================================

@dataclass
class TransitionResult:
    """Result of a state transition, returned to the caller."""
    from_stage: LearningStage
    to_stage: LearningStage
    label: str = ""
    context: dict = field(default_factory=dict)
    available_next: list[str] = field(default_factory=list)
    blocked_next: list[dict] = field(default_factory=list)


# ================================================================
# LearningLoopMachine — type-safe domain wrapper
# ================================================================

class LearningLoopMachine:
    """
    Domain-specific state machine for the 5-stage learning loop.

    Streamlit usage:
        machine = LearningLoopMachine.from_session_dict(st.session_state)
        if not machine.can_advance_to(LearningStage.FEYNMAN):
            st.error("Cannot skip stages")
        result = machine.complete_diagnosis(is_correct=True)
        st.session_state.update(result.context)

    FastAPI usage (future):
        machine = LearningLoopMachine.from_session(session)
        result = machine.complete_diagnosis(is_correct=True)
        session = apply_result(session, result)
        await db.save(session)
        return result
    """

    def __init__(self, sm: StateMachine):
        self._sm = sm

    # ---- factories ----

    @classmethod
    def new(cls, user_id: str = "student_test_01") -> "LearningLoopMachine":
        return cls(create_learning_loop_machine(user_id))

    @classmethod
    def from_context(cls, *, current_stage: str = "qa", **context) -> "LearningLoopMachine":
        """Restore from explicit stage + context dict."""
        sm = create_learning_loop_machine(context.get("user_id", "student_test_01"))
        sm.current_state = current_stage
        sm.context.update(context)
        return cls(sm)

    @classmethod
    def from_session(cls, session) -> "LearningLoopMachine":
        """
        Build from a LearningSession Pydantic model.
        This is the canonical way to construct the machine from stored state.
        """
        from schemas.learning_session import LearningSession
        if isinstance(session, LearningSession):
            d = session.model_dump()
        elif isinstance(session, dict):
            d = session
        else:
            raise TypeError(f"Expected LearningSession or dict, got {type(session)}")

        sm = create_learning_loop_machine(d.get("user_id") or "student_test_01")
        sm.current_state = d.get("current_stage", "qa")
        sm.context.update({
            "user_id": d.get("user_id", "student_test_01"),
            "current_knowledge_id": d.get("current_knowledge_id"),
            "current_chain_id": d.get("current_chain_id"),
            "current_question_id": d.get("current_question_id"),
            "current_socratic_id": d.get("current_socratic_id"),
            "current_feynman_id": d.get("current_feynman_id"),
            # Extract guard-relevant fields from stored results
            "diagnosis_is_correct": (d.get("diagnosis_result") or {}).get("is_correct"),
            "feynman_total_score": (d.get("feynman_result") or {}).get("total_score", 0),
        })
        return cls(sm)

    # ---- properties ----

    @property
    def current_stage(self) -> LearningStage:
        return LearningStage(self._sm.current_state)

    @property
    def context(self) -> dict:
        return self._sm.context

    @property
    def user_id(self) -> str:
        return self._sm.context.get("user_id", "student_test_01")

    @property
    def is_completed(self) -> bool:
        return self._sm.current_state == LearningStage.COMPLETED.value

    # ---- query ----

    def can_advance_to(self, target: LearningStage) -> bool:
        """Check whether advancing to `target` is currently allowed."""
        return self._sm.can_transition(target.value)

    def available_transitions(self) -> list[LearningStage]:
        """List all target stages reachable right now."""
        return [LearningStage(s) for s in self._sm.available_transitions()]

    def blocked_transitions(self) -> list[dict]:
        """List transitions that exist but are blocked by guards."""
        return self._sm.blocked_transitions()

    # ---- transitions (domain methods) ----

    def complete_qa(self) -> TransitionResult:
        """QA -> Diagnosis (unconditional)."""
        return self._advance(LearningStage.DIAGNOSIS)

    def complete_diagnosis(self, is_correct: bool) -> TransitionResult:
        """
        Diagnosis -> Socratic (wrong) or Feynman (correct).

        The guard conditions use `diagnosis_is_correct` in context.
        """
        self._sm.context["diagnosis_is_correct"] = is_correct
        target = LearningStage.FEYNMAN if is_correct else LearningStage.SOCRATIC
        return self._advance(target)

    def complete_socratic(self) -> TransitionResult:
        """Socratic -> Feynman (unconditional)."""
        return self._advance(LearningStage.FEYNMAN)

    def complete_feynman(self, total_score: int) -> TransitionResult:
        """
        Feynman -> Recommendation (pass) or back to Socratic (weak).

        The guard conditions use `feynman_total_score` in context.
        """
        self._sm.context["feynman_total_score"] = total_score
        threshold = self._sm.context.get("feynman_pass_threshold", 60)
        target = LearningStage.RECOMMENDATION if total_score >= threshold else LearningStage.SOCRATIC
        return self._advance(target)

    def complete_recommendation(self) -> TransitionResult:
        """Recommendation -> Completed (terminal)."""
        return self._advance(LearningStage.COMPLETED)

    def restart(self) -> TransitionResult:
        """Return to QA from any stage."""
        return self._advance(LearningStage.QA)

    # ---- internal ----

    def _advance(self, target: LearningStage) -> TransitionResult:
        """Execute a transition and return a structured result."""
        from_stage = self.current_stage
        self._sm.transition(target.value)

        key = (from_stage.value, target.value)
        label = TRANSITION_LABELS.get(key, f"{from_stage.value} -> {target.value}")

        return TransitionResult(
            from_stage=from_stage,
            to_stage=target,
            label=label,
            context=self._sm.context,
            available_next=[LearningStage(s) for s in self._sm.available_transitions()],
            blocked_next=self._sm.blocked_transitions(),
        )

    # ---- serialization ----

    def to_dict(self) -> dict:
        return self._sm.to_dict()


# ================================================================
# Convenience: validate transition from raw request
# ================================================================

def validate_transition(
    current_stage: str,
    target_stage: str,
    *,
    diagnosis_is_correct: bool | None = None,
    feynman_total_score: int | None = None,
) -> TransitionResult:
    """
    Stateless validation: check whether a transition is allowed
    given the current stage and relevant outcome data.

    Useful for FastAPI endpoints that receive a target stage in the request
    and need to validate it before executing business logic.

    Raises InvalidTransitionError if the transition is illegal.
    """
    machine = LearningLoopMachine.from_context(
        current_stage=current_stage,
        diagnosis_is_correct=diagnosis_is_correct,
        feynman_total_score=feynman_total_score,
    )
    return machine._advance(LearningStage(target_stage))

"""
Generic finite state machine — lightweight, zero-dependency.

Used by the learning loop and other business processes.
Framework-agnostic: works identically in Streamlit and FastAPI.
"""

from dataclasses import dataclass, field
from typing import Any, Callable


class InvalidTransitionError(Exception):
    """Raised when a transition is not allowed from the current state."""

    def __init__(self, current: str, target: str, reason: str = ""):
        msg = f"Cannot transition from '{current}' to '{target}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.current = current
        self.target = target
        self.reason = reason


@dataclass
class Transition:
    """A single transition rule between two states."""

    from_state: str
    to_state: str
    name: str = ""                               # Human-readable label
    guard: str | None = None                     # Guard condition name (for error messages)
    condition: Callable[[dict], bool] | None = None   # Guard predicate
    side_effect: Callable[[dict], dict] | None = None # Optional context mutation


@dataclass
class StateMachine:
    """
    Generic finite state machine.

    Usage:
        sm = StateMachine(
            initial_state="idle",
            transitions=[
                Transition("idle", "running"),
                Transition("running", "done"),
            ],
        )
        sm.transition("running")  # -> "running"
        sm.transition("done")     # -> "done"
        sm.transition("running")  # -> raises InvalidTransitionError
    """

    initial_state: str
    transitions: list[Transition] = field(default_factory=list)
    current_state: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.current_state:
            self.current_state = self.initial_state

    # ---- lookup ----

    def _find_transition(self, target: str) -> Transition | None:
        for t in self.transitions:
            if t.from_state == self.current_state and t.to_state == target:
                return t
        return None

    # ---- query ----

    def can_transition(self, target: str) -> bool:
        """Check whether the transition to `target` is currently allowed."""
        t = self._find_transition(target)
        if t is None:
            return False
        if t.condition and not t.condition(self.context):
            return False
        return True

    def available_transitions(self) -> list[str]:
        """List all target states reachable from the current state (considering guards)."""
        return [
            t.to_state
            for t in self.transitions
            if t.from_state == self.current_state
            and (t.condition is None or t.condition(self.context))
        ]

    def blocked_transitions(self) -> list[dict]:
        """List transitions that exist but are blocked by guard conditions."""
        result: list[dict] = []
        for t in self.transitions:
            if t.from_state != self.current_state:
                continue
            if t.condition and not t.condition(self.context):
                result.append({
                    "target": t.to_state,
                    "guard": t.guard or "unknown",
                    "name": t.name,
                })
        return result

    # ---- mutation ----

    def transition(self, target: str, **context_updates) -> str:
        """
        Execute a state transition.

        Args:
            target: Target state name.
            **context_updates: Key-value pairs merged into context BEFORE guard evaluation.

        Returns:
            New state name.

        Raises:
            InvalidTransitionError: If the transition is not defined or its guard fails.
        """
        # Apply context updates first so guards can evaluate them
        self.context.update(context_updates)

        t = self._find_transition(target)
        if t is None:
            raise InvalidTransitionError(
                self.current_state, target,
                reason=f"no transition defined from '{self.current_state}' to '{target}'",
            )

        if t.condition and not t.condition(self.context):
            raise InvalidTransitionError(
                self.current_state, target,
                reason=f"guard '{t.guard}' not satisfied",
            )

        # Side effect
        if t.side_effect:
            self.context = t.side_effect(self.context)

        self.current_state = target
        return self.current_state

    def reset(self):
        """Return to initial state, preserving context."""
        self.current_state = self.initial_state

    def hard_reset(self):
        """Return to initial state, clearing all context."""
        self.current_state = self.initial_state
        self.context = {}

    # ---- serialization ----

    def to_dict(self) -> dict:
        return {
            "current_state": self.current_state,
            "context": self.context,
            "available_transitions": self.available_transitions(),
            "blocked_transitions": self.blocked_transitions(),
        }

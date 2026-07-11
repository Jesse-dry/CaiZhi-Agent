"""
workflows/ -- Learning loop state machine.

Framework-agnostic state machine with guard-condition branching.
Backend-enforced: even if the frontend sends requests out of order,
the state machine rejects illegal transitions.

States:
    QA -> DIAGNOSIS -> SOCRATIC <-> FEYNMAN -> RECOMMENDATION -> COMPLETED

Key types:
    LearningLoopMachine   -- domain wrapper with typed transition methods
    TransitionResult      -- structured result of each transition
    validate_transition() -- stateless check for FastAPI endpoints
"""

from workflows.learning_loop import (
    Guard,
    TRANSITION_TABLE,
    TRANSITION_LABELS,
    ALLOWED_TRANSITIONS,
    LearningLoopMachine,
    TransitionResult,
    create_learning_loop_machine,
    validate_transition,
)
from workflows.state_machine import (
    StateMachine,
    Transition,
    InvalidTransitionError,
)

__all__ = [
    # State machine core
    "StateMachine",
    "Transition",
    "InvalidTransitionError",
    # Learning loop
    "Guard",
    "TRANSITION_TABLE",
    "TRANSITION_LABELS",
    "ALLOWED_TRANSITIONS",
    "LearningLoopMachine",
    "TransitionResult",
    "create_learning_loop_machine",
    "validate_transition",
]

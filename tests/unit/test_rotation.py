import pytest

from server.models.db import WorkloadState
from server.state.machine import InvalidTransitionError, VALID_TRANSITIONS, validate_transition


def test_healthy_can_transition_to_rotating():
    validate_transition(WorkloadState.HEALTHY, WorkloadState.ROTATING)


def test_rotating_can_transition_to_attesting():
    validate_transition(WorkloadState.ROTATING, WorkloadState.ATTESTING)


def test_rotating_can_transition_to_failed():
    validate_transition(WorkloadState.ROTATING, WorkloadState.FAILED)


def test_rotating_cannot_transition_to_healthy_directly():
    with pytest.raises(InvalidTransitionError):
        validate_transition(WorkloadState.ROTATING, WorkloadState.HEALTHY)


def test_rotating_cannot_transition_to_revoked():
    with pytest.raises(InvalidTransitionError):
        validate_transition(WorkloadState.ROTATING, WorkloadState.REVOKED)


def test_registered_cannot_transition_to_rotating():
    with pytest.raises(InvalidTransitionError):
        validate_transition(WorkloadState.REGISTERED, WorkloadState.ROTATING)


def test_stale_cannot_transition_to_rotating():
    with pytest.raises(InvalidTransitionError):
        validate_transition(WorkloadState.STALE, WorkloadState.ROTATING)


def test_rotating_in_valid_transitions():
    assert WorkloadState.ROTATING in VALID_TRANSITIONS
    assert VALID_TRANSITIONS[WorkloadState.ROTATING] == {
        WorkloadState.ATTESTING,
        WorkloadState.FAILED,
    }


def test_healthy_includes_rotating():
    assert WorkloadState.ROTATING in VALID_TRANSITIONS[WorkloadState.HEALTHY]


def test_rotation_lifecycle_path():
    """Full rotation path: HEALTHY → ROTATING → ATTESTING → HEALTHY"""
    validate_transition(WorkloadState.HEALTHY, WorkloadState.ROTATING)
    validate_transition(WorkloadState.ROTATING, WorkloadState.ATTESTING)
    validate_transition(WorkloadState.ATTESTING, WorkloadState.HEALTHY)


def test_rotation_failure_path():
    """Failed rotation path: HEALTHY → ROTATING → ATTESTING → FAILED"""
    validate_transition(WorkloadState.HEALTHY, WorkloadState.ROTATING)
    validate_transition(WorkloadState.ROTATING, WorkloadState.ATTESTING)
    validate_transition(WorkloadState.ATTESTING, WorkloadState.FAILED)

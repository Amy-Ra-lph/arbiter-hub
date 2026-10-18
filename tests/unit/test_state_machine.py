import pytest

from server.models.db import WorkloadState
from server.state.machine import VALID_TRANSITIONS, InvalidTransitionError, validate_transition


def test_registered_can_go_to_attesting():
    validate_transition(WorkloadState.REGISTERED, WorkloadState.ATTESTING)


def test_attesting_can_go_to_healthy():
    validate_transition(WorkloadState.ATTESTING, WorkloadState.HEALTHY)


def test_attesting_can_go_to_failed():
    validate_transition(WorkloadState.ATTESTING, WorkloadState.FAILED)


def test_healthy_can_go_to_stale():
    validate_transition(WorkloadState.HEALTHY, WorkloadState.STALE)


def test_healthy_can_go_to_revoked():
    validate_transition(WorkloadState.HEALTHY, WorkloadState.REVOKED)


def test_stale_can_go_to_attesting():
    validate_transition(WorkloadState.STALE, WorkloadState.ATTESTING)


def test_failed_can_go_to_under_remediation():
    validate_transition(WorkloadState.FAILED, WorkloadState.UNDER_REMEDIATION)


def test_failed_can_go_to_revoked():
    validate_transition(WorkloadState.FAILED, WorkloadState.REVOKED)


def test_under_remediation_can_go_to_attesting():
    validate_transition(WorkloadState.UNDER_REMEDIATION, WorkloadState.ATTESTING)


def test_failed_cannot_go_to_healthy():
    with pytest.raises(InvalidTransitionError, match="prohibited"):
        validate_transition(WorkloadState.FAILED, WorkloadState.HEALTHY)


def test_revoked_cannot_go_anywhere():
    for target in WorkloadState:
        if target != WorkloadState.REVOKED:
            with pytest.raises(InvalidTransitionError):
                validate_transition(WorkloadState.REVOKED, target)


def test_healthy_cannot_go_to_registered():
    with pytest.raises(InvalidTransitionError):
        validate_transition(WorkloadState.HEALTHY, WorkloadState.REGISTERED)


def test_all_seven_states_have_entries():
    assert len(VALID_TRANSITIONS) == 7


from server.backends.base import AttestationResult, compute_composite_verdict
from server.models.db import AttestationVerdict


def test_composite_all_pass():
    results = [
        AttestationResult(verdict=AttestationVerdict.PASS, backend="keylime", evidence_hash="a"),
        AttestationResult(verdict=AttestationVerdict.PASS, backend="cosign", evidence_hash="b"),
    ]
    assert compute_composite_verdict(results) == AttestationVerdict.PASS


def test_composite_one_fail_one_pass():
    results = [
        AttestationResult(verdict=AttestationVerdict.PASS, backend="keylime", evidence_hash="a"),
        AttestationResult(verdict=AttestationVerdict.FAIL, backend="cosign", evidence_hash="b"),
    ]
    assert compute_composite_verdict(results) == AttestationVerdict.FAIL


def test_composite_one_unavailable_one_pass():
    results = [
        AttestationResult(verdict=AttestationVerdict.PASS, backend="keylime", evidence_hash="a"),
        AttestationResult(
            verdict=AttestationVerdict.UNAVAILABLE, backend="cosign", evidence_hash=""
        ),
    ]
    assert compute_composite_verdict(results) == AttestationVerdict.UNAVAILABLE


def test_composite_fail_trumps_unavailable():
    results = [
        AttestationResult(verdict=AttestationVerdict.FAIL, backend="keylime", evidence_hash="a"),
        AttestationResult(
            verdict=AttestationVerdict.UNAVAILABLE, backend="cosign", evidence_hash=""
        ),
    ]
    assert compute_composite_verdict(results) == AttestationVerdict.FAIL


def test_composite_single_backend():
    results = [
        AttestationResult(verdict=AttestationVerdict.PASS, backend="keylime", evidence_hash="a"),
    ]
    assert compute_composite_verdict(results) == AttestationVerdict.PASS


def test_composite_error_treated_as_unavailable():
    results = [
        AttestationResult(verdict=AttestationVerdict.PASS, backend="keylime", evidence_hash="a"),
        AttestationResult(verdict=AttestationVerdict.ERROR, backend="cosign", evidence_hash=""),
    ]
    assert compute_composite_verdict(results) == AttestationVerdict.UNAVAILABLE

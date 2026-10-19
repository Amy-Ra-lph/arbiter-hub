import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mock-kbs"))


@pytest.mark.asyncio
async def test_mock_kbs_health():
    from mock_kbs.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/kbs/v0/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_mock_kbs_attest_registered_measurement():
    from mock_kbs.main import _registered_measurements, app

    _registered_measurements.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        reg_resp = await c.post(
            "/kbs/v0/register", json={"measurement": "ab" * 24}
        )
        assert reg_resp.status_code == 200

        resp = await c.post(
            "/kbs/v0/attest",
            json={"evidence": {"measurement": "ab" * 24, "report_data": "cd" * 32}},
        )
        assert resp.status_code == 200
        assert resp.json()["attestation_pass"] is True
        assert "measurement" in resp.json()["report"]


@pytest.mark.asyncio
async def test_mock_kbs_attest_unknown_measurement():
    from mock_kbs.main import _registered_measurements, app

    _registered_measurements.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/kbs/v0/attest",
            json={"evidence": {"measurement": "ff" * 24, "report_data": "00" * 32}},
        )
        assert resp.status_code == 200
        assert resp.json()["attestation_pass"] is False


def test_evidence_generator_produces_snp_fields():
    from mock_kbs.evidence import generate_snp_report

    report = generate_snp_report(measurement="ab" * 24, report_data="cd" * 32)
    assert len(report["report_data"]) == 128
    assert len(report["measurement"]) == 96
    assert "policy" in report
    assert "platform_version" in report

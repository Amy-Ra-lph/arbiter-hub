from fastapi import FastAPI
from pydantic import BaseModel

from mock_kbs.evidence import generate_snp_report

app = FastAPI(title="Mock KBS (Trustee-compatible)")

_registered_measurements: set[str] = set()


class RegisterRequest(BaseModel):
    measurement: str


class AttestEvidence(BaseModel):
    measurement: str
    report_data: str = "00" * 32


class AttestRequest(BaseModel):
    evidence: AttestEvidence


@app.get("/kbs/v0/health")
async def health():
    return {"status": "ok"}


@app.post("/kbs/v0/register")
async def register_measurement(body: RegisterRequest):
    _registered_measurements.add(body.measurement)
    return {"registered": True, "measurement": body.measurement}


@app.post("/kbs/v0/attest")
async def attest(body: AttestRequest):
    report = generate_snp_report(
        measurement=body.evidence.measurement,
        report_data=body.evidence.report_data,
    )
    passed = body.evidence.measurement in _registered_measurements
    return {"attestation_pass": passed, "report": report}

# Integration Examples

Reference implementations for connecting Arbiter Hub to external systems.
Adapt these to your environment.

## GitHub Actions (`github-actions-attest-deploy.yml`)

CI/CD workflow for self-hosted runners. Builds, signs (cosign via Hub),
attests (registers workload, verifies state), and deploys only if the
workload is in ATTESTED or HEALTHY state.

**Setup:**
1. Install a self-hosted runner in your network with access to Hub + IPA
2. Register an ahdapa OAuth2 client for CI (`client_credentials` grant)
3. Add secrets: `ARBITER_CLIENT_ID`, `ARBITER_CLIENT_SECRET`
4. Add variables: `IPA_HOST`, `HUB_HOST`, `REGISTRY`
5. Copy workflow to `.github/workflows/`
6. Configure branch protection to require `verify-attestation` check

## ServiceNow Webhook (`servicenow-webhook.py`)

Receives OCSF v1.3 events from Hub EDA and creates ServiceNow incidents
for SUSPECT, QUARANTINED, and REVOKED state transitions.

**Setup:**
```bash
export SNOW_INSTANCE=dev12345.service-now.com
export SNOW_USER=api_user
export SNOW_PASSWORD=api_password
export SNOW_ASSIGNMENT_GROUP="Security Operations"
python3 servicenow-webhook.py --port 8080
```

**Hub EDA config:**
Point webhook URL to `http://<this-host>:8080/webhook`

**Testing:**
```bash
# Test without SNOW credentials (prints what would be created)
python3 servicenow-webhook.py --test

# Send test event
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":"Workload state transition: ATTESTED → SUSPECT","finding":{"title":"TPM failure","desc":"Quote mismatch"},"resources":[{"name":"test-app"}]}'
```

No pip dependencies — stdlib only (`http.server`, `urllib`).

# Arbiter Hub

Federation attestation hub that arbitrates trust decisions across multiple attestation backends — Keylime, Trustee (KBS), cosign, and Rekor — through a unified API and management interface.

Arbiter Hub tracks workloads through a 7-state machine (registered, attesting, healthy, stale, failed, under_remediation, revoked), enforces attestation policies, gates secret release on workload state, and provides a complete audit trail.

## Architecture

```
Browser ──► nginx :8080 ──► React SPA (PatternFly 6)
                │
                ▼ /api/
        FastAPI :8400 (stateless, horizontally scalable)
            ├── PostgreSQL (shared state)
            ├── Keylime Verifier (TPM attestation, mTLS)
            ├── Trustee KBS (confidential computing secrets)
            ├── cosign (container image signing)
            └── Rekor (transparency log)
```

See [docs/architecture.md](docs/architecture.md) for the full architecture reference.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 22+
- PostgreSQL 16

### Backend

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure database
export ARBITER_DATABASE_URL="postgresql+asyncpg://arbiter:yourpassword@localhost:5432/arbiter"
export ARBITER_DEV_MODE=true  # enables header-based auth for development

# Run migrations
alembic upgrade head

# Start API server
uvicorn server.main:app --host 0.0.0.0 --port 8400 --reload
```

### Frontend

```bash
cd ui
npm ci
npm run dev    # starts on :5173, proxies /api to :8400
```

### Tests

```bash
# Backend (84 tests)
pytest tests/ -v

# Frontend (23 tests)
cd ui && npx vitest run

# Lint
ruff check . && ruff format --check .
```

## Container Deployment

Arbiter Hub ships as four container images, deployed via Podman Quadlet units:

| Image | Purpose | Port |
|-------|---------|------|
| `arbiter-hub-api` | FastAPI backend | 8400 (internal) |
| `arbiter-hub-ui` | nginx + React SPA | 8080 (external) |
| `arbiter-hub-kbs` | Key Broker Service | internal only |
| `arbiter-hub-mcp` | MCP tools server | 127.0.0.1:8401 |

```bash
# Deploy with Ansible
ansible-playbook -i inventory deploy/ansible/site.yml \
  -e arbiter_hub_db_password="$(openssl rand -base64 32)"
```

Images: `quay.io/rhel-security/arbiter-hub-{api,ui,kbs,mcp}`

### Multi-Node Scaling

The API tier is stateless — scale by adding nodes behind the nginx upstream. See [deploy/multi-node/](deploy/multi-node/) for example configuration.

## Project Structure

```
server/                 # FastAPI backend
  api/                  #   REST endpoints (workloads, attestation, audit, kbs, signing, health)
  auth/                 #   Authentication and RBAC
  backends/             #   Attestation backend adapters (keylime, cosign, trustee, rekor)
  kbs/                  #   Key Broker Service gate logic
  models/               #   SQLAlchemy models and Pydantic schemas
  policy/               #   Policy engine (rules-based, OPA-compatible interface)
  state/                #   Mubeen 7-state machine and stale-TTL scheduler
  plugins/              #   Plugin loader (entry_points-based)
  telemetry/            #   OpenTelemetry, Prometheus metrics, OCSF events, webhooks
ui/                     # React 18 + TypeScript + PatternFly 6 SPA
  src/pages/            #   Dashboard, Workloads, WorkloadDetail, Backends, Policies,
                        #   AuditLog, History, KBSSecrets, Federation (topology), Vulnerabilities
  src/services/         #   RTK Query API services
  src/components/       #   StateBadge, VerdictBadge, TTLCountdown, StateMachineDiagram
arbiter_mcp/            # MCP tools server (read-only federation queries)
clevis-pin/             # Clevis pin for TPM-bound secret release
deploy/
  containerfiles/       #   Multi-stage Containerfiles (UBI 10)
  quadlet/              #   Podman Quadlet systemd units
  nginx/                #   Reverse proxy config with upstream failover
  ansible/              #   Deployment automation (ansible-freeipa pattern)
  multi-node/           #   Horizontal scaling example
tests/                  # 84 backend tests (unit + integration)
```

## State Machine

Workloads follow the Mubeen 7-state machine:

```
registered ──► attesting ──► healthy ──► stale ──► failed
                  ▲              │                    │
                  │              │                    ▼
                  │              ▼            under_remediation
                  │           revoked
                  │              ▲
                  └──────────────┘
```

- **Healthy workloads** are re-attested before their stale TTL expires
- **Stale** triggers when TTL elapses without re-attestation
- **Failed** on attestation failure — can be remediated or revoked
- **Revoked** is terminal unless explicitly re-registered

## Security

See [docs/security-threat-model.md](docs/security-threat-model.md) for the full STRIDE analysis, findings, and remediation status.

Key security properties:
- Authentication gated by `ARBITER_DEV_MODE` — production requires OIDC/mTLS
- KBS secrets encrypted at rest (AES) with mandatory key file
- Internal network isolation (Quadlet `Internal=true`)
- Container images run non-root, read-only filesystem
- CSP, X-Frame-Options, X-Content-Type-Options on all responses
- CSV exports sanitized against formula injection
- CI includes CodeQL SAST and dependency license review

## Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| Phase 1 | Complete | Core API, 4 backends, state machine, audit, Beaker CI |
| Phase 2 | Complete | React UI (12 pages), multi-node failover, threat model |
| Phase 2.5 | Planned | OIDC auth, CORS, rate limiting, append-only audit |
| Phase 3 | Planned | Falco eBPF runtime monitoring, EDA remediation rulebooks, mTLS backend-to-backend |

## CI

GitHub Actions runs on every push and PR:
- **Lint** — ruff check + format
- **Test** — pytest against real PostgreSQL
- **CodeQL** — Python SAST analysis
- **Dependency Review** — license and vulnerability check (PRs only)

## License

Apache License 2.0. See [LICENSE](LICENSE).

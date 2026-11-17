# Arbiter Hub Secret Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Arbiter Hub application secrets out of systemd unit files, environment variables, and command lines into file-based secrets consumed by the app, with idempotent generation for demo and fail-closed sealed credentials for production.

**Architecture:** Pydantic Settings reads secrets from `/run/secrets` (podman `Secret=...,type=mount`). A single `build_dsn()` helper owns URL percent-encoding. Firstboot stores root-only files under `/etc/arbiter/secrets/` (0700) and creates podman secrets from them, reusing existing values. A deployment-mode switch (`demo` / `production`) decides generation vs sealed decryption and whether the local admin account is enabled.

**Tech Stack:** Python 3.12, pydantic 2.7+, pydantic-settings 2.3+, FastAPI, SQLAlchemy/Alembic, bash, podman + Quadlet, systemd-creds.

**Spec:** `docs/superpowers/specs/2026-11-16-arbiter-secrets-handling-design.md`

## Global Constraints

- Secrets must never appear in: git-tracked files, `Environment=` in Quadlet units, container argv, stdout/logs.
- `ARBITER_DATABASE_URL` remains a supported explicit override and wins over component secrets.
- Existing deployments that set `ARBITER_DATABASE_URL` must keep working unchanged.
- Python: keep `model_config = {"env_prefix": "ARBITER_", "secrets_dir": "/run/secrets"}` shape; no new dependencies.
- Bash: `set -euo pipefail` stays; all secret files created under `umask 077`; mode 0600/0700.
- Demo images must provision with no operator input; production must fail closed.
- Quadlet secret names are fixed: `arbiter-hub-db-password`, `arbiter-hub-admin-password`.
- Secret file names match the Settings field names exactly: `db_password`, `local_admin_password`.

## File Structure

| File | Responsibility |
|---|---|
| `server/db_url.py` (new) | Build and encode the asyncpg DSN from components |
| `server/config.py` | Secret fields, `secrets_dir`, `dsn` property |
| `server/models/db.py` | Engine uses `settings.dsn` |
| `alembic/env.py` | Component-based DSN for migrations |
| `server/auth/dependencies.py`, `server/api/auth_config.py` | Unwrap `SecretStr` |
| `deploy/quadlet/arbiter-hub-api.container`, `deploy/multi-node/arbiter-hub-api-2.container` | Mount secrets, drop plaintext URL |
| `deploy/bootc/server-firstboot.sh` | Secret files, podman secrets, migration, modes, permissions |
| `deploy/bootc/seal-secrets.sh` (new), `deploy/bootc/production-secrets.md` (new) | Production sealing |
| `idm-ci/metadata/infra/bootc-arbiter-server-fedora-44.yaml` | Demo mode flag + post-firstboot assertions |
| `tests/unit/test_db_url.py`, `test_local_admin_secret.py`, `test_quadlet_secrets.py`, `test_firstboot_secrets.py` (new) | Unit + contract tests |

## Review Focus

1. **Base64 password containing `/`, `+`, `=`** — must be percent-encoded in the DSN; a raw value breaks asyncpg URL parsing. Pinned in Task 1.
2. **`ARBITER_DATABASE_URL` set explicitly** — must still win over `db_password`/`secrets_dir`, or existing deployments break on upgrade. Pinned in Task 1.
3. **Empty `SecretStr`** — `bool(SecretStr(""))` is `True`; an empty admin password must count as disabled, never as an enabled account with a blank password. Pinned in Task 2.
4. **Firstboot re-run with an existing podman secret** — must reuse, not regenerate; otherwise Postgres role and secret drift and the API locks out. Pinned in Task 4 and exercised in Task 8.
5. **Production with no sealed credential present** — must exit non-zero before starting containers rather than silently generating a password. Pinned in Task 5.

---

### Task 1: DSN builder and Settings wiring

**Files:**
- Create: `server/db_url.py`
- Create: `tests/unit/test_db_url.py`
- Modify: `server/config.py:5,30,53` (defaults + model_config)
- Modify: `server/models/db.py:204`
- Modify: `alembic/env.py:18`
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `build_dsn(password: str, user: str = "arbiter", host: str = "arbiter-hub-db", port: int = 5432, database: str = "arbiter") -> str`; `Settings.db_password: SecretStr`; `Settings.dsn -> str`; `server.models.db.get_engine()`; `server.models.db.async_session()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_db_url.py
from server.db_url import build_dsn


def test_encodes_base64_password():
    assert build_dsn("a/b+c=") == (
        "postgresql+asyncpg://arbiter:a%2Fb%2Bc%3D@arbiter-hub-db:5432/arbiter"
    )


def test_defaults():
    assert build_dsn("pw") == (
        "postgresql+asyncpg://arbiter:pw@arbiter-hub-db:5432/arbiter"
    )


def test_rejects_empty_password():
    import pytest
    with pytest.raises(ValueError):
        build_dsn("")
```

```python
# tests/test_config.py — append
from server.config import Settings


def test_dsn_uses_secret_file(tmp_path):
    (tmp_path / "db_password").write_text("a/b+c=")
    settings = Settings(_secrets_dir=str(tmp_path))
    assert settings.dsn == (
        "postgresql+asyncpg://arbiter:a%2Fb%2Bc%3D@arbiter-hub-db:5432/arbiter"
    )


def test_explicit_database_url_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("ARBITER_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db")
    settings = Settings(_secrets_dir=str(tmp_path))
    assert settings.dsn == "postgresql+asyncpg://u:p@h:5432/db"


def test_dsn_raises_without_url_or_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("ARBITER_DATABASE_URL", raising=False)
    settings = Settings(_secrets_dir=str(tmp_path / "missing"))
    with pytest.raises(ValueError):
        settings.dsn


def test_db_module_imports_without_db_config(tmp_path, monkeypatch):
    """Import must not resolve the DSN; the engine is created lazily."""
    monkeypatch.delenv("ARBITER_DATABASE_URL", raising=False)
    import importlib

    import server.models.db as db
    importlib.reload(db)
    assert callable(db.async_session)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_db_url.py tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: server.db_url`, then `AttributeError: 'Settings' object has no attribute 'dsn'`.

- [ ] **Step 3: Implement `build_dsn()` and wire Settings**

`server/db_url.py`: build the URL with `urllib.parse.quote(password, safe="")`; raise `ValueError("db password is empty")` when `password == ""`.

`server/config.py`: add `from pydantic import SecretStr`; change `database_url: str = ""`; add `db_password: SecretStr = SecretStr("")`; add property `dsn` returning `self.database_url or build_dsn(self.db_password.get_secret_value())`; set `model_config = {"env_prefix": "ARBITER_", "secrets_dir": "/run/secrets"}`.

`server/models/db.py:204` — replace the module-level `engine` / `async_session` objects with lazy accessors, because `settings.dsn` now raises when neither the override nor a secret is present and the module is imported everywhere:

```python
_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.dsn, echo=False)
    return _engine


def async_session():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory()
```

`get_session()` at line 210 becomes `async with async_session() as session:`. `server/state/scheduler.py:31` already calls `async_session()` and needs no change.

`alembic/env.py` after line 18:

```python
if not _db_url_override and os.environ.get("ALEMBIC_DB_PASSWORD"):
    _db_url_override = build_dsn(
        os.environ["ALEMBIC_DB_PASSWORD"],
        host=os.environ.get("ALEMBIC_DB_HOST", "arbiter-hub-db"),
    )
```
with `from server.db_url import build_dsn` at the imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_db_url.py tests/test_config.py -v`
Expected: PASS (new tests) and existing config tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add server/db_url.py server/config.py server/models/db.py alembic/env.py tests/
git commit -m "feat(config): file-based DB secret with encoded DSN builder"
```

---

### Task 2: Local admin password as SecretStr

**Files:**
- Modify: `server/config.py:30`
- Modify: `server/auth/dependencies.py:39`
- Modify: `server/api/auth_config.py:38`
- Create: `tests/unit/test_local_admin_secret.py`

**Interfaces:**
- Consumes: `Settings` from Task 1.
- Produces: `Settings.local_admin_password: SecretStr`; callers use `.get_secret_value()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_local_admin_secret.py
from server.config import Settings


def test_admin_password_from_secret_file(tmp_path):
    (tmp_path / "local_admin_password").write_text("s3cret", encoding="utf-8")
    settings = Settings(_secrets_dir=str(tmp_path))
    assert settings.local_admin_password.get_secret_value() == "s3cret"


def test_empty_admin_password_is_empty_string(tmp_path):
    settings = Settings(_secrets_dir=str(tmp_path))
    assert settings.local_admin_password.get_secret_value() == ""


def test_admin_password_not_in_repr(tmp_path):
    (tmp_path / "local_admin_password").write_text("s3cret", encoding="utf-8")
    settings = Settings(_secrets_dir=str(tmp_path))
    assert "s3cret" not in repr(settings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_local_admin_secret.py -v`
Expected: FAIL — `AttributeError: 'str' object has no attribute 'get_secret_value'`.

- [ ] **Step 3: Change the type and unwrap at call sites**

`server/config.py:30`: `local_admin_password: SecretStr = SecretStr("")`.

`server/auth/dependencies.py:39`: `password=settings.local_admin_password.get_secret_value()`.

`server/api/auth_config.py:38`: `if not settings.local_admin_password.get_secret_value():`.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests -q`
Expected: PASS. Any test constructing `Settings(local_admin_password="x")` still works (pydantic coerces str to SecretStr).

- [ ] **Step 5: Commit**

```bash
git add server/config.py server/auth/dependencies.py server/api/auth_config.py tests/unit/test_local_admin_secret.py
git commit -m "feat(auth): store local admin password as SecretStr"
```

---

### Task 3: Quadlet templates use mounted secrets

**Files:**
- Modify: `deploy/quadlet/arbiter-hub-api.container:13-14`
- Modify: `deploy/multi-node/arbiter-hub-api-2.container:12-13`
- Create: `tests/unit/test_quadlet_secrets.py`

**Interfaces:**
- Consumes: Settings field names `db_password`, `local_admin_password` (Task 1/2).
- Produces: units that mount `/run/secrets/db_password` and `/run/secrets/local_admin_password`; no `Environment=` carrying a password.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/unit/test_quadlet_secrets.py
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API_UNITS = [
    REPO / "deploy/quadlet/arbiter-hub-api.container",
    REPO / "deploy/multi-node/arbiter-hub-api-2.container",
]


@pytest.mark.parametrize("unit", API_UNITS)
def test_api_unit_mounts_both_secrets(unit):
    text = unit.read_text()
    assert "Secret=arbiter-hub-db-password,type=mount,target=db_password" in text
    assert (
        "Secret=arbiter-hub-admin-password,type=mount,target=local_admin_password"
        in text
    )


@pytest.mark.parametrize("unit", API_UNITS)
def test_api_unit_has_no_password_env(unit):
    text = unit.read_text()
    assert not re.search(r"^Environment=\S*PASSWORD", text, re.MULTILINE)
    assert "ARBITER_DATABASE_URL" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_quadlet_secrets.py -v`
Expected: FAIL on missing mount lines.

- [ ] **Step 3: Edit the two unit files**

Replace the `Secret=...,type=env,target=ARBITER_DB_PASSWORD` line and the plaintext `Environment=ARBITER_DATABASE_URL=...` line in both files with:

```
Secret=arbiter-hub-db-password,type=mount,target=db_password
Secret=arbiter-hub-admin-password,type=mount,target=local_admin_password
```

Leave `deploy/quadlet/arbiter-hub-db.container` unchanged — the Postgres image only accepts `POSTGRESQL_PASSWORD` through the environment, injected by podman from the secret; the value never lands in a host unit file.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_quadlet_secrets.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/quadlet/arbiter-hub-api.container deploy/multi-node/arbiter-hub-api-2.container tests/unit/test_quadlet_secrets.py
git commit -m "feat(quadlet): mount app secrets instead of env plaintext"
```

---

### Task 4: Firstboot secret lifecycle

**Files:**
- Modify: `deploy/bootc/server-firstboot.sh:9,30-37,183-232,264-276,344-364,408-414`
- Create: `tests/unit/test_firstboot_secrets.py`

**Interfaces:**
- Consumes: podman secret names and field names from Tasks 1-3.
- Produces: `/etc/arbiter/secrets/` files (`db_password`, `local_admin_password`) mode 0600 in a 0700 dir; identical podman secrets; a firstboot that never prints or embeds a secret.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/unit/test_firstboot_secrets.py
import re
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2]
          / "deploy/bootc/server-firstboot.sh").read_text()


def test_umask_set_before_secret_writes():
    assert re.search(r"^umask 077$", SCRIPT, re.MULTILINE)


def test_no_password_in_environment_lines():
    assert not re.search(r"^Environment=\S*PASSWORD", SCRIPT, re.MULTILINE)
    assert "DB_PASSWORD_URLENC" not in SCRIPT


def test_secret_helpers_present_and_idempotent():
    assert "ensure_secret_file()" in SCRIPT
    assert "ensure_podman_secret()" in SCRIPT
    assert "podman secret inspect" in SCRIPT


def test_migration_does_not_pass_dsn_on_argv():
    assert "ALEMBIC_DB_URL=" not in SCRIPT
    assert "target=ALEMBIC_DB_PASSWORD" in SCRIPT


def test_dropins_are_private():
    assert re.search(r"chmod 600 .*arbiter-hub-api\.container\.d", SCRIPT)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_firstboot_secrets.py -v`
Expected: FAIL on `umask 077`, helpers, and `DB_PASSWORD_URLENC` still present.

- [ ] **Step 3: Rewrite the secret lifecycle in firstboot**

After `set -euo pipefail`: add `umask 077`.

Replace lines 30-37 with:

```bash
SECRETS_DIR=/etc/arbiter/secrets
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

ensure_secret_file() {
    local name="$1" bytes="$2"
    [ -s "${SECRETS_DIR}/${name}" ] && return 0
    openssl rand -base64 "$bytes" > "${SECRETS_DIR}/${name}"
    chmod 600 "${SECRETS_DIR}/${name}"
}

ensure_podman_secret() {
    local name="$1" file="$2"
    podman secret inspect "$name" >/dev/null 2>&1 && return 0
    podman secret create "$name" < "${SECRETS_DIR}/${file}"
}

ensure_secret_file db_password 32
ensure_secret_file local_admin_password 24
ensure_podman_secret arbiter-hub-db-password db_password
ensure_podman_secret arbiter-hub-admin-password local_admin_password
```

Honor `server.env` overrides when the corresponding file does not yet exist: if `DB_PASSWORD` / `ARBITER_SERVICE_PASSWORD` are set and the file is missing, write them instead of generating. Never overwrite an existing file.

Delete the `password.conf` drop-in block (lines 183-190) and the `podman secret create` at line 184 (superseded).

In the API `config.conf` drop-in (lines 217-232): delete the `ARBITER_DATABASE_URL` and `ARBITER_LOCAL_ADMIN_PASSWORD` lines. After writing the file, `chmod 600 /etc/containers/systemd/arbiter-hub-api.container.d/*.conf`.

Replace the migration block (lines 269-275) with:

```bash
DB_CONTAINER_IP=$(podman inspect arbiter-hub-db --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
podman run --rm --network systemd-arbiter-hub \
    --secret arbiter-hub-db-password,type=env,target=ALEMBIC_DB_PASSWORD \
    -e ALEMBIC_DB_HOST="${DB_CONTAINER_IP}" \
    quay.io/rhel-security/arbiter-hub-api:latest \
    bash -c 'cd /opt/app-root/src && alembic upgrade head'
```

In the EDA inventory block, replace `${ARBITER_SERVICE_PASSWORD}` with `$(cat "${SECRETS_DIR}/local_admin_password")` and keep `chmod 600` on `hosts.yml`.

Remove the three `sed -i` redactions of `DB_PASSWORD` / `ARBITER_SERVICE_PASSWORD` from `server.env` only if those keys are still supported as overrides — otherwise keep them and additionally redact `WEBHOOK_SECRET` as today.

- [ ] **Step 4: Check syntax and run contract tests**

Run: `bash -n deploy/bootc/server-firstboot.sh && pytest tests/unit/test_firstboot_secrets.py -v`
Expected: no syntax output from `bash -n`; all contract tests PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/bootc/server-firstboot.sh tests/unit/test_firstboot_secrets.py
git commit -m "feat(firstboot): idempotent file-based secrets, no plaintext env or argv"
```

---

### Task 5: Demo vs production mode guard

**Files:**
- Modify: `deploy/bootc/server-firstboot.sh` (top, after config validation)
- Modify: `deploy/bootc/server.env.example`
- Create: `tests/unit/test_deployment_mode.py`

**Interfaces:**
- Consumes: `SECRETS_DIR` and helpers from Task 4.
- Produces: `ARBITER_DEPLOYMENT_MODE` (`demo|production`, default `production`); production requires sealed credentials and refuses demo defaults.

- [ ] **Step 1: Write the failing contract test**

```python
# tests/unit/test_deployment_mode.py
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2]
          / "deploy/bootc/server-firstboot.sh").read_text()


def test_mode_defaults_to_production():
    assert 'ARBITER_DEPLOYMENT_MODE:-production' in SCRIPT


def test_production_refuses_demo_password():
    assert "Secret123!" in SCRIPT
    assert "refusing demo IPA admin password" in SCRIPT


def test_production_requires_sealed_credentials():
    assert "systemd-creds decrypt" in SCRIPT
    assert "missing sealed secret" in SCRIPT


def test_local_admin_disabled_in_production():
    assert 'ARBITER_ALLOW_LOCAL_ADMIN' in SCRIPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_deployment_mode.py -v`
Expected: FAIL — none of the strings exist.

- [ ] **Step 3: Implement the guard**

After the `IPA_ADMIN_PASSWORD` check, add:

```bash
DEPLOYMENT_MODE="${ARBITER_DEPLOYMENT_MODE:-production}"
case "$DEPLOYMENT_MODE" in
    demo|production) ;;
    *) echo "ERROR: ARBITER_DEPLOYMENT_MODE must be demo or production"; exit 1 ;;
esac

if [ "$DEPLOYMENT_MODE" = "production" ]; then
    [ "$IPA_ADMIN_PASSWORD" = "Secret123!" ] && {
        echo "ERROR: refusing demo IPA admin password in production"; exit 1; }
    for name in db_password local_admin_password; do
        if [ ! -s "${SECRETS_DIR}/${name}" ]; then
            if [ -f "/etc/arbiter/secrets/${name}.cred" ]; then
                systemd-creds decrypt --name="$name" --with-key=host+tpm2 \
                    "/etc/arbiter/secrets/${name}.cred" > "${SECRETS_DIR}/${name}"
                chmod 600 "${SECRETS_DIR}/${name}"
            else
                echo "ERROR: missing sealed secret ${name} for production"; exit 1
            fi
        fi
    done
    ARBITER_LOCAL_ADMIN_ENABLED="${ARBITER_ALLOW_LOCAL_ADMIN:-false}"
else
    ARBITER_LOCAL_ADMIN_ENABLED="${ARBITER_LOCAL_ADMIN_ENABLED:-true}"
fi
```

Note the ordering constraint: this block must run after `SECRETS_DIR` is defined and before `ensure_secret_file` calls, so move the `SECRETS_DIR` definition above the mode guard and let `ensure_secret_file` remain generation-only for demo.

Add to `server.env.example`:

```
# demo | production (default: production)
ARBITER_DEPLOYMENT_MODE=demo
```

- [ ] **Step 4: Verify**

Run: `bash -n deploy/bootc/server-firstboot.sh && pytest tests/unit/test_deployment_mode.py -v`
Expected: no syntax output; all PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy/bootc/server-firstboot.sh deploy/bootc/server.env.example tests/unit/test_deployment_mode.py
git commit -m "feat(firstboot): fail-closed production mode, demo opt-in"
```

---

### Task 6: Demo CI metadata

**Files:**
- Modify: `~/DevSpace/idm-ci/metadata/infra/bootc-arbiter-server-fedora-44.yaml:149-158` (server.env heredoc)
- Modify: same file, after the firstboot wait loop (~line 175)

**Interfaces:**
- Consumes: `ARBITER_DEPLOYMENT_MODE` from Task 5.
- Produces: demo runs that exercise the new path and assert no secret leaked into units.

- [ ] **Step 1: Add the mode flag and assertions**

In the heredoc add `ARBITER_DEPLOYMENT_MODE=demo` after `IPA_DOMAIN`.

After the firstboot wait loop, add a step that fails the build on regressions:

```bash
echo "=== secret hygiene checks ==="
systemctl cat arbiter-hub-api 2>/dev/null | grep -qi 'PASSWORD' \
  && { echo "FAIL: password in unit file"; exit 1; }
podman secret ls --format '{{.Name}}' | grep -qx arbiter-hub-db-password \
  || { echo "FAIL: db password secret missing"; exit 1; }
podman secret ls --format '{{.Name}}' | grep -qx arbiter-hub-admin-password \
  || { echo "FAIL: admin password secret missing"; exit 1; }
echo "=== secret hygiene OK ==="
```

- [ ] **Step 2: Verify the edit is present**

Run: `grep -n "ARBITER_DEPLOYMENT_MODE=demo\|secret hygiene OK" ~/DevSpace/idm-ci/metadata/infra/bootc-arbiter-server-fedora-44.yaml`
Expected: two matching lines.

- [ ] **Step 3: Commit and push (branch `arbiter-demo-3node` only)**

```bash
cd ~/DevSpace/idm-ci
git add metadata/infra/bootc-arbiter-server-fedora-44.yaml
git commit -m "test(demo): mark demo mode and assert secret hygiene"
git push afarley arbiter-demo-3node
```

---

### Task 7: Production sealing tooling and docs

**Files:**
- Create: `deploy/bootc/seal-secrets.sh`
- Create: `deploy/bootc/production-secrets.md`

**Interfaces:**
- Consumes: secret names from Task 4, mode contract from Task 5.
- Produces: `/etc/arbiter/secrets/db_password.cred` and `local_admin_password.cred`, encrypted with `--with-key=host+tpm2`.

- [ ] **Step 1: Write the sealing script**

`deploy/bootc/seal-secrets.sh`: `set -euo pipefail`; `umask 077`; refuse to run if `.cred` files already exist; for each of `db_password` (32 bytes) and `local_admin_password` (24 bytes), generate with `openssl rand -base64`, pipe to `systemd-creds encrypt --name=<name> --with-key=host+tpm2 - /etc/arbiter/secrets/<name>.cred`, then `systemd-creds decrypt` back and compare before deleting any plaintext. Print only names and paths, never values.

- [ ] **Step 2: Write the runbook**

`deploy/bootc/production-secrets.md`: when to run (after image deployment, before first boot of `arbiter-server-firstboot.service`), TPM2 vs `--with-key=host` fallback and what each protects against, what happens if a `.cred` is missing (firstboot exits 1), rotation procedure (re-seal, then `podman secret rm` and reboot), and the demo contrast.

- [ ] **Step 3: Verify**

Run: `bash -n deploy/bootc/seal-secrets.sh`
Expected: no output (syntax valid). Run `shellcheck deploy/bootc/seal-secrets.sh` if available; expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add deploy/bootc/seal-secrets.sh deploy/bootc/production-secrets.md
git commit -m "feat(bootc): TPM2-sealed production secret provisioning"
```

---

### Task 8: End-to-end verification

**Files:** none (verification only; record in `poc/RESULTS.md`).

**Interfaces:**
- Consumes: all prior tasks.
- Produces: evidence that demo still passes and no secret is present in build logs or unit files.

- [ ] **Step 1: Push arbiter-hub and bump CACHE_BUST**

```bash
cd ~/DevSpace/arbiter-hub && git push origin partner-onboarding
cd ~/DevSpace/idm-ci
sed -i 's/^ARG CACHE_BUST=.*/ARG CACHE_BUST=2026-11-16b/' bootc-containerfiles/bootc-arbiter-server-fedora-44
git add bootc-containerfiles/bootc-arbiter-server-fedora-44
git commit -m "chore: bump CACHE_BUST for secrets refactor"
git push afarley arbiter-demo-3node
```

- [ ] **Step 2: Run Phase 1, then Phase 2**

Use the standard parameter sets from `poc/HANDOFF.md` (Phase 1 with `IDMCI_CUSTOM_CONTAINERFILE`, Phase 2 without). Wait for `result=SUCCESS` on each.

- [ ] **Step 3: Verify success markers**

Phase 2 console must contain all of: `=== Primary installed ===`, `OAuth2: 4 pass, 0 fail`, `Hub API healthy`, `=== Arbiter Server: 7 pass, 0 fail ===`, `=== agent enrolled ===`, `=== secret hygiene OK ===`. Absence of any line is a failure, not a pass.

- [ ] **Step 4: Verify no secret leakage**

```bash
curl -sk -u "afarley:$(cat ~/.jenkins-token)" \
  "$JENKINS_URL/job/User-Tools/job/trigger-test-suite-tool/<N>/consoleText" \
  | grep -Ei 'password|database_url|asyncpg://' | grep -v 'secret hygiene'
```
Expected: no line containing a credential value. Any hit is a finding.

- [ ] **Step 5: Record results**

Write build numbers, pass/fail lines, and any leak hits to `poc/RESULTS.md` using the format in `poc/CLAUDE.md`.

## Self-Review

- **Spec coverage:** capture point (T1,T3,T4), DSN in app (T1), idempotency (T4), modes (T5), demo metadata (T6), production sealing (T7), Postgres env exception (T3 note), rollout/verification (T8). Threat-model items map to T4 (local user, logs) and T7 (at-rest).
- **Step scan:** each step has one checkable result; implementation steps give signatures and the specific values, not full bodies except where the algorithm is not implied (firstboot helper block, mode guard).
- **Type consistency:** `db_password`, `local_admin_password`, `build_dsn`, `Settings.dsn`, `ensure_secret_file`, `ensure_podman_secret`, `SECRETS_DIR`, `ARBITER_DEPLOYMENT_MODE` used identically across tasks.
- **Review Focus:** each of the five items is pinned by a named test in T1, T2, T4, T5.
- **Proportion:** plan is task-level; code bodies appear only where the implementation is not determined by a signature and a test.

## Review Findings Applied (2026-11-16)

1. **Bug A — empty-password test contradiction.** Removed the test expecting a
   graceful default; added `test_dsn_raises_without_url_or_secret`. Because
   `server/models/db.py` built the engine at import, the `ValueError` would have
   broken every module that imports the models. Engine and session factory are
   now lazy (`get_engine()`, `async_session()`), pinned by
   `test_db_module_imports_without_db_config`.
2. **Bug B — `ensure_podman_secret` name/file mismatch.** Helper takes the
   podman secret name and the source filename separately; calls corrected in
   Task 4 Step 3.
3. Accepted exceptions (Postgres `type=env`, EDA reading `SECRETS_DIR`,
   production default fail-closed, demo IPA password in git) are recorded in the
   spec's Review Findings section and require no plan change, except that Task 5
   and Task 6 must ship in the same image rebuild — noted in Task 8 Step 1.

# Arbiter Hub — Phase 2 UI Design

## Intent

Build a PatternFly 6 web UI for the arbiter-hub federation attestation hub. The UI serves two personas — SOC analysts monitoring workload attestation health, and platform admins managing the fleet, policies, and backend configuration. The UI follows the freeipa-webui modern patterns exactly: React 18, TypeScript, Vite, PatternFly 6, RTK Query, Redux Toolkit.

### Why

Phase 1 delivered a working API + MCP tools. The API is fully functional (workload CRUD, attestation, KBS, audit, policies) but only accessible via curl/MCP. A visual interface is needed for:
- Real-time estate visibility (which workloads are healthy, stale, failed)
- Actionable alerts (stale TTL countdowns, failed attestation)
- Policy management without raw JSON
- Demo/customer-facing presentation of the attestation pipeline
- Federation topology visualization

### Why Now

E2E attestation pipeline is live on Beaker lab. All API endpoints working. The backend is stable enough to build a UI against.

## Personas

### SOC Analyst
- Lands on Dashboard
- Monitors workload health, reacts to state changes
- Drills into failed/stale workloads, views attestation history
- Triggers remediation or escalates
- Does NOT manage policies or register workloads
- Needs: at-a-glance health, recent events, fast drill-down

### Platform Admin
- Lands on Workloads list (estate view)
- Registers/removes workloads, configures metadata
- Creates and manages attestation policies
- Monitors backend health and cert status
- Reviews audit log for compliance
- Manages KBS secrets
- Needs: CRUD operations, bulk actions, policy editor, topology view

## Goals

- Match freeipa-webui look and feel (same PF6 components, same page patterns)
- Functional for both personas without role-based access gating
- All existing API endpoints surfaced in the UI
- State machine transitions visible and actionable
- Real-time-ish monitoring via polling (no websocket for PoC)

## Non-Goals

- Authentication/authorization (PoC uses open API)
- Mobile responsiveness (desktop-first, admin tool)
- Offline support
- i18n/l10n

## Anti-Goals

- Don't build a generic monitoring dashboard — this is attestation-specific
- Don't implement CVE backend integration yet (placeholder nav + empty states only)
- Don't add features the API doesn't support (no scheduler, no webhook config)

## Tech Stack (Decided)

Matches freeipa-webui exactly:

| Layer | Choice | Version |
|-------|--------|---------|
| Framework | React | 18.x |
| Language | TypeScript | 5.x |
| Build | Vite | 6.x |
| UI Library | PatternFly | 6.x |
| State | Redux Toolkit + RTK Query | latest |
| Router | react-router | 7.x |
| Table | @patternfly/react-table | 6.x |
| Topology | @patternfly/react-topology | 6.x |
| Icons | @patternfly/react-icons | 6.x |
| Test | Vitest + @testing-library/react | latest |
| Lint | ESLint + Prettier | latest |

## Navigation Structure

```
Arbiter Hub
├─ Dashboard
├─ Attestation
│  ├─ Workloads
│  ├─ Backends
│  └─ History
├─ Vulnerabilities (placeholder)
│  ├─ CVE Overview
│  └─ Affected Workloads
├─ Policy
│  ├─ Policies
│  └─ KBS Secrets
├─ Administration
│  ├─ Audit Log
│  └─ Federation
```

## Pages

### Dashboard

SOC analyst landing page. Four sections:

1. **State Summary** — PF donut chart showing workload count by current_state. Colors: healthy=green, registered=blue, attesting=cyan, stale=orange, failed=red, under_remediation=purple, revoked=grey. Click segment → filtered workloads list.

2. **Backend Health** — row of PF cards, one per registered backend. Shows: name, healthy/unhealthy badge, last check time, agent count (for Keylime). Cards link to Backends page.

3. **Stale Alerts** — PF alert group. Workloads approaching TTL expiry. Format: "{display_name} stale in {remaining_time}" with re-attest action button. Sorted by urgency.

4. **Recent Events** — PF data list of last 20 attestation records. Columns: timestamp, workload name, verdict badge (pass=green, fail=red, error=yellow, unavailable=grey), backend. Click → workload detail.

**Data source:** `GET /workloads`, `GET /backends`, `GET /audit?limit=20`. Poll every 30s.

### Workloads (List)

Follows freeipa-webui Hosts page pattern exactly:

- **Toolbar:** SearchInputLayout (search by display_name or ipa_principal), filter dropdowns (workload_type, current_state, backend_type), BulkSelectorPrep, kebab with bulk actions (attest selected, revoke selected), pagination
- **Table:** Columns: display_name (link to detail), ipa_principal, workload_type badge, current_state badge (colored), backend_type, last_attested_at (relative time), stale_ttl countdown
- **Add Workload** button → modal (ModalWithFormLayout):
  - ipa_principal (text, required)
  - display_name (text, required)
  - workload_type (select: agentic/cvm/service)
  - backend_type (select: keylime/trustee/cosign/rekor)
  - stale_ttl_seconds (number, default 3600)
  - metadata (key-value pairs, dynamic add/remove)
- **Delete** via kebab → confirmation modal
- **Empty state:** "No workloads registered. Register your first workload to begin attestation monitoring."

**Data source:** `GET /workloads?start_index={}&count={}`, `POST /workloads`, `DELETE /workloads/{id}`

### Workload Detail

Follows freeipa-webui host detail tab pattern:

**Header:** display_name, state badge (large, colored), ipa_principal subtitle. Action buttons: Attest (if valid transition), Remediate, Revoke — disabled/enabled based on state machine rules.

**Tabs:**

1. **Overview** — two-column layout:
   - Left: metadata key-value pairs, workload_type, backend_type, registered_at, last_attested_at, stale_ttl_seconds with countdown
   - Right: state machine diagram (7-node Mubeen). Current state highlighted (filled circle), valid transitions shown as solid arrows, invalid as dashed grey. Nodes arranged in logical flow:
     ```
     registered → attesting → healthy → stale
                                 ↓         ↓
                              failed ← ────┘
                                 ↓
                         under_remediation
                                 ↓
                              revoked
     ```

2. **Attestation History** — PF table: timestamp, verdict badge, backend, evidence_hash (truncated), detail expand. Most recent first. Pagination.

3. **State Transitions** — PF table: timestamp, from_state → to_state (with colored badges), triggered_by, justification. Timeline visualization option.

4. **Vulnerabilities** (placeholder) — empty state: "Vulnerability scanning not configured. Connect a CVE data source to view workload vulnerability status."

**Data source:** `GET /workloads/{id}`, `POST /workloads/{id}/attest`, `POST /workloads/{id}/remediate`, `POST /workloads/{id}/revoke`

### Backends

PF card grid (not table — visual, like a status board):

Each card:
- Backend name + type icon
- Health status: green check / red X
- Last check timestamp
- Detail string (e.g., "verifier reachable, 1 agents")
- Cert expiry info (if available from API — may need new endpoint)
- Link to workloads filtered by this backend

**Data source:** `GET /backends`. Poll every 30s.

### History

Global attestation records — all workloads:

- **Toolbar:** date range picker, filter by verdict, filter by workload, search
- **Table:** timestamp, workload display_name (link), backend, verdict badge, evidence_hash, detail expandable row
- **Export CSV** button in toolbar
- Pagination

**Data source:** `GET /audit` (attestation events filtered from audit log — may need dedicated endpoint or query param)

### Policies

CRUD table following freeipa-webui pattern:

- **Table:** name (link to detail), policy_type, scope, active (toggle), created_by, created_at
- **Add Policy** modal:
  - name (text, required)
  - policy_type (select)
  - scope (text, optional)
  - policy_content (code editor — PF CodeEditor or textarea with JSON validation)
  - active (toggle, default true)
- **Policy Detail** page: full policy_content rendered as formatted JSON, edit button, deactivate button
- **Empty state:** "No policies defined. Create a policy to enforce attestation requirements."

**Data source:** `GET /policies`, `POST /policies`

### KBS Secrets

Table with store/retrieve actions:

- **Table:** repo, secret_type, tag, required_state badge, workload_scope, created_by, created_at, rotated_at
- **Store Secret** modal:
  - repo (text)
  - secret_type (text)
  - tag (text)
  - value (textarea, masked)
  - required_state (select from WorkloadState)
  - workload_scope (text, optional)
- Retrieve button → shows value in modal (if workload in required state)

**Data source:** `POST /kbs/v0/resource/{repo}/{type}/{tag}`, `GET /kbs/v0/resource/{repo}/{type}/{tag}`

### Audit Log

Searchable log table:

- **Toolbar:** search (actor, action), date range, filter by action type
- **Table:** timestamp, actor, actor_type badge, action, target_type, target_id (link if workload), detail expandable
- **Export CSV** button
- Pagination

**Data source:** `GET /audit`

### Federation (Topology)

PF react-topology graph visualization:

- **Nodes:** workloads (colored by state) and backends (colored by health)
- **Edges:** workload → backend (attestation relationship)
- **Layout:** force-directed or dagre
- **Interactions:** click node → sidebar with details, zoom/pan, filter by state
- **Legend:** state colors, backend types

This is the showpiece for demos — visualizes the federation trust graph.

**Data source:** `GET /workloads`, `GET /backends` combined

### Vulnerabilities (Placeholder)

Two sub-pages, both showing empty states:

- **CVE Overview:** "Vulnerability monitoring coming soon. This page will show estate-wide CVE exposure across all attested workloads."
- **Affected Workloads:** "Connect a CVE data source to map vulnerabilities to workloads."

Nav section visible but pages non-functional. Architecture accommodates future `GET /workloads/{id}/vulnerabilities` and `GET /vulnerabilities` endpoints.

## State Machine UI Spec

The Mubeen 7-state machine is central to the UX. Each state maps to a visual treatment:

| State | Color | PF Status | Badge |
|-------|-------|-----------|-------|
| registered | blue | info | outline |
| attesting | cyan | info | solid |
| healthy | green | success | solid |
| stale | orange | warning | solid |
| failed | red | danger | solid |
| under_remediation | purple | custom | solid |
| revoked | grey | default | solid |

**Valid transitions (determines which action buttons are enabled):**

| From | Allowed Actions |
|------|----------------|
| registered | attest |
| attesting | (automatic → healthy or failed) |
| healthy | (automatic → stale via TTL) |
| stale | attest |
| failed | remediate, revoke |
| under_remediation | attest, revoke |
| revoked | (terminal) |

## RTK Query Services Structure

Following freeipa-webui `src/services/rpc*.ts` pattern:

```
src/services/
├─ api.ts              # createApi base with fetchBaseQuery to :8400
├─ rpcWorkloads.ts     # workload CRUD + attest/remediate/revoke
├─ rpcBackends.ts      # backend health
├─ rpcPolicies.ts      # policy CRUD
├─ rpcAudit.ts         # audit log
├─ rpcKBS.ts           # KBS store/retrieve
├─ rpcHealth.ts        # /health endpoint
```

Base API:
```typescript
export const api = createApi({
  reducerPath: 'arbiterApi',
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  tagTypes: ['Workload', 'Policy', 'Backend', 'Audit', 'KBSSecret'],
  endpoints: () => ({}),
});
```

Each service file injects endpoints into the base API (code-split pattern from freeipa-webui).

## Redux Store Structure

```
src/store/
├─ store.ts
├─ hooks.ts            # useAppDispatch, useAppSelector
├─ Global/
│  ├─ alerts-slice.ts  # toast notifications
│  ├─ routes-slice.ts  # active page, breadcrumbs, browser title
│  └─ dashboard-slice.ts  # polling state, refresh interval
```

## Project Structure

```
ui/
├─ index.html
├─ package.json
├─ vite.config.ts
├─ tsconfig.json
├─ src/
│  ├─ main.tsx
│  ├─ App.tsx
│  ├─ AppLayout.tsx
│  ├─ main.css
│  ├─ navigation/
│  │  ├─ Nav.tsx
│  │  └─ NavRoutes.ts
│  ├─ pages/
│  │  ├─ Dashboard/
│  │  ├─ Workloads/
│  │  ├─ WorkloadDetail/
│  │  ├─ Backends/
│  │  ├─ History/
│  │  ├─ Policies/
│  │  ├─ PolicyDetail/
│  │  ├─ KBSSecrets/
│  │  ├─ AuditLog/
│  │  ├─ Federation/
│  │  └─ Vulnerabilities/
│  ├─ components/
│  │  ├─ StateBadge.tsx
│  │  ├─ VerdictBadge.tsx
│  │  ├─ StateMachineDiagram.tsx
│  │  ├─ TTLCountdown.tsx
│  │  ├─ layouts/           # TitleLayout, ToolbarLayout, etc.
│  │  └─ modals/
│  ├─ services/
│  ├─ store/
│  └─ utils/
│     └─ datatypes/
│        └─ globalDataTypes.ts
├─ deploy/
│  └─ containerfiles/
│     └─ Containerfile.ui
```

## Branding

- **Product name:** "Red Hat Arbiter" in all text references
- **Logo:** Red Hat hat logo in masthead (same placement as freeipa-webui IpaLogo)
- **Source:** Use SVG from `~/.claude/skills/powerpoint/redhat-assets/` or Red Hat icons repo

## Container Deployment

New Quadlet: `arbiter-hub-ui` on port 8443, nginx serving static build, proxying `/api` to arbiter-hub-api:8400.

## Backend Additions Required

The following small API changes are needed to support the UI:

1. **`GET /kbs/v0/resources`** — list all KBS secrets (metadata only, not values). Required for KBS Secrets table page.
2. **`GET /workloads/{id}/transitions`** — list state transitions for a workload. Required for State Transitions tab on Workload Detail.
3. **`DELETE /workloads/{id}`** — delete a workload. Required for workload removal from estate.
4. **Fix `POST /workloads/{id}/attest`** — allow attestation from `UNDER_REMEDIATION` state (currently only allows REGISTERED, STALE, ATTESTING).
5. **Fix `GET /policies`** — return all policies (active + inactive), not just active. Required for admin toggle functionality.
6. **Audit filtering** — client-side filtering for PoC (no new query params needed).

## Constraints

- API proxy via Vite dev server (dev) / nginx (prod) — UI never calls API directly by port
- Polling interval configurable (default 30s for dashboard, 60s for lists)
- PF6 dark mode support via ThemeContext (same pattern as freeipa-webui)
- All tables must support: search (by key text fields), filter dropdowns (by categorical fields like state/type/verdict), sortable columns (click column header to toggle asc/desc), pagination, bulk select
- All forms must validate client-side before submit
- Loading states: skeleton screens for initial load, spinner for actions
- Error states: inline for forms, toast for actions, full-page for fatal

## What's Left to the Builder

- Exact PF component choices for policy editor (CodeEditor vs textarea)
- Topology graph layout algorithm (force-directed vs dagre — test both)
- Dashboard polling implementation (RTK Query polling vs custom interval)
- Vite proxy config details
- Test coverage targets
- Exact breakpoints for card grid responsive behavior on Backends page

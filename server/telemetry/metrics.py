from prometheus_client import Counter, Histogram, Gauge

ATTESTATION_COUNTER = Counter(
    "arbiter_attestations_total",
    "Total attestation verifications",
    ["backend", "verdict", "workload_type"],
)

STATE_TRANSITION_COUNTER = Counter(
    "arbiter_state_transitions_total",
    "Total workload state transitions",
    ["from_state", "to_state"],
)

ATTESTATION_DURATION = Histogram(
    "arbiter_attestation_duration_seconds",
    "Time to complete attestation verification",
    ["backend"],
)

KBS_RELEASE_COUNTER = Counter(
    "arbiter_kbs_releases_total",
    "Total KBS secret releases",
    ["repo", "result"],
)

BACKEND_HEALTH_GAUGE = Gauge(
    "arbiter_backend_health",
    "Backend health status (1=healthy, 0=unhealthy)",
    ["backend"],
)

WORKLOADS_BY_STATE = Gauge(
    "arbiter_workloads_by_state",
    "Number of workloads in each state",
    ["state", "workload_type"],
)

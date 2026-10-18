export enum WorkloadType {
  AGENTIC = "agentic",
  CVM = "cvm",
  SERVICE = "service",
}

export enum WorkloadState {
  REGISTERED = "registered",
  ATTESTING = "attesting",
  HEALTHY = "healthy",
  STALE = "stale",
  FAILED = "failed",
  UNDER_REMEDIATION = "under_remediation",
  REVOKED = "revoked",
}

export enum BackendType {
  KEYLIME = "keylime",
  TRUSTEE = "trustee",
  COSIGN = "cosign",
  REKOR = "rekor",
}

export enum AttestationVerdict {
  PASS = "pass",
  FAIL = "fail",
  ERROR = "error",
  UNAVAILABLE = "unavailable",
}

export interface Workload {
  id: string;
  ipa_principal: string;
  display_name: string;
  workload_type: WorkloadType;
  current_state: WorkloadState;
  backend_type: BackendType;
  stale_ttl_seconds: number;
  registered_at: string;
  last_attested_at: string | null;
  metadata: Record<string, unknown>;
}

export interface AttestationRecord {
  id: string;
  workload_id: string;
  backend: BackendType;
  verdict: AttestationVerdict;
  evidence_hash: string | null;
  policy_hash: string | null;
  detail: Record<string, unknown>;
  rekor_entry_uuid: string | null;
  created_at: string;
}

export interface StateTransition {
  id: string;
  workload_id: string;
  from_state: WorkloadState;
  to_state: WorkloadState;
  triggered_by: string;
  justification: string | null;
  rekor_entry_uuid: string | null;
  created_at: string;
}

export interface Policy {
  id: string;
  name: string;
  policy_type: string;
  policy_content: Record<string, unknown>;
  scope: string | null;
  active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AuditLogEntry {
  id: string;
  actor: string;
  actor_type: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface KBSSecret {
  id: string;
  repo: string;
  secret_type: string;
  tag: string;
  required_state: WorkloadState;
  workload_scope: string | null;
  created_by: string;
  created_at: string;
  rotated_at: string | null;
}

export interface BackendHealth {
  name: string;
  backend_type: BackendType;
  healthy: boolean;
  detail: string;
  agent_count?: number;
  last_check?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  start_index: number;
  count: number;
}

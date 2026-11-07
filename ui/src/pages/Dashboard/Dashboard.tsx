import React from "react";
import {
  PageSection,
  Grid,
  GridItem,
  Card,
  CardTitle,
  CardBody,
  Alert,
  AlertGroup,
  Label,
  AlertActionLink,
  DataList,
  DataListItem,
  DataListItemRow,
  DataListItemCells,
  DataListCell,
  EmptyState,
  EmptyStateBody,
  Icon,
  Button,
  Flex,
  FlexItem,
} from "@patternfly/react-core";
import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  CubesIcon,
} from "@patternfly/react-icons";
import { useNavigate } from "react-router-dom";
import TitleLayout from "src/components/layouts/TitleLayout";
import StateBadge from "src/components/StateBadge";

import DataSpinner from "src/components/DataSpinner";
import { useGetWorkloadsQuery } from "src/services/rpcWorkloads";
import { useGetBackendsQuery } from "src/services/rpcBackends";
import { useGetAuditQuery } from "src/services/rpcAudit";
import { useGetHealthQuery } from "src/services/rpcHealth";
import {
  WorkloadState,
} from "src/utils/datatypes/globalDataTypes";
import type { Workload } from "src/utils/datatypes/globalDataTypes";

const STATE_ORDER = [
  WorkloadState.HEALTHY,
  WorkloadState.REGISTERED,
  WorkloadState.ATTESTING,
  WorkloadState.STALE,
  WorkloadState.FAILED,
  WorkloadState.UNDER_REMEDIATION,
  WorkloadState.REVOKED,
];

const ATTENTION_STATES = [
  WorkloadState.FAILED,
  WorkloadState.STALE,
  WorkloadState.UNDER_REMEDIATION,
  WorkloadState.REGISTERED,
];

const PRIORITY_ORDER: Record<string, number> = {
  [WorkloadState.FAILED]: 0,
  [WorkloadState.STALE]: 1,
  [WorkloadState.UNDER_REMEDIATION]: 2,
  [WorkloadState.REGISTERED]: 3,
};

function stateReason(state: WorkloadState): string {
  switch (state) {
    case WorkloadState.FAILED:
      return "Evidence did not meet policy — blocked from proceeding";
    case WorkloadState.STALE:
      return "No successful attestation within the stale threshold";
    case WorkloadState.UNDER_REMEDIATION:
      return "Workload is under active remediation";
    case WorkloadState.REGISTERED:
      return "Registered but not yet attested — needs first attestation";
    default:
      return "";
  }
}

function stateAction(state: WorkloadState): string {
  switch (state) {
    case WorkloadState.FAILED:
      return "Investigate";
    case WorkloadState.STALE:
      return "Re-attest";
    case WorkloadState.UNDER_REMEDIATION:
      return "View";
    case WorkloadState.REGISTERED:
      return "Attest";
    default:
      return "View";
  }
}

function countByState(
  items: Workload[]
): Record<WorkloadState, number> {
  const counts = {} as Record<WorkloadState, number>;
  for (const s of Object.values(WorkloadState)) {
    counts[s] = 0;
  }
  for (const w of items) {
    counts[w.current_state] = (counts[w.current_state] || 0) + 1;
  }
  return counts;
}

function getStaleWorkloads(items: Workload[]): Workload[] {
  const now = Date.now();
  return items.filter((w) => {
    if (w.current_state === WorkloadState.STALE) return true;
    if (
      w.current_state === WorkloadState.HEALTHY &&
      w.last_attested_at
    ) {
      const elapsed =
        (now - new Date(w.last_attested_at).getTime()) / 1000;
      const remaining = w.stale_ttl_seconds - elapsed;
      return remaining < 900 && remaining > 0;
    }
    return false;
  });
}

function formatRelativeTime(dateStr: string): string {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const kpiCardStyle: React.CSSProperties = {
  textAlign: "center",
  cursor: "pointer",
  padding: "20px 16px",
};

const kpiMetricStyle = (color: string): React.CSSProperties => ({
  fontSize: "32px",
  fontWeight: 700,
  color,
  lineHeight: 1.2,
});

const kpiLabelStyle: React.CSSProperties = {
  fontSize: "13px",
  color: "#4f5255",
  marginTop: "4px",
};

const sectionHeadStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "12px",
  marginTop: "24px",
};

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const {
    data: workloadsData,
    isLoading: wlLoading,
    isError: wlError,
  } = useGetWorkloadsQuery({ count: 100 }, { pollingInterval: 30000 });
  const {
    data: backendsData,
    isLoading: beLoading,
  } = useGetBackendsQuery(undefined, { pollingInterval: 30000 });
  const {
    data: auditData,
    isLoading: auLoading,
    isError: auError,
  } = useGetAuditQuery({ count: 20 }, { pollingInterval: 30000 });
  const {
    data: healthData,
    isError: healthError,
  } = useGetHealthQuery(undefined, { pollingInterval: 15000 });

  if (wlLoading || beLoading || auLoading) {
    return (
      <PageSection>
        <DataSpinner />
      </PageSection>
    );
  }

  const workloads = workloadsData?.items ?? [];
  const stateCounts = countByState(workloads);
  const staleWorkloads = getStaleWorkloads(workloads);
  const backends = backendsData ?? {};
  const auditItems = auditData?.items ?? [];

  const total = workloads.length;
  const healthyCount = stateCounts[WorkloadState.HEALTHY] || 0;
  const attentionCount =
    (stateCounts[WorkloadState.STALE] || 0) +
    (stateCounts[WorkloadState.REGISTERED] || 0) +
    (stateCounts[WorkloadState.UNDER_REMEDIATION] || 0);
  const blockedCount = stateCounts[WorkloadState.FAILED] || 0;
  const coverage = total > 0 ? Math.round((healthyCount / total) * 100) : 0;

  const backendEntries = Object.entries(backends);
  const backendHealthy = backendEntries.filter(([, info]) => info.healthy).length;
  const backendHealthPct = backendEntries.length > 0
    ? Math.round((backendHealthy / backendEntries.length) * 100)
    : 0;

  const decisionQueue = workloads
    .filter((w) => ATTENTION_STATES.includes(w.current_state))
    .sort((a, b) => (PRIORITY_ORDER[a.current_state] ?? 9) - (PRIORITY_ORDER[b.current_state] ?? 9));

  return (
    <PageSection>
      <TitleLayout
        title="Dashboard"
        description="Federated workload trust at a glance — posture, decision queue, backend health, and recent activity."
      />

      {/* KPI Cards */}
      <Grid hasGutter>
        <GridItem span={3}>
          <Card isClickable onClick={() => navigate("/workloads?state=healthy")} style={kpiCardStyle}>
            <CardBody>
              <div style={kpiMetricStyle("#3e8635")}>{healthyCount}</div>
              <div style={kpiLabelStyle}>Healthy workloads</div>
            </CardBody>
          </Card>
        </GridItem>
        <GridItem span={3}>
          <Card isClickable onClick={() => navigate("/workloads?state=stale")} style={kpiCardStyle}>
            <CardBody>
              <div style={kpiMetricStyle("#f0ab00")}>{attentionCount}</div>
              <div style={kpiLabelStyle}>Needs attention</div>
            </CardBody>
          </Card>
        </GridItem>
        <GridItem span={3}>
          <Card isClickable onClick={() => navigate("/workloads?state=failed")} style={kpiCardStyle}>
            <CardBody>
              <div style={kpiMetricStyle("#c9190b")}>{blockedCount}</div>
              <div style={kpiLabelStyle}>Blocked</div>
            </CardBody>
          </Card>
        </GridItem>
        <GridItem span={3}>
          <Card isClickable onClick={() => navigate("/backends")} style={kpiCardStyle}>
            <CardBody>
              <div style={kpiMetricStyle(backendHealthPct >= 80 ? "#3e8635" : "#c9190b")}>
                {backendHealthPct}%
              </div>
              <div style={kpiLabelStyle}>Backend health</div>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>

      {/* Cluster Status */}
      <div style={{ marginTop: "24px" }}>
        <Card>
          <CardTitle>Cluster Status</CardTitle>
          <CardBody>
            {healthError ? (
              <Alert variant="danger" title="API Unreachable" isInline>
                Cannot connect to the Arbiter Hub API. Check that the API container is running.
              </Alert>
            ) : healthData ? (
              <div style={{ display: "flex", gap: "24px", alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <Icon status={healthData.status === "ok" ? "success" : "danger"}>
                    {healthData.status === "ok" ? <CheckCircleIcon /> : <ExclamationCircleIcon />}
                  </Icon>
                  <strong>API Node: {healthData.node_id}</strong>
                </div>
                <div>Version: {healthData.version}</div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <Icon status={healthData.backends_healthy ? "success" : "danger"}>
                    {healthData.backends_healthy ? <CheckCircleIcon /> : <ExclamationCircleIcon />}
                  </Icon>
                  {healthData.backend_count} backend{healthData.backend_count !== 1 ? "s" : ""} connected
                </div>
              </div>
            ) : (
              <div>Checking cluster health...</div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Trust Coverage */}
      <div style={sectionHeadStyle}>
        <div>
          <div style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "#6a6e73" }}>Fleet metric</div>
          <h2 style={{ margin: "4px 0 2px", fontSize: "18px" }}>Trust coverage</h2>
          <p style={{ margin: 0, fontSize: "13px", color: "#4f5255" }}>
            Share of workloads with current, policy-compliant evidence.
          </p>
        </div>
        <Label color={coverage >= 90 ? "green" : "orange"} isCompact>
          {coverage >= 90 ? "On target" : "Needs attention"}
        </Label>
      </div>
      <Card>
        <CardBody>
          <Grid hasGutter>
            <GridItem span={6}>
              <div style={{ fontSize: "48px", fontWeight: 700, color: coverage >= 90 ? "#3e8635" : "#c9190b" }}>
                {coverage}%
              </div>
              <div style={{
                height: "8px",
                borderRadius: "4px",
                background: "#d2d2d2",
                marginTop: "8px",
                overflow: "hidden",
              }}>
                <div style={{
                  height: "100%",
                  width: `${coverage}%`,
                  borderRadius: "4px",
                  background: coverage >= 90 ? "#3e8635" : "#c9190b",
                  transition: "width 0.3s",
                }} />
              </div>
              <p style={{ marginTop: "8px", fontSize: "13px", color: "#4f5255" }}>
                <strong>{healthyCount} of {total}</strong> workloads verified · target 90%
              </p>
            </GridItem>
            <GridItem span={6}>
              <div style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "#6a6e73", marginBottom: "8px" }}>
                Workload states
              </div>
              {wlError ? (
                <Alert variant="warning" title="Could not load workloads" isInline />
              ) : workloads.length === 0 ? (
                <EmptyState
                  titleText="No workloads registered"
                  icon={CubesIcon}
                  headingLevel="h4"
                >
                  <EmptyStateBody>
                    Register your first workload to begin attestation monitoring.
                  </EmptyStateBody>
                </EmptyState>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
                  {STATE_ORDER.map((state) => (
                    <div
                      key={state}
                      onClick={() => navigate(`/workloads?state=${state}`)}
                      style={{
                        cursor: "pointer",
                        textAlign: "center",
                        padding: "8px 12px",
                        borderRadius: "8px",
                        border: "1px solid #e7e7e7",
                        background: "#fafafa",
                        minWidth: "64px",
                      }}
                    >
                      <div style={{ fontSize: "20px", fontWeight: 600 }}>
                        {stateCounts[state]}
                      </div>
                      <StateBadge state={state} />
                    </div>
                  ))}
                </div>
              )}
            </GridItem>
          </Grid>
        </CardBody>
      </Card>

      {/* Decision Queue */}
      <div style={sectionHeadStyle}>
        <div>
          <h2 style={{ margin: "0 0 2px", fontSize: "18px" }}>Decision queue</h2>
          <p style={{ margin: 0, fontSize: "13px", color: "#4f5255" }}>
            Workloads that need an operator decision — attest, remediate, or investigate.
          </p>
        </div>
        <Button variant="link" onClick={() => navigate("/workloads")}>
          All Workloads
        </Button>
      </div>
      <Card>
        <CardBody>
          {decisionQueue.length === 0 ? (
            <div style={{ textAlign: "center", padding: "24px", color: "#4f5255" }}>
              No Workload objects need attention.
            </div>
          ) : (
            <div style={{ display: "grid", gap: "12px" }}>
              {decisionQueue.map((w) => (
                <div
                  key={w.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "12px 16px",
                    borderRadius: "8px",
                    border: "1px solid #e7e7e7",
                    background: "#fafafa",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "#6a6e73" }}>
                      Workload
                    </div>
                    <strong
                      onClick={() => navigate(`/workloads/${w.id}`)}
                      style={{ cursor: "pointer", color: "#0066cc" }}
                    >
                      {w.display_name}
                    </strong>
                    <div style={{ fontSize: "13px", color: "#4f5255", marginTop: "4px" }}>
                      {stateReason(w.current_state)}
                    </div>
                  </div>
                  <Flex alignItems={{ default: "alignItemsCenter" }} spaceItems={{ default: "spaceItemsMd" }}>
                    <FlexItem>
                      <StateBadge state={w.current_state} />
                    </FlexItem>
                    <FlexItem>
                      <Button
                        variant={w.current_state === WorkloadState.FAILED ? "danger" : "secondary"}
                        size="sm"
                        onClick={() => navigate(`/workloads/${w.id}`)}
                      >
                        {stateAction(w.current_state)}
                      </Button>
                    </FlexItem>
                  </Flex>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {/* System Readiness */}
      <div style={sectionHeadStyle}>
        <div>
          <h2 style={{ margin: "0 0 2px", fontSize: "18px" }}>System readiness</h2>
          <p style={{ margin: 0, fontSize: "13px", color: "#4f5255" }}>
            Policy and backend status that gate trust decisions.
          </p>
        </div>
      </div>
      <Grid hasGutter>
        <GridItem span={4}>
          <Card>
            <CardBody>
              <div style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "#6a6e73" }}>
                Policy
              </div>
              <h3 style={{ margin: "4px 0 8px", fontSize: "16px" }}>production-attestation</h3>
              <p style={{ fontSize: "13px", color: "#4f5255", margin: "0 0 12px" }}>
                Enforce · fail restricts · unable-to-verify holds.
              </p>
              <Label color="green" isCompact>Active</Label>
              <div style={{ marginTop: "12px" }}>
                <Button variant="link" size="sm" onClick={() => navigate("/policies")}>
                  Open Policies
                </Button>
              </div>
            </CardBody>
          </Card>
        </GridItem>
        <GridItem span={4}>
          <Card>
            <CardBody>
              <div style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "#6a6e73" }}>
                Backend
              </div>
              <h3 style={{ margin: "4px 0 8px", fontSize: "16px" }}>
                {backendEntries.length > 0
                  ? backendEntries.map(([name]) => name).join(" · ")
                  : "No backends"}
              </h3>
              <p style={{ fontSize: "13px", color: "#4f5255", margin: "0 0 12px" }}>
                Federated attestation backends for evaluation.
              </p>
              <Label color={backendHealthPct >= 80 ? "green" : "red"} isCompact>
                {backendHealthPct >= 80 ? "Healthy" : "Degraded"}
              </Label>
              <div style={{ marginTop: "12px" }}>
                <Button variant="link" size="sm" onClick={() => navigate("/backends")}>
                  Open Backends
                </Button>
              </div>
            </CardBody>
          </Card>
        </GridItem>
        <GridItem span={4}>
          <Card>
            <CardBody>
              <div style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "#6a6e73" }}>
                Evidence
              </div>
              <h3 style={{ margin: "4px 0 8px", fontSize: "16px" }}>Recent activity</h3>
              <p style={{ fontSize: "13px", color: "#4f5255", margin: "0 0 12px" }}>
                Decision records and audit events for the fleet.
              </p>
              <Label color="blue" isCompact>Traceable</Label>
              <div style={{ marginTop: "12px" }}>
                <Button variant="link" size="sm" onClick={() => navigate("/audit")}>
                  Open Audit log
                </Button>
              </div>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>

      {/* Stale Alerts */}
      {staleWorkloads.length > 0 && (
        <div style={{ marginTop: "24px" }}>
          <Card>
            <CardTitle>Stale Alerts</CardTitle>
            <CardBody>
              <AlertGroup>
                {staleWorkloads.map((w) => (
                  <Alert
                    key={w.id}
                    variant="warning"
                    title={`${w.display_name} is stale or approaching TTL`}
                    actionLinks={
                      <AlertActionLink
                        onClick={() => navigate(`/workloads/${w.id}`)}
                      >
                        View
                      </AlertActionLink>
                    }
                  />
                ))}
              </AlertGroup>
            </CardBody>
          </Card>
        </div>
      )}

      {/* Recent Events */}
      <div style={sectionHeadStyle}>
        <div>
          <div style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "#6a6e73" }}>
            Recent evidence activity
          </div>
          <h2 style={{ margin: "4px 0 0", fontSize: "18px" }}>Latest Events</h2>
        </div>
        <Button variant="link" onClick={() => navigate("/audit")}>
          All Events
        </Button>
      </div>
      <Card>
        <CardBody>
          {auError ? (
            <Alert variant="warning" title="Could not load events" isInline />
          ) : auditItems.length === 0 ? (
            <div>No recent events.</div>
          ) : (
            <DataList aria-label="Recent events" isCompact>
              {auditItems.slice(0, 10).map((event) => (
                <DataListItem key={event.id}>
                  <DataListItemRow>
                    <DataListItemCells
                      dataListCells={[
                        <DataListCell key="time" width={1}>
                          {formatRelativeTime(event.created_at)}
                        </DataListCell>,
                        <DataListCell key="transition" width={2}>
                          {event.detail &&
                          typeof event.detail === "object" &&
                          "from" in event.detail &&
                          "to" in event.detail ? (
                            <span>
                              <StateBadge state={event.detail.from as WorkloadState} />{" "}
                              <span style={{ margin: "0 4px" }}>&rarr;</span>{" "}
                              <StateBadge state={event.detail.to as WorkloadState} />
                            </span>
                          ) : (
                            event.action
                          )}
                        </DataListCell>,
                        <DataListCell key="actor" width={1}>
                          {event.actor === "falco_alert" ? (
                            <Label color="orange" isCompact>falco</Label>
                          ) : event.actor === "attestation_result" ? (
                            <Label color="blue" isCompact>attest</Label>
                          ) : (
                            <span style={{ fontSize: "13px" }}>{event.actor}</span>
                          )}
                        </DataListCell>,
                        <DataListCell key="detail" width={3}>
                          <span style={{ fontSize: "13px", color: "#4f5255" }}>
                            {event.detail &&
                            typeof event.detail === "object" &&
                            "justification" in event.detail &&
                            event.detail.justification
                              ? String(event.detail.justification).length > 80
                                ? String(event.detail.justification).slice(0, 80) + "..."
                                : String(event.detail.justification)
                              : event.detail &&
                                typeof event.detail === "object" &&
                                "verdict" in event.detail
                              ? String(event.detail.verdict)
                              : ""}
                          </span>
                        </DataListCell>,
                      ]}
                    />
                  </DataListItemRow>
                </DataListItem>
              ))}
            </DataList>
          )}
        </CardBody>
      </Card>
    </PageSection>
  );
};

export default Dashboard;

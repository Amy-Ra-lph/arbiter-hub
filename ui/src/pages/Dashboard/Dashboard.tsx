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
  AlertActionLink,
  DataList,
  DataListItem,
  DataListItemRow,
  DataListItemCells,
  DataListCell,
  EmptyState,
  EmptyStateBody,
  Icon,
} from "@patternfly/react-core";
import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  CubesIcon,
} from "@patternfly/react-icons";
import { useNavigate } from "react-router-dom";
import TitleLayout from "src/components/layouts/TitleLayout";
import StateBadge from "src/components/StateBadge";
import VerdictBadge from "src/components/VerdictBadge";
import DataSpinner from "src/components/DataSpinner";
import { useGetWorkloadsQuery } from "src/services/rpcWorkloads";
import { useGetBackendsQuery } from "src/services/rpcBackends";
import { useGetAuditQuery } from "src/services/rpcAudit";
import { useGetHealthQuery } from "src/services/rpcHealth";
import {
  WorkloadState,
  AttestationVerdict,
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

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const {
    data: workloadsData,
    isLoading: wlLoading,
  } = useGetWorkloadsQuery({ count: 100 }, { pollingInterval: 30000 });
  const {
    data: backendsData,
    isLoading: beLoading,
  } = useGetBackendsQuery(undefined, { pollingInterval: 30000 });
  const {
    data: auditData,
    isLoading: auLoading,
  } = useGetAuditQuery({ count: 20 }, { pollingInterval: 30000 });
  const {
    data: healthData,
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

  return (
    <PageSection>
      <TitleLayout
        title="Dashboard"
        description="Federation attestation estate overview"
      />

      <Grid hasGutter>
        {/* Cluster Status */}
        <GridItem span={12}>
          <Card>
            <CardTitle>Cluster Status</CardTitle>
            <CardBody>
              {healthData ? (
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
        </GridItem>

        {/* State Summary */}
        <GridItem span={6}>
          <Card>
            <CardTitle>Workload States</CardTitle>
            <CardBody>
              {workloads.length === 0 ? (
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
                      style={{ cursor: "pointer", textAlign: "center" }}
                    >
                      <div style={{ fontSize: "24px", fontWeight: 600 }}>
                        {stateCounts[state]}
                      </div>
                      <StateBadge state={state} />
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </GridItem>

        {/* Backend Health */}
        <GridItem span={6}>
          <Card>
            <CardTitle>Backend Health</CardTitle>
            <CardBody>
              {Object.keys(backends).length === 0 ? (
                <EmptyState
                  titleText="No backends configured"
                  headingLevel="h4"
                />
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
                  {Object.entries(backends).map(([name, info]) => (
                    <Card key={name} isCompact style={{ minWidth: "180px" }}>
                      <CardBody>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <Icon
                            status={info.healthy ? "success" : "danger"}
                          >
                            {info.healthy ? (
                              <CheckCircleIcon />
                            ) : (
                              <ExclamationCircleIcon />
                            )}
                          </Icon>
                          <strong>{name}</strong>
                        </div>
                        <div style={{ fontSize: "12px", marginTop: "4px" }}>
                          {info.detail}
                        </div>
                      </CardBody>
                    </Card>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </GridItem>

        {/* Stale Alerts */}
        <GridItem span={12}>
          <Card>
            <CardTitle>Stale Alerts</CardTitle>
            <CardBody>
              {staleWorkloads.length === 0 ? (
                <div>No stale or near-stale workloads.</div>
              ) : (
                <AlertGroup>
                  {staleWorkloads.map((w) => (
                    <Alert
                      key={w.id}
                      variant="warning"
                      title={`${w.display_name} is stale or approaching TTL`}
                      actionLinks={
                        <AlertActionLink
                          onClick={() =>
                            navigate(`/workloads/${w.id}`)
                          }
                        >
                          View
                        </AlertActionLink>
                      }
                    />
                  ))}
                </AlertGroup>
              )}
            </CardBody>
          </Card>
        </GridItem>

        {/* Recent Events */}
        <GridItem span={12}>
          <Card>
            <CardTitle>Recent Events</CardTitle>
            <CardBody>
              {auditItems.length === 0 ? (
                <div>No recent events.</div>
              ) : (
                <DataList aria-label="Recent events">
                  {auditItems.slice(0, 20).map((event) => (
                    <DataListItem key={event.id}>
                      <DataListItemRow>
                        <DataListItemCells
                          dataListCells={[
                            <DataListCell key="time" width={1}>
                              {formatRelativeTime(event.created_at)}
                            </DataListCell>,
                            <DataListCell key="action" width={2}>
                              {event.action}
                            </DataListCell>,
                            <DataListCell key="actor" width={2}>
                              {event.actor}
                            </DataListCell>,
                            <DataListCell key="verdict" width={1}>
                              {event.detail &&
                              typeof event.detail === "object" &&
                              "verdict" in event.detail ? (
                                <VerdictBadge
                                  verdict={
                                    event.detail
                                      .verdict as AttestationVerdict
                                  }
                                />
                              ) : (
                                event.target_type ?? ""
                              )}
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
        </GridItem>
      </Grid>
    </PageSection>
  );
};

export default Dashboard;

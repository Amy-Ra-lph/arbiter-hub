import React, { useMemo } from "react";
import {
  PageSection,
  Card,
  CardBody,
  Alert,
  Button,
  EmptyState,
  EmptyStateBody,
} from "@patternfly/react-core";
import { CheckCircleIcon } from "@patternfly/react-icons";
import { useNavigate } from "react-router-dom";
import TitleLayout from "src/components/layouts/TitleLayout";
import DataSpinner from "src/components/DataSpinner";
import StateBadge from "src/components/StateBadge";
import { useGetWorkloadsQuery, useAttestWorkloadMutation } from "src/services/rpcWorkloads";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";
import type { Workload } from "src/utils/datatypes/globalDataTypes";

const PRIORITY_ORDER: WorkloadState[] = [
  WorkloadState.FAILED,
  WorkloadState.STALE,
  WorkloadState.UNDER_REMEDIATION,
  WorkloadState.REGISTERED,
];

function impactLabel(state: WorkloadState): string {
  switch (state) {
    case WorkloadState.FAILED: return "Blocked from proceeding";
    case WorkloadState.STALE: return "Cannot treat as verified until new evidence";
    case WorkloadState.UNDER_REMEDIATION: return "Active recovery in progress";
    case WorkloadState.REGISTERED: return "No first attestation yet";
    default: return "Needs attention";
  }
}

const Remediation: React.FC = () => {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useGetWorkloadsQuery({ count: 100 }, { pollingInterval: 15000 });
  const [attestWorkload] = useAttestWorkloadMutation();

  const queue = useMemo(() => {
    const items = (data?.items ?? []).filter((w: Workload) =>
      PRIORITY_ORDER.includes(w.current_state)
    );
    return items.sort(
      (a: Workload, b: Workload) =>
        PRIORITY_ORDER.indexOf(a.current_state) - PRIORITY_ORDER.indexOf(b.current_state)
    );
  }, [data]);

  if (isLoading) return <PageSection><DataSpinner /></PageSection>;

  return (
    <PageSection>
      <TitleLayout title="Remediation" description="Actions on Workloads that restore a verified trust state." />

      {isError && <Alert variant="warning" title="Could not load workloads" isInline style={{ marginBottom: 16 }} />}

      <Alert
        variant="info"
        title="Each item is a Workload needing an action. Mutation actions require Operator or Administrator role."
        isInline
        isPlain
        style={{ marginBottom: 16 }}
      />

      {queue.length === 0 ? (
        <Card>
          <CardBody>
            <EmptyState
              titleText="No remediation needed"
              icon={CheckCircleIcon}
              headingLevel="h4"
            >
              <EmptyStateBody>
                All Workloads are healthy or already attesting.
              </EmptyStateBody>
              <Button variant="link" onClick={() => navigate("/workloads")}>View Workloads</Button>
            </EmptyState>
          </CardBody>
        </Card>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {queue.map((w: Workload) => (
            <Card key={w.id}>
              <CardBody>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", color: "var(--pf-t--global--text--color--subtle)", marginBottom: 4 }}>
                      Workload
                    </div>
                    <strong
                      style={{ fontSize: 16, cursor: "pointer", color: "var(--pf-t--global--color--brand--default)" }}
                      onClick={() => navigate(`/workloads/${w.id}`)}
                    >
                      {w.display_name}
                    </strong>
                    <div style={{ marginTop: 8 }}>
                      <StateBadge state={w.current_state} />
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 24, marginTop: 12, fontSize: 13 }}>
                      <div><strong>Impact</strong><br />{impactLabel(w.current_state)}</div>
                      <div><strong>Backend</strong><br />{w.backend_type}</div>
                      <div><strong>Principal</strong><br /><span style={{ fontFamily: "var(--pf-t--global--font-family--mono)" }}>{w.ipa_principal}</span></div>
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <Button
                      variant="primary"
                      onClick={() => attestWorkload(w.id)}
                    >
                      Request re-attestation
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => navigate(`/workloads/${w.id}`)}
                    >
                      View Workload
                    </Button>
                  </div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </PageSection>
  );
};

export default Remediation;

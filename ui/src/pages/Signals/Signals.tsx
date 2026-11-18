import React, { useMemo } from "react";
import {
  PageSection,
  Card,
  CardTitle,
  CardBody,
  Grid,
  GridItem,
  Alert,
  Label,
} from "@patternfly/react-core";
import { useNavigate } from "react-router-dom";
import TitleLayout from "src/components/layouts/TitleLayout";
import DataSpinner from "src/components/DataSpinner";
import StateBadge from "src/components/StateBadge";
import { useGetWorkloadsQuery } from "src/services/rpcWorkloads";
import { useGetAuditQuery } from "src/services/rpcAudit";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";
import type { Workload, AuditLogEntry } from "src/utils/datatypes/globalDataTypes";

function computeSignals(workloads: Workload[], auditItems: AuditLogEntry[]) {
  const total = workloads.length;
  const healthy = workloads.filter((w) => w.current_state === WorkloadState.HEALTHY).length;
  const coverage = total ? Math.round((healthy / total) * 100) : 0;

  const now = Date.now();
  const forecast = workloads
    .filter((w) => w.current_state !== WorkloadState.REVOKED)
    .map((w) => {
      const elapsed = w.last_attested_at ? (now - new Date(w.last_attested_at).getTime()) / 1000 : null;
      const remaining = elapsed !== null ? Math.max(0, w.stale_ttl_seconds - elapsed) : null;
      const already = [WorkloadState.STALE, WorkloadState.FAILED].includes(w.current_state);
      return { ...w, remaining: already ? 0 : remaining, already };
    })
    .filter((w) => w.already || (w.remaining !== null && w.remaining < 2700))
    .sort((a, b) => (a.remaining ?? 9999) - (b.remaining ?? 9999))
    .slice(0, 5);

  const attestResults = auditItems.filter((e) => e.action === "attestation_result");
  const passes = attestResults.filter((e) => typeof e.detail === "object" && e.detail && "verdict" in e.detail && String(e.detail.verdict).toLowerCase() === "pass").length;
  const fails = attestResults.length - passes;
  const passRate = attestResults.length ? Math.round((passes / attestResults.length) * 100) : 0;

  const flapMap: Record<string, number> = {};
  auditItems.forEach((e) => {
    if (e.target_id && ["state_transition", "attestation_result"].includes(e.action)) {
      flapMap[e.target_id] = (flapMap[e.target_id] || 0) + 1;
    }
  });
  const flapping = Object.entries(flapMap)
    .filter(([, count]) => count >= 2)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5)
    .map(([id, count]) => ({ id, count, workload: workloads.find((w) => w.id === id) }));

  const types = [...new Set(workloads.map((w) => w.workload_type))];
  const cohorts = types.map((type) => {
    const set = workloads.filter((w) => w.workload_type === type);
    const v = set.filter((w) => w.current_state === WorkloadState.HEALTHY).length;
    const rate = set.length ? Math.round((v / set.length) * 100) : 0;
    return { type, total: set.length, verified: v, rate };
  });

  const ages = { fresh: 0, aging: 0, stale: 0, none: 0 };
  workloads.forEach((w) => {
    if (!w.last_attested_at) { ages.none++; return; }
    const elapsed = (now - new Date(w.last_attested_at).getTime()) / 1000;
    if (elapsed < w.stale_ttl_seconds * 0.5) ages.fresh++;
    else if (elapsed < w.stale_ttl_seconds) ages.aging++;
    else ages.stale++;
  });

  return { total, healthy, coverage, forecast, passRate, passes, fails, decided: attestResults.length, flapping, cohorts, ages };
}

const Signals: React.FC = () => {
  const navigate = useNavigate();
  const { data: wlData, isLoading: wlLoading, isError: wlError } = useGetWorkloadsQuery({ count: 100 }, { pollingInterval: 30000 });
  const { data: auData, isLoading: auLoading, isError: auError } = useGetAuditQuery({ count: 100 }, { pollingInterval: 30000 });

  const signals = useMemo(
    () => computeSignals(wlData?.items ?? [], auData?.items ?? []),
    [wlData, auData]
  );

  if (wlLoading || auLoading) return <PageSection><DataSpinner /></PageSection>;

  return (
    <PageSection>
      <TitleLayout title="Signals" description="Patterns over time — forecast, efficacy, cohorts, and noise. Current object counts stay on the Dashboard." />

      {(wlError || auError) && <Alert variant="warning" title="Some data could not be loaded" isInline style={{ marginBottom: 16 }} />}

      <Grid hasGutter>
        {/* Forecast */}
        <GridItem span={6}>
          <Card>
            <CardTitle>TTL / freshness breaches</CardTitle>
            <CardBody>
              <p style={{ fontSize: 13, color: "var(--pf-t--global--text--color--subtle)", marginBottom: 12 }}>
                Who goes stale soon — not how many are unhealthy right now.
              </p>
              {signals.forecast.length === 0 ? (
                <p>No near-term breaches in the 45-minute forecast window.</p>
              ) : (
                signals.forecast.map((w) => (
                  <div key={w.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--pf-t--global--border--color--default)" }}>
                    <div style={{ minWidth: 48, fontWeight: 600, color: w.already ? "var(--pf-t--global--color--status--warning--default)" : undefined }}>
                      {w.already ? "Now" : w.remaining !== null ? `${Math.round(w.remaining / 60)}m` : "—"}
                    </div>
                    <div style={{ flex: 1 }}>
                      <strong style={{ cursor: "pointer" }} onClick={() => navigate(`/workloads/${w.id}`)}>{w.display_name}</strong>
                      <div style={{ fontSize: 12, color: "var(--pf-t--global--text--color--subtle)" }}>
                        {w.already ? "Already outside freshness window" : `TTL remaining before stale (${w.stale_ttl_seconds}s)`}
                      </div>
                    </div>
                    <StateBadge state={w.current_state} />
                  </div>
                ))
              )}
            </CardBody>
          </Card>
        </GridItem>

        {/* Pass rate */}
        <GridItem span={6}>
          <Card>
            <CardTitle>Attestation pass rate</CardTitle>
            <CardBody>
              <p style={{ fontSize: 13, color: "var(--pf-t--global--text--color--subtle)", marginBottom: 12 }}>
                Decision outcomes from attestation history.
              </p>
              <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 12 }}>
                <span style={{ fontSize: 48, fontWeight: 700, color: signals.passRate >= 80 ? "var(--pf-t--global--color--status--success--default)" : "var(--pf-t--global--color--status--warning--default)" }}>
                  {signals.passRate}%
                </span>
                <div style={{ fontSize: 13 }}>
                  <strong>{signals.passes} pass</strong> · {signals.fails} fail/unavailable
                  <br />Across {signals.decided} recorded Decisions
                </div>
              </div>
              <div style={{ display: "flex", gap: 4, height: 8, borderRadius: 4, overflow: "hidden", background: "var(--pf-t--global--background--color--secondary--default)" }}>
                {signals.decided > 0 && (
                  <>
                    <div style={{ width: `${signals.passRate}%`, background: "var(--pf-t--global--color--status--success--default)", borderRadius: 4 }} />
                    <div style={{ width: `${100 - signals.passRate}%`, background: "var(--pf-t--global--color--status--danger--default)", borderRadius: 4 }} />
                  </>
                )}
              </div>
            </CardBody>
          </Card>
        </GridItem>

        {/* Flapping */}
        <GridItem span={6}>
          <Card>
            <CardTitle>Flapping Workloads</CardTitle>
            <CardBody>
              <p style={{ fontSize: 13, color: "var(--pf-t--global--text--color--subtle)", marginBottom: 12 }}>
                Repeated events/transitions — signal worth investigating.
              </p>
              {signals.flapping.length === 0 ? (
                <p>No flapping detected in the current event stream.</p>
              ) : (
                <table className="pf-v6-c-table pf-m-compact" role="grid">
                  <thead><tr><th>Workload</th><th>Events</th><th>Current</th></tr></thead>
                  <tbody>
                    {signals.flapping.map((f) => (
                      <tr key={f.id}>
                        <td>
                          <span style={{ cursor: "pointer", color: "var(--pf-t--global--color--brand--default)" }} onClick={() => navigate(`/workloads/${f.id}`)}>
                            {f.workload?.display_name ?? f.id}
                          </span>
                        </td>
                        <td><Label isCompact>{f.count}</Label></td>
                        <td>{f.workload ? <StateBadge state={f.workload.current_state} /> : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardBody>
          </Card>
        </GridItem>

        {/* Cohorts */}
        <GridItem span={6}>
          <Card>
            <CardTitle>Verify rate by Workload type</CardTitle>
            <CardBody>
              <p style={{ fontSize: 13, color: "var(--pf-t--global--text--color--subtle)", marginBottom: 12 }}>
                Compare segments instead of a single fleet average.
              </p>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                {signals.cohorts.map((c) => (
                  <Card key={c.type} isCompact style={{ minWidth: 140, textAlign: "center", padding: 16 }}>
                    <div style={{ fontWeight: 600, textTransform: "capitalize", marginBottom: 4 }}>{c.type}</div>
                    <div style={{ fontSize: 32, fontWeight: 700, color: c.rate >= 80 ? "var(--pf-t--global--color--status--success--default)" : c.rate >= 40 ? "var(--pf-t--global--color--status--warning--default)" : "var(--pf-t--global--color--status--danger--default)" }}>
                      {c.rate}%
                    </div>
                    <div style={{ fontSize: 12 }}>{c.verified} of {c.total} verified</div>
                  </Card>
                ))}
              </div>
            </CardBody>
          </Card>
        </GridItem>

        {/* Evidence age */}
        <GridItem span={6}>
          <Card>
            <CardTitle>Evidence age distribution</CardTitle>
            <CardBody>
              <p style={{ fontSize: 13, color: "var(--pf-t--global--text--color--subtle)", marginBottom: 12 }}>
                How fresh is evidence across the fleet.
              </p>
              {[
                { label: "Fresh (< 50% TTL)", count: signals.ages.fresh, color: "var(--pf-t--global--color--status--success--default)" },
                { label: "Aging (50-100% TTL)", count: signals.ages.aging, color: "var(--pf-t--global--color--status--warning--default)" },
                { label: "Past TTL", count: signals.ages.stale, color: "var(--pf-t--global--color--status--danger--default)" },
                { label: "No evidence yet", count: signals.ages.none, color: "var(--pf-t--global--border--color--default)" },
              ].map((row) => (
                <div key={row.label} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
                  <span style={{ minWidth: 140, fontSize: 13 }}>{row.label}</span>
                  <div style={{ flex: 1, height: 8, borderRadius: 4, background: "var(--pf-t--global--background--color--secondary--default)" }}>
                    <div style={{ width: `${signals.total ? (row.count / signals.total) * 100 : 0}%`, height: "100%", borderRadius: 4, background: row.color }} />
                  </div>
                  <strong style={{ minWidth: 24, textAlign: "right" }}>{row.count}</strong>
                </div>
              ))}
            </CardBody>
          </Card>
        </GridItem>

        {/* Coverage KPI */}
        <GridItem span={6}>
          <Card>
            <CardTitle>Trust coverage</CardTitle>
            <CardBody>
              <div style={{ textAlign: "center", padding: 16 }}>
                <div style={{ fontSize: 64, fontWeight: 700, color: signals.coverage >= 90 ? "var(--pf-t--global--color--status--success--default)" : "var(--pf-t--global--color--status--danger--default)" }}>
                  {signals.coverage}%
                </div>
                <div style={{ height: 8, borderRadius: 4, background: "var(--pf-t--global--background--color--secondary--default)", marginTop: 8 }}>
                  <div style={{ width: `${signals.coverage}%`, height: "100%", borderRadius: 4, background: signals.coverage >= 90 ? "var(--pf-t--global--color--status--success--default)" : "var(--pf-t--global--color--status--danger--default)" }} />
                </div>
                <p style={{ fontSize: 13, marginTop: 8 }}><strong>{signals.healthy} of {signals.total}</strong> workloads verified — target 90%</p>
              </div>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>
    </PageSection>
  );
};

export default Signals;

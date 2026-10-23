import React, { useState, useMemo } from "react";
import {
  PageSection,
  Card,
  CardBody,
  SearchInput,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  MenuToggle,
  Select,
  SelectOption,
  Alert,
} from "@patternfly/react-core";
import TitleLayout from "src/components/layouts/TitleLayout";
import DataSpinner from "src/components/DataSpinner";
import StateBadge from "src/components/StateBadge";
import { useGetAuditQuery } from "src/services/rpcAudit";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";
import type { AuditLogEntry } from "src/utils/datatypes/globalDataTypes";

function formatRelativeTime(dateStr: string): string {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function isLifecycleEvent(entry: AuditLogEntry): boolean {
  return ["attestation_result", "state_transition", "workload_registered", "workload_revoked", "workload_remediated"].includes(entry.action);
}

function eventTypeLabel(action: string): string {
  const map: Record<string, string> = {
    attestation_result: "Attestation result",
    state_transition: "State transition",
    workload_registered: "Registered",
    workload_revoked: "Revoked",
    workload_remediated: "Remediated",
  };
  return map[action] || action;
}

function nextAction(entry: AuditLogEntry): string {
  const detail = entry.detail;
  if (typeof detail === "object" && detail) {
    if ("verdict" in detail) {
      const v = String(detail.verdict).toLowerCase();
      if (v === "pass") return "Continue monitoring";
      if (v === "fail") return "Investigate or remediate";
      if (v === "error" || v === "unavailable") return "Request re-attestation";
    }
    if ("to" in detail) {
      const to = String(detail.to);
      if (to === WorkloadState.FAILED) return "Investigate or revoke";
      if (to === WorkloadState.STALE) return "Request re-attestation";
      if (to === WorkloadState.HEALTHY) return "Continue monitoring";
    }
  }
  return "Review";
}

const EVENT_FILTERS = ["all", "attestation_result", "state_transition", "workload_registered", "workload_revoked"];

const Events: React.FC = () => {
  const { data, isLoading, isError } = useGetAuditQuery({ count: 100 }, { pollingInterval: 30000 });
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [typeOpen, setTypeOpen] = useState(false);

  const events = useMemo(() => {
    const items = (data?.items ?? []).filter(isLifecycleEvent);
    return items.filter((e) => {
      if (typeFilter !== "all" && e.action !== typeFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const searchable = [e.actor, e.action, e.target_id, JSON.stringify(e.detail)].join(" ").toLowerCase();
        if (!searchable.includes(q)) return false;
      }
      return true;
    });
  }, [data, search, typeFilter]);

  if (isLoading) return <PageSection><DataSpinner /></PageSection>;

  return (
    <PageSection>
      <TitleLayout title="Events" description="Signals about Workload Decisions for operations and security tools." />

      {isError && <Alert variant="warning" title="Could not load events" isInline style={{ marginBottom: 16 }} />}

      <Card>
        <CardBody style={{ padding: 0 }}>
          <Toolbar>
            <ToolbarContent>
              <ToolbarItem>
                <SearchInput
                  placeholder="Search workload or reason"
                  value={search}
                  onChange={(_e, val) => setSearch(val)}
                  onClear={() => setSearch("")}
                />
              </ToolbarItem>
              <ToolbarItem>
                <Select
                  toggle={(toggleRef) => (
                    <MenuToggle ref={toggleRef} onClick={() => setTypeOpen(!typeOpen)} isExpanded={typeOpen}>
                      {typeFilter === "all" ? "All event types" : eventTypeLabel(typeFilter)}
                    </MenuToggle>
                  )}
                  isOpen={typeOpen}
                  onSelect={(_e, val) => { setTypeFilter(val as string); setTypeOpen(false); }}
                  onOpenChange={setTypeOpen}
                  selected={typeFilter}
                >
                  {EVENT_FILTERS.map((f) => (
                    <SelectOption key={f} value={f}>
                      {f === "all" ? "All event types" : eventTypeLabel(f)}
                    </SelectOption>
                  ))}
                </Select>
              </ToolbarItem>
            </ToolbarContent>
          </Toolbar>

          <div style={{ overflowX: "auto" }}>
            <table className="pf-v6-c-table pf-m-grid-md" role="grid">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Workload</th>
                  <th>Event</th>
                  <th>Source</th>
                  <th>Detail</th>
                  <th>Next action</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: "center", padding: 32 }}>No events match the current filters.</td></tr>
                ) : events.map((e) => (
                  <tr key={e.id}>
                    <td>{formatRelativeTime(e.created_at)}</td>
                    <td style={{ fontFamily: "var(--pf-t--global--font-family--mono)" }}>{e.target_id ?? "—"}</td>
                    <td>
                      {e.action === "state_transition" && typeof e.detail === "object" && e.detail && "from" in e.detail && "to" in e.detail ? (
                        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <StateBadge state={e.detail.from as WorkloadState} />
                          <span>→</span>
                          <StateBadge state={e.detail.to as WorkloadState} />
                        </span>
                      ) : (
                        eventTypeLabel(e.action)
                      )}
                    </td>
                    <td>{e.actor}</td>
                    <td style={{ fontSize: 13, color: "var(--pf-t--global--text--color--subtle)" }}>
                      {typeof e.detail === "object" && e.detail && "justification" in e.detail
                        ? String(e.detail.justification).slice(0, 80)
                        : typeof e.detail === "object" && e.detail && "verdict" in e.detail
                        ? String(e.detail.verdict)
                        : "—"}
                    </td>
                    <td>{nextAction(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </PageSection>
  );
};

export default Events;

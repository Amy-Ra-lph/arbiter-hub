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

interface TransitionDetail {
  from: string;
  to: string;
  justification?: string;
}

function isTransition(entry: AuditLogEntry): entry is AuditLogEntry & { detail: TransitionDetail } {
  return (
    entry.action === "state_transition" &&
    typeof entry.detail === "object" &&
    entry.detail !== null &&
    "from" in entry.detail &&
    "to" in entry.detail
  );
}

const STATE_OPTIONS = ["all", ...Object.values(WorkloadState)];

const StateTransitions: React.FC = () => {
  const { data, isLoading, isError } = useGetAuditQuery({ count: 100 }, { pollingInterval: 30000 });
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("all");
  const [stateOpen, setStateOpen] = useState(false);

  const transitions = useMemo(() => {
    const items = (data?.items ?? []).filter(isTransition);
    return items.filter((e) => {
      const detail = e.detail as TransitionDetail;
      if (stateFilter !== "all" && detail.to !== stateFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const searchable = [e.target_id, e.actor, detail.justification ?? ""].join(" ").toLowerCase();
        if (!searchable.includes(q)) return false;
      }
      return true;
    });
  }, [data, search, stateFilter]);

  if (isLoading) return <PageSection><DataSpinner /></PageSection>;

  return (
    <PageSection>
      <TitleLayout title="State Transitions" description="Lifecycle edges between Workload states — trigger and justification." />

      {isError && <Alert variant="warning" title="Could not load transitions" isInline style={{ marginBottom: 16 }} />}

      <Card>
        <CardBody style={{ padding: 0 }}>
          <Toolbar>
            <ToolbarContent>
              <ToolbarItem>
                <SearchInput
                  placeholder="Search workload or trigger"
                  value={search}
                  onChange={(_e, val) => setSearch(val)}
                  onClear={() => setSearch("")}
                />
              </ToolbarItem>
              <ToolbarItem>
                <Select
                  toggle={(toggleRef) => (
                    <MenuToggle ref={toggleRef} onClick={() => setStateOpen(!stateOpen)} isExpanded={stateOpen}>
                      {stateFilter === "all" ? "All states" : stateFilter.replace("_", " ")}
                    </MenuToggle>
                  )}
                  isOpen={stateOpen}
                  onSelect={(_e, val) => { setStateFilter(val as string); setStateOpen(false); }}
                  onOpenChange={setStateOpen}
                  selected={stateFilter}
                >
                  {STATE_OPTIONS.map((s) => (
                    <SelectOption key={s} value={s}>
                      {s === "all" ? "All states" : s.replace("_", " ")}
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
                  <th>From</th>
                  <th>To</th>
                  <th>Triggered by</th>
                  <th>Justification</th>
                </tr>
              </thead>
              <tbody>
                {transitions.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: "center", padding: 32 }}>No transitions match the current filters.</td></tr>
                ) : transitions.map((e) => {
                  const d = e.detail as TransitionDetail;
                  return (
                    <tr key={e.id}>
                      <td>{formatRelativeTime(e.created_at)}</td>
                      <td style={{ fontFamily: "var(--pf-t--global--font-family--mono)" }}>{e.target_id ?? "—"}</td>
                      <td><StateBadge state={d.from as WorkloadState} /></td>
                      <td><StateBadge state={d.to as WorkloadState} /></td>
                      <td>{e.actor}</td>
                      <td style={{ fontSize: 13, color: "var(--pf-t--global--text--color--subtle)" }}>
                        {d.justification ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </PageSection>
  );
};

export default StateTransitions;

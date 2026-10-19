import React, { useState, useMemo } from "react";
import {
  PageSection,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  ToolbarGroup,
  FormSelect,
  FormSelectOption,
  Button,
} from "@patternfly/react-core";
import {
  Table,
  Thead,
  Tr,
  Th,
  Tbody,
  Td,
} from "@patternfly/react-table";
import { Label } from "@patternfly/react-core";
import { Link } from "react-router-dom";
import TitleLayout from "src/components/layouts/TitleLayout";
import SearchInputLayout from "src/components/layouts/SearchInputLayout";
import PaginationLayout from "src/components/layouts/PaginationLayout";
import StateBadge from "src/components/StateBadge";
import VerdictBadge from "src/components/VerdictBadge";
import DataSpinner from "src/components/DataSpinner";
import { useGetAuditQuery } from "src/services/rpcAudit";
import { AttestationVerdict, WorkloadState } from "src/utils/datatypes/globalDataTypes";

const History: React.FC = () => {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [search, setSearch] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("");

  const { data, isLoading } = useGetAuditQuery({ count: 100 });

  const items = data?.items ?? [];

  const filtered = useMemo(() => {
    let result = items;
    if (verdictFilter) {
      result = result.filter(
        (e) =>
          e.detail &&
          typeof e.detail === "object" &&
          "verdict" in e.detail &&
          e.detail.verdict === verdictFilter
      );
    }
    if (search) {
      const lower = search.toLowerCase();
      result = result.filter(
        (e) =>
          e.actor.toLowerCase().includes(lower) ||
          (e.target_id && e.target_id.toLowerCase().includes(lower)) ||
          e.action.toLowerCase().includes(lower)
      );
    }
    return result;
  }, [items, verdictFilter, search]);

  const paginated = filtered.slice((page - 1) * perPage, page * perPage);

  const csvEscape = (val: string) => {
    const escaped = val.replace(/"/g, '""');
    return `"${escaped}"`;
  };

  const exportCsv = () => {
    const header = "timestamp,actor,action,target_type,target_id,verdict\n";
    const rows = filtered
      .map((e) => {
        const verdict =
          e.detail && typeof e.detail === "object" && "verdict" in e.detail
            ? String(e.detail.verdict)
            : "";
        return [e.created_at, e.actor, e.action, e.target_type ?? "", e.target_id ?? "", verdict]
          .map(csvEscape)
          .join(",");
      })
      .join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "attestation-history.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <PageSection>
        <DataSpinner />
      </PageSection>
    );
  }

  return (
    <PageSection>
      <TitleLayout
        title="Attestation History"
        description="Cross-workload attestation event log"
      />

      <Toolbar>
        <ToolbarContent>
          <ToolbarItem>
            <SearchInputLayout
              value={search}
              onChange={setSearch}
              placeholder="Search by workload or backend..."
            />
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={verdictFilter}
              onChange={(_evt, val) => setVerdictFilter(val)}
              aria-label="Filter by verdict"
            >
              <FormSelectOption value="" label="All verdicts" />
              {Object.values(AttestationVerdict).map((v) => (
                <FormSelectOption key={v} value={v} label={v} />
              ))}
            </FormSelect>
          </ToolbarItem>
          <ToolbarGroup align={{ default: "alignEnd" }}>
            <ToolbarItem>
              <Button variant="secondary" onClick={exportCsv}>
                Export CSV
              </Button>
            </ToolbarItem>
          </ToolbarGroup>
          <ToolbarItem variant="pagination">
            <PaginationLayout
              itemCount={filtered.length}
              page={page}
              perPage={perPage}
              onSetPage={setPage}
              onPerPageSelect={(pp) => { setPerPage(pp); setPage(1); }}
            />
          </ToolbarItem>
        </ToolbarContent>
      </Toolbar>

      <Table aria-label="Attestation history">
        <Thead>
          <Tr>
            <Th>Time</Th>
            <Th>Actor</Th>
            <Th>Action</Th>
            <Th>Target</Th>
            <Th>Verdict</Th>
          </Tr>
        </Thead>
        <Tbody>
          {paginated.map((event) => (
            <Tr key={event.id}>
              <Td dataLabel="Time">
                {new Date(event.created_at).toLocaleString()}
              </Td>
              <Td dataLabel="Actor">
                {event.actor === "falco_alert" ? (
                  <Label color="orange" isCompact>falco</Label>
                ) : event.actor === "attestation_result" ? (
                  <Label color="blue" isCompact>attest</Label>
                ) : (
                  event.actor
                )}
              </Td>
              <Td dataLabel="Action">
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
              </Td>
              <Td dataLabel="Target">
                {event.target_id ? (
                  <Link to={`/workloads/${event.target_id}`}>
                    {event.target_id.slice(0, 8)}
                  </Link>
                ) : (
                  "—"
                )}
              </Td>
              <Td dataLabel="Verdict">
                {event.detail &&
                typeof event.detail === "object" &&
                "verdict" in event.detail ? (
                  <VerdictBadge
                    verdict={event.detail.verdict as AttestationVerdict}
                  />
                ) : (
                  "—"
                )}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </PageSection>
  );
};

export default History;

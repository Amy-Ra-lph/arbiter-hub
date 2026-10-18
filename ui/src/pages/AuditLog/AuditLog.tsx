import React, { useState, useMemo } from "react";
import {
  PageSection,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  ToolbarGroup,
  Button,
  FormSelect,
  FormSelectOption,
  Label,
} from "@patternfly/react-core";
import {
  Table,
  Thead,
  Tr,
  Th,
  Tbody,
  Td,
  ExpandableRowContent,
} from "@patternfly/react-table";
import { Link } from "react-router-dom";
import TitleLayout from "src/components/layouts/TitleLayout";
import SearchInputLayout from "src/components/layouts/SearchInputLayout";
import PaginationLayout from "src/components/layouts/PaginationLayout";
import DataSpinner from "src/components/DataSpinner";
import { useGetAuditQuery } from "src/services/rpcAudit";

const AuditLog: React.FC = () => {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [actorTypeFilter, setActorTypeFilter] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const { data, isLoading } = useGetAuditQuery({ count: 500 });

  const items = data?.items ?? [];

  const actionTypes = useMemo(
    () => [...new Set(items.map((e) => e.action))],
    [items]
  );
  const actorTypes = useMemo(
    () => [...new Set(items.map((e) => e.actor_type))],
    [items]
  );

  const filtered = useMemo(() => {
    let result = items;
    if (actionFilter) result = result.filter((e) => e.action === actionFilter);
    if (actorTypeFilter)
      result = result.filter((e) => e.actor_type === actorTypeFilter);
    if (search) {
      const lower = search.toLowerCase();
      result = result.filter(
        (e) =>
          e.actor.toLowerCase().includes(lower) ||
          (e.target_id && e.target_id.toLowerCase().includes(lower))
      );
    }
    return result;
  }, [items, actionFilter, actorTypeFilter, search]);

  const paginated = filtered.slice((page - 1) * perPage, page * perPage);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const exportCsv = () => {
    const header =
      "timestamp,actor,actor_type,action,target_type,target_id\n";
    const rows = filtered
      .map(
        (e) =>
          `${e.created_at},${e.actor},${e.actor_type},${e.action},${e.target_type ?? ""},${e.target_id ?? ""}`
      )
      .join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit-log.csv";
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
        title="Audit Log"
        description="System-wide event audit trail"
      />

      <Toolbar>
        <ToolbarContent>
          <ToolbarItem>
            <SearchInputLayout
              value={search}
              onChange={setSearch}
              placeholder="Search by actor or target..."
            />
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={actionFilter}
              onChange={(_evt, val) => setActionFilter(val)}
              aria-label="Filter by action"
            >
              <FormSelectOption value="" label="All actions" />
              {actionTypes.map((a) => (
                <FormSelectOption key={a} value={a} label={a} />
              ))}
            </FormSelect>
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={actorTypeFilter}
              onChange={(_evt, val) => setActorTypeFilter(val)}
              aria-label="Filter by actor type"
            >
              <FormSelectOption value="" label="All actor types" />
              {actorTypes.map((t) => (
                <FormSelectOption key={t} value={t} label={t} />
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

      <Table aria-label="Audit log">
        <Thead>
          <Tr>
            <Th screenReaderText="Expand" />
            <Th>Time</Th>
            <Th>Actor</Th>
            <Th>Actor Type</Th>
            <Th>Action</Th>
            <Th>Target Type</Th>
            <Th>Target</Th>
          </Tr>
        </Thead>
        <Tbody>
          {paginated.map((event, rowIndex) => {
            const isExpanded = expandedIds.has(event.id);
            return (
              <React.Fragment key={event.id}>
                <Tr>
                  <Td
                    expand={{
                      rowIndex,
                      isExpanded,
                      onToggle: () => toggleExpand(event.id),
                    }}
                  />
                  <Td dataLabel="Time">
                    {new Date(event.created_at).toLocaleString()}
                  </Td>
                  <Td dataLabel="Actor">{event.actor}</Td>
                  <Td dataLabel="Actor Type">
                    <Label>{event.actor_type}</Label>
                  </Td>
                  <Td dataLabel="Action">{event.action}</Td>
                  <Td dataLabel="Target Type">{event.target_type ?? "—"}</Td>
                  <Td dataLabel="Target">
                    {event.target_type === "workload" && event.target_id ? (
                      <Link to={`/workloads/${event.target_id}`}>
                        {event.target_id.slice(0, 8)}
                      </Link>
                    ) : (
                      event.target_id ?? "—"
                    )}
                  </Td>
                </Tr>
                {isExpanded && (
                  <Tr isExpanded>
                    <Td colSpan={7}>
                      <ExpandableRowContent>
                        <pre
                          style={{ fontSize: "12px", whiteSpace: "pre-wrap" }}
                        >
                          {JSON.stringify(event.detail, null, 2)}
                        </pre>
                      </ExpandableRowContent>
                    </Td>
                  </Tr>
                )}
              </React.Fragment>
            );
          })}
        </Tbody>
      </Table>
    </PageSection>
  );
};

export default AuditLog;

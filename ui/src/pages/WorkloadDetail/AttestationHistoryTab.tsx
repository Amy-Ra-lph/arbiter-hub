import React, { useState, useMemo } from "react";
import {
  Table,
  Thead,
  Tr,
  Th,
  Tbody,
  Td,
  ExpandableRowContent,
} from "@patternfly/react-table";
import {
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  FormSelect,
  FormSelectOption,
  Tooltip,
} from "@patternfly/react-core";
import SearchInputLayout from "src/components/layouts/SearchInputLayout";
import PaginationLayout from "src/components/layouts/PaginationLayout";
import VerdictBadge from "src/components/VerdictBadge";
import DataSpinner from "src/components/DataSpinner";
import { useGetWorkloadAttestationsQuery } from "src/services/rpcWorkloads";
import { AttestationVerdict } from "src/utils/datatypes/globalDataTypes";

interface AttestationHistoryTabProps {
  workloadId: string;
}

const AttestationHistoryTab: React.FC<AttestationHistoryTabProps> = ({
  workloadId,
}) => {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [search, setSearch] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const { data, isLoading } = useGetWorkloadAttestationsQuery({
    id: workloadId,
    startIndex: (page - 1) * perPage,
    count: perPage,
  });

  const items = data?.items ?? [];

  const filtered = useMemo(() => {
    let result = items;
    if (verdictFilter) {
      result = result.filter((r) => r.verdict === verdictFilter);
    }
    if (search) {
      const lower = search.toLowerCase();
      result = result.filter((r) => r.backend.toLowerCase().includes(lower));
    }
    return result;
  }, [items, verdictFilter, search]);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (isLoading) return <DataSpinner />;

  return (
    <>
      <Toolbar>
        <ToolbarContent>
          <ToolbarItem>
            <SearchInputLayout
              value={search}
              onChange={setSearch}
              placeholder="Search by backend..."
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
          <ToolbarItem variant="pagination">
            <PaginationLayout
              itemCount={data?.total ?? 0}
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
            <Th screenReaderText="Expand" />
            <Th>Time</Th>
            <Th>Verdict</Th>
            <Th>Backend</Th>
            <Th>Evidence Hash</Th>
            <Th>Policy Hash</Th>
          </Tr>
        </Thead>
        <Tbody>
          {filtered.map((record, rowIndex) => {
            const isExpanded = expandedIds.has(record.id);
            return (
              <React.Fragment key={record.id}>
                <Tr>
                  <Td
                    expand={{
                      rowIndex,
                      isExpanded,
                      onToggle: () => toggleExpand(record.id),
                    }}
                  />
                  <Td dataLabel="Time">
                    {new Date(record.created_at).toLocaleString()}
                  </Td>
                  <Td dataLabel="Verdict">
                    <VerdictBadge verdict={record.verdict} />
                  </Td>
                  <Td dataLabel="Backend">{record.backend}</Td>
                  <Td dataLabel="Evidence Hash">
                    {record.evidence_hash ? (
                      <Tooltip content={record.evidence_hash}>
                        <span>{record.evidence_hash.slice(0, 12)}...</span>
                      </Tooltip>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td dataLabel="Policy Hash">
                    {record.policy_hash ? (
                      <Tooltip content={record.policy_hash}>
                        <span>{record.policy_hash.slice(0, 12)}...</span>
                      </Tooltip>
                    ) : (
                      "—"
                    )}
                  </Td>
                </Tr>
                {isExpanded && (
                  <Tr isExpanded>
                    <Td colSpan={6}>
                      <ExpandableRowContent>
                        <pre style={{ fontSize: "12px", whiteSpace: "pre-wrap" }}>
                          {JSON.stringify(record.detail, null, 2)}
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
    </>
  );
};

export default AttestationHistoryTab;

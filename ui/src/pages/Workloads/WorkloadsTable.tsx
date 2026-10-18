import React from "react";
import {
  Table,
  Thead,
  Tr,
  Th,
  Tbody,
  Td,
  ThProps,
} from "@patternfly/react-table";
import { EmptyState, EmptyStateBody } from "@patternfly/react-core";
import { CubesIcon } from "@patternfly/react-icons";
import { Link } from "react-router-dom";
import StateBadge from "src/components/StateBadge";
import TTLCountdown from "src/components/TTLCountdown";
import type { Workload } from "src/utils/datatypes/globalDataTypes";

interface WorkloadsTableProps {
  workloads: Workload[];
  selectedIds: string[];
  onSelect: (ids: string[]) => void;
  sortBy: string;
  sortDir: "asc" | "desc";
  onSort: (column: string) => void;
}

const COLUMNS: { key: string; label: string; sortable: boolean }[] = [
  { key: "display_name", label: "Name", sortable: true },
  { key: "ipa_principal", label: "IPA Principal", sortable: true },
  { key: "workload_type", label: "Type", sortable: true },
  { key: "current_state", label: "State", sortable: true },
  { key: "backend_type", label: "Backend", sortable: true },
  { key: "ttl", label: "TTL", sortable: false },
  { key: "registered_at", label: "Registered", sortable: true },
];

const WorkloadsTable: React.FC<WorkloadsTableProps> = ({
  workloads,
  selectedIds,
  onSelect,
  sortBy,
  sortDir,
  onSort,
}) => {
  if (workloads.length === 0) {
    return (
      <EmptyState
        titleText="No workloads found"
        icon={CubesIcon}
        headingLevel="h4"
      >
        <EmptyStateBody>
          Register a workload to begin attestation monitoring.
        </EmptyStateBody>
      </EmptyState>
    );
  }

  const allSelected =
    workloads.length > 0 && selectedIds.length === workloads.length;

  const toggleAll = () => {
    if (allSelected) {
      onSelect([]);
    } else {
      onSelect(workloads.map((w) => w.id));
    }
  };

  const toggleOne = (id: string) => {
    if (selectedIds.includes(id)) {
      onSelect(selectedIds.filter((sid) => sid !== id));
    } else {
      onSelect([...selectedIds, id]);
    }
  };

  const getSortParams = (col: string): ThProps["sort"] | undefined => {
    const colObj = COLUMNS.find((c) => c.key === col);
    if (!colObj?.sortable) return undefined;
    const colIndex = COLUMNS.findIndex((c) => c.key === col);
    return {
      sortBy: {
        index: COLUMNS.findIndex((c) => c.key === sortBy),
        direction: sortDir,
      },
      onSort: (_evt, _idx, _dir) => onSort(col),
      columnIndex: colIndex,
    };
  };

  return (
    <Table aria-label="Workloads table" variant="compact">
      <Thead>
        <Tr>
          <Th
            screenReaderText="Select all"
            select={{
              onSelect: toggleAll,
              isSelected: allSelected,
            }}
          />
          {COLUMNS.map((col) => (
            <Th key={col.key} sort={getSortParams(col.key)}>
              {col.label}
            </Th>
          ))}
        </Tr>
      </Thead>
      <Tbody>
        {workloads.map((w, idx) => (
          <Tr key={w.id}>
            <Td
              select={{
                rowIndex: idx,
                onSelect: () => toggleOne(w.id),
                isSelected: selectedIds.includes(w.id),
              }}
            />
            <Td dataLabel="Name">
              <Link to={`/workloads/${w.id}`}>{w.display_name}</Link>
            </Td>
            <Td dataLabel="IPA Principal">{w.ipa_principal}</Td>
            <Td dataLabel="Type">{w.workload_type}</Td>
            <Td dataLabel="State">
              <StateBadge state={w.current_state} />
            </Td>
            <Td dataLabel="Backend">{w.backend_type}</Td>
            <Td dataLabel="TTL">
              <TTLCountdown
                lastAttestedAt={w.last_attested_at}
                staleTtlSeconds={w.stale_ttl_seconds}
              />
            </Td>
            <Td dataLabel="Registered">
              {new Date(w.registered_at).toLocaleDateString()}
            </Td>
          </Tr>
        ))}
      </Tbody>
    </Table>
  );
};

export default WorkloadsTable;

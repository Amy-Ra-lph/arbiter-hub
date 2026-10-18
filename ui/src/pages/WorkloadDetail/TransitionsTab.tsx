import React, { useState, useMemo } from "react";
import {
  Table,
  Thead,
  Tr,
  Th,
  Tbody,
  Td,
} from "@patternfly/react-table";
import {
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  FormSelect,
  FormSelectOption,
} from "@patternfly/react-core";
import SearchInputLayout from "src/components/layouts/SearchInputLayout";
import PaginationLayout from "src/components/layouts/PaginationLayout";
import StateBadge from "src/components/StateBadge";
import DataSpinner from "src/components/DataSpinner";
import { useGetWorkloadTransitionsQuery } from "src/services/rpcWorkloads";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";

interface TransitionsTabProps {
  workloadId: string;
}

const TransitionsTab: React.FC<TransitionsTabProps> = ({ workloadId }) => {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("");

  const { data, isLoading } = useGetWorkloadTransitionsQuery({
    id: workloadId,
    startIndex: (page - 1) * perPage,
    count: perPage,
  });

  const items = data?.items ?? [];

  const filtered = useMemo(() => {
    let result = items;
    if (stateFilter) {
      result = result.filter((t) => t.to_state === stateFilter);
    }
    if (search) {
      const lower = search.toLowerCase();
      result = result.filter((t) =>
        t.triggered_by.toLowerCase().includes(lower)
      );
    }
    return result;
  }, [items, stateFilter, search]);

  if (isLoading) return <DataSpinner />;

  return (
    <>
      <Toolbar>
        <ToolbarContent>
          <ToolbarItem>
            <SearchInputLayout
              value={search}
              onChange={setSearch}
              placeholder="Search by triggered_by..."
            />
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={stateFilter}
              onChange={(_evt, val) => setStateFilter(val)}
              aria-label="Filter by target state"
            >
              <FormSelectOption value="" label="All states" />
              {Object.values(WorkloadState).map((s) => (
                <FormSelectOption
                  key={s}
                  value={s}
                  label={s.replace("_", " ")}
                />
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

      <Table aria-label="State transitions">
        <Thead>
          <Tr>
            <Th>Time</Th>
            <Th>From</Th>
            <Th>To</Th>
            <Th>Triggered By</Th>
            <Th>Justification</Th>
          </Tr>
        </Thead>
        <Tbody>
          {filtered.map((t) => (
            <Tr key={t.id}>
              <Td dataLabel="Time">
                {new Date(t.created_at).toLocaleString()}
              </Td>
              <Td dataLabel="From">
                <StateBadge state={t.from_state} />
              </Td>
              <Td dataLabel="To">
                <StateBadge state={t.to_state} />
              </Td>
              <Td dataLabel="Triggered By">{t.triggered_by}</Td>
              <Td dataLabel="Justification">{t.justification ?? "—"}</Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </>
  );
};

export default TransitionsTab;

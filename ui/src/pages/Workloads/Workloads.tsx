import React, { useState, useMemo } from "react";
import {
  PageSection,
  Button,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  ToolbarGroup,
  FormSelect,
  FormSelectOption,
  Alert,
} from "@patternfly/react-core";
import TitleLayout from "src/components/layouts/TitleLayout";
import SearchInputLayout from "src/components/layouts/SearchInputLayout";
import PaginationLayout from "src/components/layouts/PaginationLayout";
import DataSpinner from "src/components/DataSpinner";
import WorkloadsTable from "./WorkloadsTable";
import AddWorkload from "./AddWorkload";
import DeleteWorkloads from "./DeleteWorkloads";
import { useGetWorkloadsQuery } from "src/services/rpcWorkloads";
import { useListPageSearchParams } from "src/hooks/useListPageSearchParams";
import { WorkloadState, WorkloadType } from "src/utils/datatypes/globalDataTypes";
import type { Workload } from "src/utils/datatypes/globalDataTypes";

const Workloads: React.FC = () => {
  const {
    page,
    perPage,
    search,
    sortBy,
    sortDir,
    setPage,
    setPerPage,
    setSearch,
    setSortBy,
    setSortDir,
  } = useListPageSearchParams();

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const initialState = new URLSearchParams(window.location.search).get("state") ?? "";
  const [stateFilter, setStateFilter] = useState<string>(initialState);
  const [typeFilter, setTypeFilter] = useState<string>("");

  const { data, isLoading, isError } = useGetWorkloadsQuery(
    { count: 100 },
    { pollingInterval: 15000 },
  );

  const allWorkloads = data?.items ?? [];

  const filtered = useMemo(() => {
    let result = allWorkloads;

    if (stateFilter) {
      result = result.filter((w) => w.current_state === stateFilter);
    }
    if (typeFilter) {
      result = result.filter((w) => w.workload_type === typeFilter);
    }
    if (search) {
      const lower = search.toLowerCase();
      result = result.filter(
        (w) =>
          w.display_name.toLowerCase().includes(lower) ||
          w.ipa_principal.toLowerCase().includes(lower)
      );
    }

    return sortWorkloads(result, sortBy, sortDir);
  }, [allWorkloads, stateFilter, typeFilter, search, sortBy, sortDir]);

  const paginated = filtered.slice((page - 1) * perPage, page * perPage);

  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(column);
      setSortDir("asc");
    }
  };

  if (isLoading) {
    return (
      <PageSection>
        <DataSpinner />
      </PageSection>
    );
  }

  if (isError) {
    return (
      <PageSection>
        <Alert variant="danger" title="Failed to load workloads" isInline />
      </PageSection>
    );
  }

  return (
    <PageSection>
      <TitleLayout
        title="Workloads"
        description="Registered federation workloads and their attestation state"
      />

      <Toolbar>
        <ToolbarContent>
          <ToolbarItem>
            <SearchInputLayout
              value={search}
              onChange={setSearch}
              placeholder="Search by name or principal..."
            />
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={stateFilter}
              onChange={(_evt, val) => setStateFilter(val)}
              aria-label="Filter by state"
            >
              <FormSelectOption value="" label="All states" />
              {Object.values(WorkloadState).map((s) => (
                <FormSelectOption key={s} value={s} label={s.replace("_", " ")} />
              ))}
            </FormSelect>
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={typeFilter}
              onChange={(_evt, val) => setTypeFilter(val)}
              aria-label="Filter by type"
            >
              <FormSelectOption value="" label="All types" />
              {Object.values(WorkloadType).map((t) => (
                <FormSelectOption key={t} value={t} label={t} />
              ))}
            </FormSelect>
          </ToolbarItem>
          <ToolbarGroup align={{ default: "alignEnd" }}>
            <ToolbarItem>
              <Button variant="primary" onClick={() => setIsAddOpen(true)}>
                Add workload
              </Button>
            </ToolbarItem>
            <ToolbarItem>
              <Button
                variant="danger"
                isDisabled={selectedIds.length === 0}
                onClick={() => setIsDeleteOpen(true)}
              >
                Delete ({selectedIds.length})
              </Button>
            </ToolbarItem>
          </ToolbarGroup>
          <ToolbarItem variant="pagination">
            <PaginationLayout
              itemCount={filtered.length}
              page={page}
              perPage={perPage}
              onSetPage={setPage}
              onPerPageSelect={setPerPage}
            />
          </ToolbarItem>
        </ToolbarContent>
      </Toolbar>

      <WorkloadsTable
        workloads={paginated}
        selectedIds={selectedIds}
        onSelect={setSelectedIds}
        sortBy={sortBy}
        sortDir={sortDir}
        onSort={handleSort}
      />

      <PaginationLayout
        itemCount={filtered.length}
        page={page}
        perPage={perPage}
        onSetPage={setPage}
        onPerPageSelect={setPerPage}
        variant="bottom"
      />

      <AddWorkload isOpen={isAddOpen} onClose={() => setIsAddOpen(false)} />
      <DeleteWorkloads
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        selectedIds={selectedIds}
        onComplete={() => setSelectedIds([])}
      />
    </PageSection>
  );
};

function sortWorkloads(
  items: Workload[],
  by: string,
  dir: "asc" | "desc"
): Workload[] {
  const sorted = [...items].sort((a, b) => {
    const aVal = (a as unknown as Record<string, unknown>)[by];
    const bVal = (b as unknown as Record<string, unknown>)[by];
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return 1;
    if (bVal == null) return -1;
    if (typeof aVal === "string" && typeof bVal === "string") {
      return aVal.localeCompare(bVal);
    }
    if (typeof aVal === "number" && typeof bVal === "number") {
      return aVal - bVal;
    }
    return String(aVal).localeCompare(String(bVal));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export default Workloads;

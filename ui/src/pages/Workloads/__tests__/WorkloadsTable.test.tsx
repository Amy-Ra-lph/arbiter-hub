import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import WorkloadsTable from "../WorkloadsTable";
import { WorkloadState, WorkloadType, BackendType } from "src/utils/datatypes/globalDataTypes";
import type { Workload } from "src/utils/datatypes/globalDataTypes";

const mockWorkload: Workload = {
  id: "aaa-bbb-ccc",
  ipa_principal: "web-api@IPA.EXAMPLE",
  display_name: "web-api",
  workload_type: WorkloadType.SERVICE,
  current_state: WorkloadState.HEALTHY,
  backend_type: BackendType.KEYLIME,
  stale_ttl_seconds: 3600,
  registered_at: "2026-10-17T12:00:00Z",
  last_attested_at: "2026-10-17T13:00:00Z",
  metadata: {},
};

describe("WorkloadsTable", () => {
  it("renders workload rows", () => {
    render(
      <MemoryRouter>
        <WorkloadsTable
          workloads={[mockWorkload]}
          selectedIds={[]}
          onSelect={vi.fn()}
          sortBy="display_name"
          sortDir="asc"
          onSort={vi.fn()}
        />
      </MemoryRouter>
    );
    expect(screen.getByText("web-api")).toBeDefined();
    expect(screen.getByText("healthy")).toBeDefined();
    expect(screen.getByText("keylime")).toBeDefined();
  });

  it("renders empty state when no workloads", () => {
    render(
      <MemoryRouter>
        <WorkloadsTable
          workloads={[]}
          selectedIds={[]}
          onSelect={vi.fn()}
          sortBy="display_name"
          sortDir="asc"
          onSort={vi.fn()}
        />
      </MemoryRouter>
    );
    expect(screen.getByText("No workloads found")).toBeDefined();
  });

  it("shows selection checkbox", () => {
    render(
      <MemoryRouter>
        <WorkloadsTable
          workloads={[mockWorkload]}
          selectedIds={["aaa-bbb-ccc"]}
          onSelect={vi.fn()}
          sortBy="display_name"
          sortDir="asc"
          onSort={vi.fn()}
        />
      </MemoryRouter>
    );
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBeGreaterThan(0);
  });
});

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { api } from "src/services/api";
import { WorkloadState, WorkloadType, BackendType } from "src/utils/datatypes/globalDataTypes";

const mockWorkload = {
  id: "aaa-bbb-ccc",
  ipa_principal: "web-api@IPA.EXAMPLE",
  display_name: "web-api",
  workload_type: WorkloadType.SERVICE,
  current_state: WorkloadState.HEALTHY,
  backend_type: BackendType.KEYLIME,
  stale_ttl_seconds: 3600,
  registered_at: "2026-10-17T12:00:00Z",
  last_attested_at: "2026-10-17T13:00:00Z",
  metadata: { env: "prod" },
};

vi.mock("src/services/rpcWorkloads", () => ({
  useGetWorkloadQuery: () => ({
    data: mockWorkload,
    isLoading: false,
  }),
  useGetWorkloadAttestationsQuery: () => ({
    data: { items: [], total: 0, start_index: 0, count: 25 },
    isLoading: false,
  }),
  useGetWorkloadTransitionsQuery: () => ({
    data: { items: [], total: 0, start_index: 0, count: 25 },
    isLoading: false,
  }),
  useAttestWorkloadMutation: () => [vi.fn(), { isLoading: false }],
  useRemediateWorkloadMutation: () => [vi.fn(), { isLoading: false }],
  useRevokeWorkloadMutation: () => [vi.fn(), { isLoading: false }],
}));

import WorkloadDetail from "../WorkloadDetail";

function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (gDM) => gDM().concat(api.middleware),
  });
}

function renderDetail() {
  return render(
    <Provider store={makeStore()}>
      <MemoryRouter initialEntries={["/workloads/aaa-bbb-ccc"]}>
        <Routes>
          <Route path="/workloads/:workloadId" element={<WorkloadDetail />} />
        </Routes>
      </MemoryRouter>
    </Provider>
  );
}

describe("WorkloadDetail", () => {
  it("renders workload name and state", () => {
    renderDetail();
    expect(screen.getByText("web-api")).toBeDefined();
    expect(screen.getAllByText("healthy").length).toBeGreaterThan(0);
  });

  it("renders IPA principal subtitle", () => {
    renderDetail();
    expect(screen.getByText("web-api@IPA.EXAMPLE")).toBeDefined();
  });

  it("renders 4 tabs", () => {
    renderDetail();
    expect(screen.getByText("Overview")).toBeDefined();
    expect(screen.getByText("Attestation History")).toBeDefined();
    expect(screen.getByText("Transitions")).toBeDefined();
    expect(screen.getByText("Vulnerabilities")).toBeDefined();
  });

  it("shows Attest button for HEALTHY state", () => {
    renderDetail();
    expect(screen.getByRole("button", { name: "Attest" })).toBeDefined();
  });
});

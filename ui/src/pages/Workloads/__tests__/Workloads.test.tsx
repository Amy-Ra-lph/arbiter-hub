import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { api } from "src/services/api";
import { WorkloadState, WorkloadType, BackendType } from "src/utils/datatypes/globalDataTypes";

const mockWorkloads = [
  {
    id: "aaa",
    ipa_principal: "web@IPA.EXAMPLE",
    display_name: "web-api",
    workload_type: WorkloadType.SERVICE,
    current_state: WorkloadState.HEALTHY,
    backend_type: BackendType.KEYLIME,
    stale_ttl_seconds: 3600,
    registered_at: "2026-10-17T12:00:00Z",
    last_attested_at: "2026-10-17T13:00:00Z",
    metadata: {},
  },
];

vi.mock("src/services/rpcWorkloads", () => ({
  useGetWorkloadsQuery: () => ({
    data: { items: mockWorkloads, total: 1, start_index: 0, count: 25 },
    isLoading: false,
    isFetching: false,
  }),
  useCreateWorkloadMutation: () => [vi.fn(), { isLoading: false }],
  useDeleteWorkloadMutation: () => [vi.fn(), { isLoading: false }],
}));

import Workloads from "../Workloads";

function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (gDM) => gDM().concat(api.middleware),
  });
}

describe("Workloads page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page title and table", () => {
    render(
      <Provider store={makeStore()}>
        <MemoryRouter>
          <Workloads />
        </MemoryRouter>
      </Provider>
    );
    expect(screen.getByText("Workloads")).toBeDefined();
    expect(screen.getByText("web-api")).toBeDefined();
  });

  it("has Add workload button", () => {
    render(
      <Provider store={makeStore()}>
        <MemoryRouter>
          <Workloads />
        </MemoryRouter>
      </Provider>
    );
    expect(
      screen.getByRole("button", { name: /add workload/i })
    ).toBeDefined();
  });

  it("has search input", () => {
    render(
      <Provider store={makeStore()}>
        <MemoryRouter>
          <Workloads />
        </MemoryRouter>
      </Provider>
    );
    expect(screen.getByPlaceholderText(/search/i)).toBeDefined();
  });
});

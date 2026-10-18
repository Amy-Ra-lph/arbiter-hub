import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { api } from "src/services/api";
import DeleteWorkloads from "../../Workloads/DeleteWorkloads";

function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (gDM) => gDM().concat(api.middleware),
  });
}

describe("DeleteWorkloads modal", () => {
  it("shows selected count", () => {
    render(
      <Provider store={makeStore()}>
        <DeleteWorkloads
          isOpen
          onClose={vi.fn()}
          selectedIds={["aaa", "bbb"]}
          onComplete={vi.fn()}
        />
      </Provider>
    );
    expect(screen.getAllByText(/2 workload/).length).toBeGreaterThan(0);
  });

  it("has danger-styled delete button", () => {
    render(
      <Provider store={makeStore()}>
        <DeleteWorkloads
          isOpen
          onClose={vi.fn()}
          selectedIds={["aaa"]}
          onComplete={vi.fn()}
        />
      </Provider>
    );
    const btn = screen.getByRole("button", { name: /delete/i });
    expect(btn.classList.toString()).toContain("danger");
  });
});

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { api } from "src/services/api";
import AddWorkload from "../../Workloads/AddWorkload";

function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (gDM) => gDM().concat(api.middleware),
  });
}

function getSubmitButton() {
  return screen.getByRole("button", { name: "Register Workload" });
}

describe("AddWorkload modal", () => {
  it("renders form fields when open", () => {
    render(
      <Provider store={makeStore()}>
        <AddWorkload isOpen onClose={vi.fn()} />
      </Provider>
    );
    expect(screen.getByLabelText("Display Name")).toBeDefined();
    expect(screen.getByLabelText("IPA Principal")).toBeDefined();
    expect(getSubmitButton()).toBeDefined();
  });

  it("disables submit when required fields empty", () => {
    render(
      <Provider store={makeStore()}>
        <AddWorkload isOpen onClose={vi.fn()} />
      </Provider>
    );
    expect(getSubmitButton().hasAttribute("disabled")).toBe(true);
  });

  it("enables submit when fields filled", () => {
    render(
      <Provider store={makeStore()}>
        <AddWorkload isOpen onClose={vi.fn()} />
      </Provider>
    );
    fireEvent.change(screen.getByLabelText("Display Name"), {
      target: { value: "test-workload" },
    });
    fireEvent.change(screen.getByLabelText("IPA Principal"), {
      target: { value: "test@IPA.EXAMPLE" },
    });
    expect(getSubmitButton().hasAttribute("disabled")).toBe(false);
  });
});

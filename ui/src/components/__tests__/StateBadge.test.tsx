import { render, screen } from "@testing-library/react";
import { describe, test, expect } from "vitest";
import StateBadge from "../StateBadge";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";

describe("StateBadge", () => {
  test("renders healthy state with text", () => {
    render(<StateBadge state={WorkloadState.HEALTHY} />);
    expect(screen.getByText("healthy")).toBeInTheDocument();
  });

  test("renders failed state with text", () => {
    render(<StateBadge state={WorkloadState.FAILED} />);
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  test("renders all seven states without crashing", () => {
    const states = Object.values(WorkloadState);
    expect(states).toHaveLength(7);
    states.forEach((state) => {
      const { unmount } = render(<StateBadge state={state} />);
      expect(screen.getByText(state.replace("_", " "))).toBeInTheDocument();
      unmount();
    });
  });
});

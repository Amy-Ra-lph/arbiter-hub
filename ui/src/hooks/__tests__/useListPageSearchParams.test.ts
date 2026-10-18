import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockSearchParams = new URLSearchParams();
const mockSetSearchParams = vi.fn();

vi.mock("react-router-dom", () => ({
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}));

import { useListPageSearchParams } from "../useListPageSearchParams";

describe("useListPageSearchParams", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const key of [...mockSearchParams.keys()]) {
      mockSearchParams.delete(key);
    }
  });

  it("returns defaults when URL has no params", () => {
    const { result } = renderHook(() => useListPageSearchParams());
    expect(result.current.page).toBe(1);
    expect(result.current.perPage).toBe(25);
    expect(result.current.search).toBe("");
    expect(result.current.sortBy).toBe("created_at");
    expect(result.current.sortDir).toBe("desc");
  });

  it("reads page and perPage from URL", () => {
    mockSearchParams.set("page", "3");
    mockSearchParams.set("perPage", "50");
    const { result } = renderHook(() => useListPageSearchParams());
    expect(result.current.page).toBe(3);
    expect(result.current.perPage).toBe(50);
  });

  it("reads search, sortBy, sortDir from URL", () => {
    mockSearchParams.set("search", "web-api");
    mockSearchParams.set("sortBy", "display_name");
    mockSearchParams.set("sortDir", "asc");
    const { result } = renderHook(() => useListPageSearchParams());
    expect(result.current.search).toBe("web-api");
    expect(result.current.sortBy).toBe("display_name");
    expect(result.current.sortDir).toBe("asc");
  });

  it("setPage updates search params", () => {
    const { result } = renderHook(() => useListPageSearchParams());
    act(() => result.current.setPage(5));
    expect(mockSetSearchParams).toHaveBeenCalledWith(
      expect.any(Function),
      { replace: true }
    );
  });

  it("setSearch resets page to 1", () => {
    mockSearchParams.set("page", "3");
    const { result } = renderHook(() => useListPageSearchParams());
    act(() => result.current.setSearch("test"));
    const updateFn = mockSetSearchParams.mock.calls[0][0];
    const params = new URLSearchParams();
    params.set("page", "3");
    const updated = updateFn(params);
    expect(updated.get("search")).toBe("test");
    expect(updated.get("page")).toBe("1");
  });
});

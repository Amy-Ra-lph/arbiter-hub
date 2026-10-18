import { useSearchParams } from "react-router-dom";
import { useCallback, useMemo } from "react";

interface ListPageParams {
  page: number;
  perPage: number;
  search: string;
  sortBy: string;
  sortDir: "asc" | "desc";
  setPage: (page: number) => void;
  setPerPage: (perPage: number) => void;
  setSearch: (search: string) => void;
  setSortBy: (sortBy: string) => void;
  setSortDir: (dir: "asc" | "desc") => void;
}

export function useListPageSearchParams(defaults?: {
  sortBy?: string;
  sortDir?: "asc" | "desc";
  perPage?: number;
}): ListPageParams {
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Number(searchParams.get("page")) || 1;
  const perPage = Number(searchParams.get("perPage")) || defaults?.perPage || 25;
  const search = searchParams.get("search") ?? "";
  const sortBy = searchParams.get("sortBy") ?? defaults?.sortBy ?? "created_at";
  const sortDir = (searchParams.get("sortDir") as "asc" | "desc") ?? defaults?.sortDir ?? "desc";

  const update = useCallback(
    (key: string, value: string, resetPage = false) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set(key, value);
          if (resetPage) next.set("page", "1");
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  return useMemo(
    () => ({
      page,
      perPage,
      search,
      sortBy,
      sortDir,
      setPage: (p: number) => update("page", String(p)),
      setPerPage: (pp: number) => update("perPage", String(pp), true),
      setSearch: (s: string) => update("search", s, true),
      setSortBy: (sb: string) => update("sortBy", sb),
      setSortDir: (sd: "asc" | "desc") => update("sortDir", sd),
    }),
    [page, perPage, search, sortBy, sortDir, update]
  );
}

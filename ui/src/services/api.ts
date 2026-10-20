import { createApi, fetchBaseQuery, retry } from "@reduxjs/toolkit/query/react";
import { getStoredToken } from "src/auth/useAuth";

const baseQuery = fetchBaseQuery({
  baseUrl: "/api",
  prepareHeaders: (headers) => {
    const token = getStoredToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    return headers;
  },
});

const baseQueryWithRetry = retry(baseQuery, { maxRetries: 3 });

export const api = createApi({
  reducerPath: "arbiterApi",
  baseQuery: baseQueryWithRetry,
  refetchOnReconnect: true,
  tagTypes: ["Workload", "Policy", "Backend", "Audit", "KBSSecret"],
  endpoints: () => ({}),
});

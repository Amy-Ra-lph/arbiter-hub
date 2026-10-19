import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import { getStoredToken } from "src/auth/useAuth";

export const api = createApi({
  reducerPath: "arbiterApi",
  baseQuery: fetchBaseQuery({
    baseUrl: "/api",
    prepareHeaders: (headers) => {
      const token = getStoredToken();
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
      return headers;
    },
  }),
  tagTypes: ["Workload", "Policy", "Backend", "Audit", "KBSSecret"],
  endpoints: () => ({}),
});

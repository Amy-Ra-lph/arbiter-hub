import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

export const api = createApi({
  reducerPath: "arbiterApi",
  baseQuery: fetchBaseQuery({ baseUrl: "/api" }),
  tagTypes: ["Workload", "Policy", "Backend", "Audit", "KBSSecret"],
  endpoints: () => ({}),
});

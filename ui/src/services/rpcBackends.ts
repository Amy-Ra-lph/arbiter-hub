import { api } from "./api";
import type { BackendHealth } from "src/utils/datatypes/globalDataTypes";

const backendsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getBackends: builder.query<Record<string, BackendHealth>, void>({
      query: () => "/backends",
      providesTags: ["Backend"],
    }),
  }),
});

export const { useGetBackendsQuery } = backendsApi;

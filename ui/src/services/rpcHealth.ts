import { api } from "./api";

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  node_id: string;
  backends_healthy: boolean;
  backend_count: number;
}

const healthApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getHealth: builder.query<HealthResponse, void>({
      query: () => "/health",
    }),
  }),
});

export const { useGetHealthQuery } = healthApi;

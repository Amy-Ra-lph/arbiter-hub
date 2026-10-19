import { api } from "./api";

interface WhoamiResponse {
  principal: string;
  roles: string[];
  actor_type: string;
}

const authApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getWhoami: builder.query<WhoamiResponse, void>({
      query: () => "/auth/whoami",
    }),
  }),
});

export const { useGetWhoamiQuery } = authApi;

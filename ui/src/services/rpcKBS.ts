import { api } from "./api";
import type { KBSSecret, PaginatedResponse } from "src/utils/datatypes/globalDataTypes";

interface StoreSecretPayload {
  repo: string;
  secret_type: string;
  tag: string;
  value: string;
  required_state: string;
  workload_scope?: string;
}

const kbsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getKBSSecrets: builder.query<PaginatedResponse<KBSSecret>, void>({
      query: () => "/kbs/v0/resources",
      providesTags: ["KBSSecret"],
    }),
    storeKBSSecret: builder.mutation<KBSSecret, StoreSecretPayload>({
      query: ({ repo, secret_type, tag, ...body }) => ({
        url: `/kbs/v0/resource/${repo}/${secret_type}/${tag}`,
        method: "POST",
        body,
      }),
      invalidatesTags: ["KBSSecret"],
    }),
  }),
});

export const { useGetKBSSecretsQuery, useStoreKBSSecretMutation } = kbsApi;

import { api } from "./api";
import type { Policy, PaginatedResponse } from "src/utils/datatypes/globalDataTypes";

interface PolicyCreatePayload {
  name: string;
  policy_type: string;
  scope: string | null;
  policy_content: Record<string, unknown>;
  active: boolean;
}

const policiesApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getPolicies: builder.query<PaginatedResponse<Policy>, void>({
      query: () => "/policies",
      providesTags: ["Policy"],
    }),
    createPolicy: builder.mutation<Policy, PolicyCreatePayload>({
      query: (body) => ({
        url: "/policies",
        method: "POST",
        body,
      }),
      invalidatesTags: ["Policy"],
    }),
  }),
});

export const { useGetPoliciesQuery, useCreatePolicyMutation } = policiesApi;

import { api } from "./api";
import type {
  Workload,
  AttestationRecord,
  StateTransition,
  PaginatedResponse,
} from "src/utils/datatypes/globalDataTypes";

interface WorkloadCreatePayload {
  ipa_principal: string;
  display_name: string;
  workload_type: string;
  backend_type: string;
  stale_ttl_seconds?: number;
  metadata?: Record<string, unknown>;
}

interface AttestResponse {
  workload_id: string;
  verdict: string;
  state: string;
  attestation_id: string;
  message?: string;
}

interface TransitionResponse {
  status: string;
  transition_id: string;
}

interface ListParams {
  startIndex?: number;
  count?: number;
  state?: string;
  workload_type?: string;
}

const workloadsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getWorkloads: builder.query<PaginatedResponse<Workload>, ListParams | void>({
      query: (params) => {
        const p = params ?? {};
        const searchParams = new URLSearchParams();
        if (p.startIndex) searchParams.set("startIndex", String(p.startIndex));
        if (p.count) searchParams.set("count", String(p.count));
        if (p.state) searchParams.set("state", p.state);
        if (p.workload_type)
          searchParams.set("workload_type", p.workload_type);
        const qs = searchParams.toString();
        return `/workloads${qs ? `?${qs}` : ""}`;
      },
      providesTags: ["Workload"],
    }),

    getWorkload: builder.query<Workload, string>({
      query: (id) => `/workloads/${id}`,
      providesTags: (_result, _err, id) => [{ type: "Workload", id }],
    }),

    createWorkload: builder.mutation<Workload, WorkloadCreatePayload>({
      query: (body) => ({
        url: "/workloads",
        method: "POST",
        body,
      }),
      invalidatesTags: ["Workload"],
    }),

    deleteWorkload: builder.mutation<{ status: string }, string>({
      query: (id) => ({
        url: `/workloads/${id}`,
        method: "DELETE",
      }),
      invalidatesTags: ["Workload", "Audit"],
    }),

    attestWorkload: builder.mutation<AttestResponse, string>({
      query: (id) => ({
        url: `/workloads/${id}/attest`,
        method: "POST",
      }),
      invalidatesTags: ["Workload", "Audit"],
    }),

    remediateWorkload: builder.mutation<
      TransitionResponse,
      { id: string; justification?: string }
    >({
      query: ({ id, justification }) => ({
        url: `/workloads/${id}/remediate`,
        method: "POST",
        body: { justification },
      }),
      invalidatesTags: ["Workload", "Audit"],
    }),

    revokeWorkload: builder.mutation<
      TransitionResponse,
      { id: string; justification: string }
    >({
      query: ({ id, justification }) => ({
        url: `/workloads/${id}/revoke`,
        method: "POST",
        body: { justification },
      }),
      invalidatesTags: ["Workload", "Audit"],
    }),

    getWorkloadAttestations: builder.query<
      PaginatedResponse<AttestationRecord>,
      { id: string; startIndex?: number; count?: number }
    >({
      query: ({ id, startIndex = 1, count = 25 }) =>
        `/workloads/${id}/attestations?startIndex=${startIndex}&count=${count}`,
    }),

    getWorkloadTransitions: builder.query<
      PaginatedResponse<StateTransition>,
      { id: string; startIndex?: number; count?: number }
    >({
      query: ({ id, startIndex = 1, count = 25 }) =>
        `/workloads/${id}/transitions?startIndex=${startIndex}&count=${count}`,
    }),
  }),
});

export const {
  useGetWorkloadsQuery,
  useGetWorkloadQuery,
  useCreateWorkloadMutation,
  useDeleteWorkloadMutation,
  useAttestWorkloadMutation,
  useRemediateWorkloadMutation,
  useRevokeWorkloadMutation,
  useGetWorkloadAttestationsQuery,
  useGetWorkloadTransitionsQuery,
} = workloadsApi;

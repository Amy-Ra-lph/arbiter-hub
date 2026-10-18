import { api } from "./api";
import type { AuditLogEntry, PaginatedResponse } from "src/utils/datatypes/globalDataTypes";

interface AuditParams {
  startIndex?: number;
  count?: number;
}

const auditApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getAudit: builder.query<PaginatedResponse<AuditLogEntry>, AuditParams | void>({
      query: (params) => {
        const p = params ?? {};
        const searchParams = new URLSearchParams();
        if (p.startIndex) searchParams.set("startIndex", String(p.startIndex));
        if (p.count) searchParams.set("count", String(p.count));
        const qs = searchParams.toString();
        return `/audit${qs ? `?${qs}` : ""}`;
      },
      providesTags: ["Audit"],
    }),
  }),
});

export const { useGetAuditQuery } = auditApi;

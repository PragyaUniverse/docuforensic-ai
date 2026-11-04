import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api } from "./index";
import type { Document, Field } from "./types";

export function useCase(caseId: string | undefined) {
  return useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.getCase(caseId!),
    enabled: !!caseId,
  });
}

export function useFindings(caseId: string | undefined) {
  return useQuery({
    queryKey: ["findings", caseId],
    queryFn: () => api.findings(caseId!),
    enabled: !!caseId,
  });
}

export function useCapabilities() {
  return useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api.capabilities(),
    staleTime: 30_000,
    retry: 1,
  });
}

/** Loads full documents for a case, keyed by id. Partial failures are returned, not hidden. */
export function useCaseDocuments(caseId: string | undefined) {
  const detail = useCase(caseId);
  const summaries = useMemo(() => detail.data?.documents ?? [], [detail.data]);
  const results = useQueries({
    queries: summaries.map((s) => ({
      queryKey: ["document", caseId, s.id, s.status, s.field_count],
      queryFn: () => api.getDocument(caseId!, s.id),
      enabled: !!caseId,
    })),
  });
  const docs = results.map((r) => r.data).filter(Boolean) as Document[];
  const key = docs.map((d) => `${d.id}:${d.fields.length}:${d.status}`).join("|");
  const byId = useMemo(() => {
    const m = new Map<string, Document>();
    docs.forEach((d) => m.set(d.id, d));
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const fieldsById = useMemo(() => {
    const m = new Map<string, Field>();
    byId.forEach((d) => d.fields.forEach((f) => m.set(f.id, f)));
    return m;
  }, [byId]);
  return {
    summaries,
    byId,
    fieldsById,
    isLoading: detail.isLoading || results.some((r) => r.isLoading),
    error: detail.error ?? results.find((r) => r.error)?.error ?? null,
    refetch: detail.refetch,
  };
}

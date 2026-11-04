import { ApiError, type Api } from "./client";
import type { ProgressEvent } from "./types";

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, init);
  } catch {
    throw new ApiError(0, "The analysis service is not reachable. Check that the backend is running on port 8000.");
  }
  if (!res.ok) {
    let detail = `The analysis service returned HTTP ${res.status}.`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Keep the generic message when the body is not JSON.
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const e = encodeURIComponent;

export const realApi: Api = {
  health: () => request("/health"),
  capabilities: () => request("/capabilities"),
  demoCases: () => request("/demo-cases"),
  loadDemoCase: (key) => request(`/demo-cases/${e(key)}/load`, { method: "POST" }),
  createCase: (name) => request("/cases", json({ name })),
  listCases: () => request("/cases"),
  getCase: (id) => request(`/cases/${e(id)}`),
  uploadDocuments: (caseId, files) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    return request(`/cases/${e(caseId)}/documents`, { method: "POST", body: form });
  },
  runCase: async (caseId) => {
    await request(`/cases/${e(caseId)}/run`, { method: "POST" });
  },
  subscribeProgress: (caseId, h) => {
    const es = new EventSource(`${BASE}/api/cases/${e(caseId)}/progress`);
    let finished = false;
    es.addEventListener("progress", (ev) => {
      try {
        h.onProgress(JSON.parse((ev as MessageEvent).data) as ProgressEvent);
      } catch {
        // Ignore a malformed frame; the next one carries full state.
      }
    });
    es.addEventListener("done", () => {
      finished = true;
      es.close();
      h.onDone();
    });
    es.onerror = () => {
      if (finished) return;
      es.close();
      h.onConnectionLost();
    };
    return () => {
      finished = true;
      es.close();
    };
  },
  getDocument: (caseId, docId) => request(`/cases/${e(caseId)}/documents/${e(docId)}`),
  pageImageUrl: (caseId, docId, page) => `${BASE}/api/cases/${e(caseId)}/documents/${e(docId)}/pages/${page}/image`,
  listOverlays: (caseId, docId, page) => request(`/cases/${e(caseId)}/documents/${e(docId)}/pages/${page}/overlays`),
  resolveUrl: (url) => (/^(https?:|data:|\/\/)/.test(url) ? url : `${BASE}${url.startsWith("/") ? "" : "/"}${url}`),
  fileUrl: (uri) => `${BASE}/api/files/${uri.split("/").map(e).join("/")}`,
  findings: (caseId) => request(`/cases/${e(caseId)}/findings`),
  reviewFinding: (id, decision, reviewer, note) =>
    request(`/findings/${e(id)}/review`, json({ decision, reviewer, note })),
  fields: (caseId) => request(`/cases/${e(caseId)}/fields`),
  entities: (caseId) => request(`/cases/${e(caseId)}/entities`),
  graph: (caseId) => request(`/cases/${e(caseId)}/graph`),
  dossier: (caseId) => request(`/cases/${e(caseId)}/dossier`),
  dossierPdfUrl: (caseId) => `${BASE}/api/cases/${e(caseId)}/dossier.pdf`,
  audit: (caseId) => request(`/cases/${e(caseId)}/audit`),
  verifyAudit: (caseId) => request(`/cases/${e(caseId)}/audit/verify`),
  tamperAudit: () => request("/audit/tamper-demo", { method: "POST" }),
  restoreAudit: async () => {
    await request("/audit/tamper-demo/restore", { method: "POST" });
  },
};

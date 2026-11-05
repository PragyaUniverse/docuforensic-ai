/** Login and analytics. Small enough to sit beside the main API client. */
const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

async function send<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, { credentials: "include", ...init });
  if (!res.ok) {
    let detail = `The service returned HTTP ${res.status}.`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Keep the generic message when the body is not JSON.
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export interface Me {
  auth_enabled: boolean;
  user: string | null;
}

export interface Analytics {
  cases: number;
  documents: number;
  by_risk: Record<string, number>;
  by_status: Record<string, number>;
  by_review: Record<string, number>;
  by_discrepancy: [string, number][];
  by_check: { check: string; count: number; dismissed: number }[];
  recent: { id: string; name: string; status: string; risk_level: string; created_at: string; documents: number; to_review: number }[];
}

export const accountApi = {
  me: () => send<Me>("/auth/me"),
  login: (username: string, password: string) =>
    send<{ user: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => send("/auth/logout", { method: "POST" }),
  analytics: () => send<Analytics>("/analytics"),
};

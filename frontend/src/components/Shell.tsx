import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import {
  Activity,
  Columns2,
  FileSearch,
  FileText,
  FolderOpen,
  Link as LinkIcon,
  ListChecks,
  Network,
  ScrollText,
  Table2,
  CloudOff,
  Database,
  Radio,
  Cpu,
  Unplug,
  FlaskConical,
} from "lucide-react";
import { MOCK_MODE } from "@/api";
import { useCapabilities, useCase } from "@/api/hooks";
import type { CapabilityMode } from "@/api/types";
import { cn } from "@/lib/utils";
import { HumanReviewPlate, RiskPlate } from "./StatusBadge";

const LAST = "docuforensic.lastCase";
function rememberCase(id: string) {
  try {
    sessionStorage.setItem(LAST, id);
  } catch {
    // Without storage, the nav simply forgets the case on the capabilities page.
  }
}
function lastCase(): string | null {
  try {
    return sessionStorage.getItem(LAST);
  } catch {
    return null;
  }
}

const NAV = [
  { to: "", label: "Case", icon: FolderOpen, end: true },
  { to: "pipeline", label: "Pipeline", icon: Activity },
  { to: "viewer", label: "Findings", icon: FileSearch },
  { to: "data", label: "Data", icon: Table2 },
  { to: "conflicts", label: "Conflicts", icon: Columns2 },
  { to: "graph", label: "Graph", icon: Network },
  { to: "dossier", label: "Dossier", icon: FileText },
  { to: "audit", label: "Audit", icon: LinkIcon },
];

const railItem =
  "flex w-full flex-col items-center gap-1 border-l-2 py-2.5 text-[11px] transition-colors";

const MODE: Record<CapabilityMode, { label: string; icon: typeof Cpu; hint: string }> = {
  offline: { label: "Offline", icon: CloudOff, hint: "No external calls are made." },
  demo_cache: { label: "Demo cache", icon: Database, hint: "LLM text replays recorded real runs." },
  live: { label: "Live LLM", icon: Radio, hint: "An LLM provider is answering." },
  deterministic: { label: "Deterministic", icon: Cpu, hint: "No LLM available. Explanations come from rules." },
};

function ModeBadge() {
  const caps = useCapabilities();
  const m = caps.data ? MODE[caps.data.mode] : null;
  const base =
    "flex items-center gap-1.5 border px-2 py-1 font-mono text-[11px] uppercase tracking-[0.06em] hover:bg-hover";
  if (caps.isError) {
    return (
      <NavLink to="/capabilities" className={cn(base, "border-man text-man")} title="The analysis service is not responding.">
        <Unplug className="size-3.5" aria-hidden /> Service unreachable
      </NavLink>
    );
  }
  if (!m) return <span className={cn(base, "border-line text-ink-3")}>Checking</span>;
  const Icon = m.icon;
  return (
    <NavLink to="/capabilities" title={m.hint} className={cn(base, "border-line-strong text-ink-2")}>
      <Icon className="size-3.5" aria-hidden /> {m.label}
    </NavLink>
  );
}

function CaseHeader({ caseId }: { caseId: string | null }) {
  const c = useCase(caseId ?? undefined);
  if (!caseId) return <span className="text-ink-3">No case open</span>;
  if (c.isLoading) return <span className="font-mono text-xs text-ink-3">Loading case</span>;
  if (!c.data) return <span className="text-ink-3">Case unavailable</span>;
  const { case: cs, documents } = c.data;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3">
      <div className="min-w-0">
        <div className="display truncate text-[14px] leading-tight">{cs.name}</div>
        <div className="truncate font-mono text-[11px] text-ink-3">
          {cs.id} · {documents.length} document{documents.length === 1 ? "" : "s"}
        </div>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <RiskPlate risk={cs.risk_level} assessed={cs.status === "complete"} />
        <HumanReviewPlate />
      </div>
    </div>
  );
}

export function Shell() {
  const match = useMatch("/cases/:caseId/*");
  const routeCase = match?.params.caseId ?? null;
  const location = useLocation();
  useEffect(() => {
    if (routeCase) rememberCase(routeCase);
  }, [routeCase]);
  const caseId = routeCase ?? (location.pathname === "/capabilities" ? lastCase() : null);

  return (
    <div className="flex h-full flex-col">
      {MOCK_MODE && (
        <div role="status" className="flex shrink-0 items-center justify-center gap-2 bg-inc py-1 font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-ground">
          <FlaskConical className="size-3.5" aria-hidden />
          Mock data: development fixtures, not analysis results
        </div>
      )}
      <header className="flex h-[54px] shrink-0 items-center gap-4 border-b border-line bg-panel pr-3">
        <NavLink to="/" className="flex h-full w-[76px] shrink-0 items-center justify-center border-r border-line hover:bg-hover" aria-label="DocuForensic AI home">
          <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
            <path d="M8 4h11l6 6v18H8z" fill="none" stroke="#eceae4" strokeWidth="2" />
            <rect x="11.5" y="14" width="10" height="7" fill="none" stroke="#ff5a4f" strokeWidth="2" />
          </svg>
        </NavLink>
        <NavLink to="/" className="hidden shrink-0 xl:block">
          <span className="display text-[15px]">DocuForensic</span>
          <span className="ml-1 font-mono text-[11px] text-ink-3">AI</span>
        </NavLink>
        <div className="hidden h-6 w-px bg-line xl:block" />
        <CaseHeader caseId={caseId} />
        <ModeBadge />
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Investigation" className="flex w-[76px] shrink-0 flex-col overflow-y-auto border-r border-line bg-panel">
          {NAV.map((n) => {
            const Icon = n.icon;
            if (!caseId) {
              return (
                <span key={n.label} aria-disabled className={cn(railItem, "border-transparent text-ink-3/45")}>
                  <Icon className="size-[18px]" aria-hidden />
                  {n.label}
                </span>
              );
            }
            return (
              <NavLink
                key={n.label}
                end={n.end}
                to={`/cases/${caseId}${n.to ? `/${n.to}` : ""}`}
                className={({ isActive }) =>
                  cn(railItem, isActive ? "border-ink bg-raised text-ink" : "border-transparent text-ink-3 hover:bg-hover hover:text-ink")
                }
              >
                <Icon className="size-[18px]" aria-hidden />
                {n.label}
              </NavLink>
            );
          })}
          <div className="mt-auto">
            <NavLink
              to="/capabilities"
              className={({ isActive }) =>
                cn(railItem, isActive ? "border-ink bg-raised text-ink" : "border-transparent text-ink-3 hover:bg-hover hover:text-ink")
              }
            >
              <ListChecks className="size-[18px]" aria-hidden />
              Limits
            </NavLink>
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                cn(railItem, isActive ? "border-ink bg-raised text-ink" : "border-transparent text-ink-3 hover:bg-hover hover:text-ink")
              }
            >
              <ScrollText className="size-[18px]" aria-hidden />
              Cases
            </NavLink>
          </div>
        </nav>
        <main className="min-w-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function PageHeading({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow: string;
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-6 py-4">
      <div className="min-w-0">
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="display mt-0.5 text-[22px] leading-tight">{title}</h1>
        {children && <p className="mt-1 max-w-[78ch] text-ink-2">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

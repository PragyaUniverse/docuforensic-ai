import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import { ArrowLeft, Clock, FileText, GitCompare, LayoutDashboard, Moon, ScanSearch, ScrollText, Sun } from "lucide-react";
import { motion } from "framer-motion";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MOCK_MODE } from "@/api";
import { accountApi } from "@/api/account";
import { LoginScreen } from "@/screens/Login";
import { Assistant } from "./Assistant";
import { TourHost } from "./Tour";
import { useCapabilities, useCase } from "@/api/hooks";
import type { CapabilityMode } from "@/api/types";
import { cn } from "@/lib/utils";
import { setTheme, useTheme } from "@/lib/theme";
import { RiskPlate } from "./StatusBadge";
import { openDocChat } from "@/lib/assistant";
import { caseCode, caseState } from "@/lib/case";
import { useFindings } from "@/api/hooks";

const LAST = "docuforensic.lastCase";
function rememberCase(id: string) {
  try {
    sessionStorage.setItem(LAST, id);
  } catch {
    // Without storage, the nav simply forgets the case on the capabilities page.
  }
}

const TABS = [
  { to: "", label: "Overview", icon: LayoutDashboard, also: ["pipeline"] },
  { to: "viewer", label: "Findings", icon: ScanSearch, also: [] },
  { to: "conflicts", label: "Compare", icon: GitCompare, also: ["graph"] },
  { to: "data", label: "Evidence", icon: FileText, also: [] },
  { to: "dossier", label: "Report", icon: ScrollText, also: [] },
  { to: "audit", label: "Timeline", icon: Clock, also: [] },
];

const MODE: Record<CapabilityMode, { label: string; hint: string }> = {
  offline: { label: "Offline", hint: "Nothing leaves this computer." },
  demo_cache: { label: "Recorded AI", hint: "AI explanations are replays of earlier real runs, not live answers." },
  live: { label: "AI live", hint: "An AI model is adding notes to explanations." },
  deterministic: { label: "Rules", hint: "No AI model is available. Explanations come from fixed rules." },
};

/** Doc's status in the header. It opens the investigation assistant. */
function DocStatus() {
  const caps = useCapabilities();
  const down = caps.isError;
  const m = caps.data ? MODE[caps.data.mode] : null;
  return (
    <button
      type="button"
      data-tour="doc"
      onClick={openDocChat}
      title={down ? "The analysis service is not responding." : `Ask Doc. ${m?.hint ?? ""}`}
      className={cn(
        "group flex cursor-pointer items-center gap-2 rounded-full border px-2.5 py-1 transition-colors duration-150",
        down ? "border-man/40 text-man" : "border-[rgba(var(--color-glow),0.28)] text-ink hover:border-[rgba(var(--color-glow),0.6)] hover:bg-[rgba(var(--color-glow),0.06)]",
      )}
    >
      {down ? <span className="size-[7px] rounded-full bg-man" /> : <span className="status-dot" />}
      <span className="font-mono text-[11px] font-semibold tracking-[0.14em]">{down ? "DOC OFFLINE" : "DOC ONLINE"}</span>
      {m && !down && <span className="hidden font-mono text-[11px] tracking-[0.08em] text-ink-3 md:inline">· {m.label.toUpperCase()}</span>}
    </button>
  );
}

function Account() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => accountApi.me() });
  if (!me.data?.user) return null;
  return (
    <button
      type="button"
      className="cursor-pointer text-[13px] text-ink-2 hover:text-ink"
      title={`Signed in as ${me.data.user}`}
      onClick={() => accountApi.logout().then(() => qc.invalidateQueries())}
    >
      Sign out
    </button>
  );
}

function ThemeToggle() {
  const theme = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  const Icon = theme === "dark" ? Sun : Moon;
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-hover hover:text-ink"
    >
      <motion.span key={theme} initial={{ rotate: -45, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} transition={{ duration: 0.22 }}>
        <Icon className="size-4" aria-hidden />
      </motion.span>
    </button>
  );
}

const TONE_TEXT = { cyan: "text-accent", green: "text-ok", amber: "text-inc", muted: "text-ink-3", red: "text-man" } as const;
const TONE_DOT = { cyan: "bg-accent", green: "bg-ok", amber: "bg-inc", muted: "bg-ink-3", red: "bg-man" } as const;

function CaseBar({ caseId, rest }: { caseId: string; rest: string }) {
  const c = useCase(caseId);
  const f = useFindings(caseId);
  const cs = c.data?.case;
  const toReview = (f.data ?? []).filter((x) => x.status !== "OBSERVATION" && x.review.decision === "pending").length;
  const state = cs ? caseState(cs, f.data ? toReview : undefined) : null;
  return (
    <div className="border-t border-line">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 pb-1 pt-3">
        <NavLink to="/" className="group flex items-center gap-1.5 font-mono text-[11px] tracking-[0.14em] text-ink-3 hover:text-ink">
          <ArrowLeft className="size-3.5 transition-transform group-hover:-translate-x-0.5" aria-hidden />
          INVESTIGATIONS
        </NavLink>
        <span className="h-4 w-px bg-line-strong" aria-hidden />
        <span className="font-mono text-[11px] tracking-[0.12em] text-ink-3">{caseCode(caseId)}</span>
        <h1 className="min-w-0 truncate text-[17px] font-semibold tracking-tight text-ink">{cs?.name ?? "Loading"}</h1>
        {state && (
          <span className={cn("flex items-center gap-1.5 font-mono text-[11px] font-medium tracking-[0.12em]", TONE_TEXT[state.tone])}>
            {state.tone === "cyan" ? <span className="status-dot" /> : <span className={cn("size-[7px] rounded-full", TONE_DOT[state.tone])} />}
            {state.label.toUpperCase()}
          </span>
        )}
        {cs?.status === "complete" && (
          <span className="ml-auto hidden md:block">
            <RiskPlate risk={cs.risk_level} />
          </span>
        )}
      </div>
      <nav aria-label="This case" className="flex gap-1 overflow-x-auto px-3">
        {TABS.map((t) => {
          const active = rest === t.to || t.also.includes(rest);
          const Icon = t.icon;
          return (
            <NavLink
              key={t.label}
              end={!t.to}
              to={`/cases/${caseId}${t.to ? `/${t.to}` : ""}`}
              data-tour={`tab-${t.to || "overview"}`}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex shrink-0 items-center gap-2 px-3 py-2.5 text-[13.5px] transition-colors duration-150",
                active ? "font-medium text-ink" : "text-ink-3 hover:text-ink",
              )}
            >
              <Icon className={cn("size-4", active ? "text-accent" : "")} aria-hidden />
              {t.label}
              {active && (
                <motion.span
                  layoutId="case-tab"
                  transition={{ type: "spring", stiffness: 420, damping: 36 }}
                  className="absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-accent shadow-[0_0_12px_rgba(var(--color-glow),0.9)]"
                />
              )}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}

const NAV_LINK = ({ isActive }: { isActive: boolean }) =>
  cn("rounded-md px-2.5 py-1.5 text-[13.5px] transition-colors duration-150", isActive ? "bg-hover text-ink" : "text-ink-2 hover:text-ink");

export function Shell() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => accountApi.me(), retry: false });
  const match = useMatch("/cases/:caseId/*");
  const routeCase = match?.params.caseId ?? null;
  const rest = match?.params["*"] ?? "";
  const location = useLocation();
  useEffect(() => {
    if (routeCase) rememberCase(routeCase);
  }, [routeCase]);

  if (!MOCK_MODE && me.data?.auth_enabled && !me.data.user) return <LoginScreen />;

  return (
    <div className="flex h-full flex-col">
      {MOCK_MODE && (
        <div role="status" className="shrink-0 bg-inc-dim py-1 text-center text-[13px] font-medium text-inc">
          Mock data: development fixtures, not analysis results
        </div>
      )}
      <header className="relative z-20 shrink-0 border-b border-line bg-[color-mix(in_srgb,var(--color-ground)_82%,transparent)] backdrop-blur-xl">
        <div className="flex h-14 items-center gap-6 px-5">
          <NavLink to="/" className="group flex shrink-0 items-center gap-2.5">
            <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
              <circle cx="12" cy="12" r="10" fill="none" stroke="var(--color-accent)" strokeOpacity="0.45" strokeWidth="1.3" />
              <circle cx="12" cy="12" r="6" fill="none" stroke="var(--color-accent)" strokeWidth="1.6" />
              <circle cx="12" cy="12" r="2.2" fill="var(--color-accent)" />
            </svg>
            <span className="font-mono text-[13px] font-semibold tracking-[0.22em] text-ink">DOCUFORENSIC</span>
          </NavLink>
          <nav data-tour="header-links" aria-label="Main" className="hidden items-center gap-1 sm:flex">
            <NavLink to="/" end className={NAV_LINK}>
              Investigations
            </NavLink>
            <NavLink to="/analytics" className={NAV_LINK}>
              Analytics
            </NavLink>
            <NavLink to="/capabilities" className={NAV_LINK}>
              About
            </NavLink>
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <DocStatus />
            <Account />
            <span data-tour="theme">
              <ThemeToggle />
            </span>
          </div>
        </div>
        {routeCase && <CaseBar caseId={routeCase} rest={rest} />}
      </header>
      <main className="relative min-h-0 min-w-0 flex-1 overflow-auto">
        <div key={location.pathname} className="page-in h-full">
          <Outlet />
        </div>
      </main>
      {!MOCK_MODE && <TourHost />}
      {!MOCK_MODE && <Assistant floating={location.pathname !== "/" && !location.pathname.endsWith("/pipeline")} />}
    </div>
  );
}

export function PageHeading({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow?: string;
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 px-6 pb-3 pt-7">
      <div className="min-w-0">
        {eyebrow && <div className="mono-label mb-1.5">{eyebrow}</div>}
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-ink">{title}</h1>
        {children && <p className="mt-1.5 max-w-[70ch] text-[14.5px] text-ink-2">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}


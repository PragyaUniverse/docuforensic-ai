import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import { Moon, Sun } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MOCK_MODE } from "@/api";
import { accountApi } from "@/api/account";
import { LoginScreen } from "@/screens/Login";
import { useCapabilities, useCase } from "@/api/hooks";
import type { CapabilityMode } from "@/api/types";
import { cn } from "@/lib/utils";
import { setTheme, useTheme } from "@/lib/theme";
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

const TABS = [
  { to: "", label: "Overview", also: ["pipeline"] },
  { to: "viewer", label: "Findings", also: [] },
  { to: "conflicts", label: "Compare documents", also: ["graph"] },
  { to: "data", label: "Extracted data", also: [] },
  { to: "dossier", label: "Report", also: [] },
  { to: "audit", label: "History", also: [] },
];

const MODE: Record<CapabilityMode, { label: string; hint: string }> = {
  offline: { label: "Offline", hint: "Nothing leaves this computer." },
  demo_cache: { label: "AI notes: recorded earlier", hint: "AI explanations are replays of earlier real runs, not live answers." },
  live: { label: "AI notes: on", hint: "An AI model is writing explanations." },
  deterministic: { label: "AI notes: off", hint: "No AI model is available. Explanations come from fixed rules." },
};

function ModeNote() {
  const caps = useCapabilities();
  if (caps.isError) {
    return (
      <NavLink to="/capabilities" className="text-[13px] font-medium text-man underline underline-offset-2" title="The analysis service is not responding.">
        Can't reach the service
      </NavLink>
    );
  }
  const m = caps.data ? MODE[caps.data.mode] : null;
  return (
    <NavLink to="/capabilities" title={m?.hint} className="hidden text-[13px] text-ink-3 hover:text-ink hover:underline sm:block">
      {m?.label ?? ""}
    </NavLink>
  );
}

function Account() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => accountApi.me() });
  if (!me.data?.user) return null;
  return (
    <button
      type="button"
      className="cursor-pointer text-[14px] text-ink-2 hover:text-ink hover:underline"
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
      className="flex size-8 cursor-pointer items-center justify-center rounded-md text-ink-2 hover:bg-hover hover:text-ink"
    >
      <Icon className="size-4" aria-hidden />
    </button>
  );
}

function CaseTitle({ caseId }: { caseId: string }) {
  const c = useCase(caseId);
  if (!c.data) return <span className="text-ink-3">{c.isLoading ? "Loading" : "Case unavailable"}</span>;
  const { case: cs } = c.data;
  return (
    <>
      <span className="truncate font-medium text-ink">{cs.name}</span>
      {cs.status === "complete" && (
        <span className="ml-auto hidden shrink-0 items-center gap-3 md:flex">
          <RiskPlate risk={cs.risk_level} />
          <HumanReviewPlate />
        </span>
      )}
    </>
  );
}

export function Shell() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => accountApi.me(), retry: false });
  const match = useMatch("/cases/:caseId/*");
  const routeCase = match?.params.caseId ?? null;
  const rest = match?.params["*"] ?? "";
  const location = useLocation();
  useEffect(() => {
    if (routeCase) rememberCase(routeCase);
  }, [routeCase]);
  const caseId = routeCase ?? (location.pathname === "/capabilities" ? lastCase() : null);

  if (!MOCK_MODE && me.data?.auth_enabled && !me.data.user) return <LoginScreen />;

  return (
    <div className="flex h-full flex-col">
      {MOCK_MODE && (
        <div role="status" className="shrink-0 bg-inc-dim py-1 text-center text-[13px] font-medium text-inc">
          Mock data: development fixtures, not analysis results
        </div>
      )}
      <header className="shrink-0 border-b border-line bg-panel">
        <div className="flex h-12 items-center gap-3 px-5">
          <NavLink to="/" className="shrink-0 font-semibold text-ink">
            DocuForensic
          </NavLink>
          {caseId && (
            <>
              <span aria-hidden className="text-ink-3">/</span>
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <CaseTitle caseId={caseId} />
              </div>
            </>
          )}
          <div className="ml-auto flex shrink-0 items-center gap-4 pl-4">
            <ModeNote />
            <NavLink to="/" end className="text-[14px] text-ink-2 hover:text-ink hover:underline">
              All cases
            </NavLink>
            <NavLink to="/analytics" className="hidden text-[14px] text-ink-2 hover:text-ink hover:underline sm:block">
              Analytics
            </NavLink>
            <NavLink to="/capabilities" className="text-[14px] text-ink-2 hover:text-ink hover:underline">
              About
            </NavLink>
            <Account />
            <ThemeToggle />
          </div>
        </div>
        {routeCase && (
          <nav aria-label="This case" className="flex gap-1 overflow-x-auto px-3">
            {TABS.map((t) => {
              const active = rest === t.to || t.also.includes(rest);
              return (
                <NavLink
                  key={t.label}
                  end={!t.to}
                  to={`/cases/${routeCase}${t.to ? `/${t.to}` : ""}`}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "shrink-0 border-b-2 px-3 pb-2 pt-1 text-[14px]",
                    active ? "border-accent font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink",
                  )}
                >
                  {t.label}
                </NavLink>
              );
            })}
          </nav>
        )}
      </header>
      <main className="relative min-h-0 min-w-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

export function PageHeading({
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
    <div className="flex flex-wrap items-start justify-between gap-3 px-6 pb-2 pt-6">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold leading-tight text-ink">{title}</h1>
        {children && <p className="mt-1 max-w-[70ch] text-ink-2">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

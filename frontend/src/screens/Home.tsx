import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, FileWarning, FileX, Files, GitCompare, Loader2, Plus, ScanSearch, ShieldCheck } from "lucide-react";
import { api } from "@/api";
import { accountApi } from "@/api/account";
import type { RiskLevel } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/states";
import { RiskPlate } from "@/components/StatusBadge";
import { Mascot } from "@/components/Mascot";
import { EvidenceNetwork } from "@/components/EvidenceNetwork";
import { openDocChat } from "@/lib/assistant";
import { caseCode, caseState, timeAgo } from "@/lib/case";
import { startTour } from "@/lib/tour";
import { cn } from "@/lib/utils";

const DEMOS: Record<string, { title: string; text: string; icon: typeof Files; tone: string }> = {
  case_a_clean: { title: "Consistent application", text: "Every document agrees. A baseline for what normal looks like.", icon: ShieldCheck, tone: "text-ok" },
  case_b_visual: { title: "Altered salary slip", text: "A changed figure, a pasted photo, a copied signature.", icon: ScanSearch, tone: "text-man" },
  case_c_crossdoc: { title: "Conflicting documents", text: "Each looks clean. Together, names, dates and amounts disagree.", icon: GitCompare, tone: "text-inc" },
  case_d_pdf: { title: "Edited PDF", text: "The visible figure isn't the one stored in the file.", icon: FileWarning, tone: "text-inc" },
  unsupported_files: { title: "Unreadable files", text: "Corrupt and unsupported files, handled without a crash.", icon: FileX, tone: "text-ink-3" },
};

const FACTS = [
  ["15", "Forensic checks"],
  ["9", "Cross-document checks"],
  ["100%", "Runs on this machine"],
];

export function HomeScreen() {
  const nav = useNavigate();
  const [name, setName] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const demos = useQuery({ queryKey: ["demo-cases"], queryFn: () => api.demoCases() });
  const cases = useQuery({ queryKey: ["analytics"], queryFn: () => accountApi.analytics() });
  const load = useMutation({ mutationFn: (key: string) => api.loadDemoCase(key), onSuccess: (c) => nav(`/cases/${c.id}`) });
  const create = useMutation({ mutationFn: () => api.createCase(name.trim() || "Untitled investigation"), onSuccess: (c) => nav(`/cases/${c.id}`) });
  const recent = cases.data?.recent ?? [];

  const begin = () => {
    card.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => input.current?.focus({ preventScroll: true }), 350);
  };

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-16 px-6 pb-20">
      <section className="relative grid items-center gap-8 pt-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,600px)] lg:pt-20">
        <div className="relative z-10">
          <div className="mono-label flex items-center gap-2 text-accent">
            <span className="status-dot" /> AI document forensics
          </div>
          <h1 className="text-gradient mt-5 text-[46px] font-semibold leading-[1.02] tracking-[-0.035em] sm:text-[64px]">
            Document forensics,
            <br />
            reimagined.
          </h1>
          <p className="mt-5 max-w-[520px] text-[17px] leading-relaxed text-ink-2">
            Investigate documents with AI-assisted comparison, anomaly detection and evidence tracing. Every finding links back
            to the exact spot it came from, and the final call stays with you.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button variant="primary" size="lg" onClick={begin}>
              <Plus aria-hidden /> Start investigation
            </Button>
            <button
              type="button"
              onClick={() => load.mutate("case_b_visual")}
              disabled={load.isPending}
              className="group inline-flex cursor-pointer items-center gap-1.5 text-[15px] font-medium text-ink-2 hover:text-ink"
            >
              {load.isPending && load.variables === "case_b_visual" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
              Explore demo case
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden />
            </button>
          </div>
          <dl className="mt-10 grid max-w-[520px] grid-cols-3 gap-x-6 gap-y-4 border-t border-line pt-5">
            {FACTS.map(([value, label]) => (
              <div key={label} className="flex flex-col-reverse justify-end">
                <dt className="mono-label mt-1.5">{label}</dt>
                <dd className="font-mono text-[24px] font-semibold leading-none text-ink">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="pointer-events-none absolute inset-0 -z-0 opacity-35 lg:relative lg:opacity-100">
          <div aria-hidden className="absolute inset-[10%] rounded-full bg-[radial-gradient(circle,rgba(var(--color-glow),0.14),transparent_65%)] blur-2xl" />
          <EvidenceNetwork className="relative h-full w-full lg:scale-[1.12]" />
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div ref={card} data-tour="start" className="panel scanline glow-cyan p-6">
          <div className="flex items-start justify-between gap-3">
            <div className="mono-label text-accent">New investigation</div>
            <Mascot mood={create.isPending || load.isPending ? "thinking" : "hello"} size={72} />
          </div>
          <h2 className="mt-2 text-[22px] font-semibold">Open a case</h2>
          <form
            className="mt-6"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <label className="mono-label" htmlFor="case-id">
              Case identifier
            </label>
            <input
              id="case-id"
              ref={input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Loan Application 1042"
              className="mt-2 h-12 w-full rounded-lg border border-line-strong bg-ground px-4 font-mono text-[15px] text-ink transition-[border-color,box-shadow] placeholder:text-ink-3 focus:border-[rgba(var(--color-glow),0.7)] focus:shadow-[0_0_0_4px_rgba(var(--color-glow),0.12)] focus:outline-none"
            />
            <p className="mt-3 text-[13.5px] text-ink-3">Add documents from the same application. Use only documents you're authorized to process.</p>
            <Button type="submit" variant="primary" className="mt-6 w-full" disabled={create.isPending}>
              {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              Open case <ArrowRight aria-hidden />
            </Button>
          </form>
          {create.isError && <ErrorState title="Could not open the case" error={create.error} />}
          <div className="mt-5 flex gap-4 text-[13px] text-ink-3">
            <button type="button" className="cursor-pointer hover:text-accent" onClick={openDocChat}>
              Ask Doc
            </button>
            <button type="button" className="cursor-pointer hover:text-accent" onClick={() => startTour("home")}>
              Take the tour
            </button>
          </div>
        </div>

        <div data-tour="examples">
          <div className="flex items-baseline justify-between">
            <div>
              <div className="mono-label">Demo evidence sets</div>
              <p className="mt-1 text-[13.5px] text-ink-3">Synthetic documents and fictional people.</p>
            </div>
          </div>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {demos.data?.map((d, i) => {
              const meta = DEMOS[d.key] ?? { title: d.name, text: d.description, icon: Files, tone: "text-ink-3" };
              const Icon = meta.icon;
              const busy = load.isPending && load.variables === d.key;
              return (
                <motion.li key={d.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i }}>
                  <button
                    type="button"
                    disabled={load.isPending}
                    onClick={() => load.mutate(d.key)}
                    className="panel group flex h-full w-full cursor-pointer items-start gap-3 p-4 text-left transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-[rgba(var(--color-glow),0.35)] hover:shadow-[0_0_0_1px_rgba(var(--color-glow),0.15),0_16px_40px_-20px_rgba(var(--color-glow),0.5)] disabled:cursor-default"
                  >
                    <span className={cn("mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border border-line bg-raised", meta.tone)}>
                      {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Icon className="size-4" aria-hidden />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-medium text-ink">{meta.title}</span>
                        <ArrowRight className="size-4 shrink-0 text-ink-3 transition-transform group-hover:translate-x-1 group-hover:text-accent" aria-hidden />
                      </span>
                      <span className="mt-0.5 block text-[13px] leading-snug text-ink-3">{meta.text}</span>
                      <span className="mt-2 block font-mono text-[10.5px] tracking-[0.12em] text-ink-3">{d.documents.length} EVIDENCE FILES</span>
                    </span>
                  </button>
                </motion.li>
              );
            })}
          </ul>
        </div>
      </section>

      {recent.length > 0 && (
        <section>
          <div className="flex items-end justify-between">
            <div className="mono-label">Active investigations</div>
            <Link to="/analytics" className="group flex items-center gap-1 text-[13px] text-ink-3 hover:text-ink">
              All analytics <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          </div>
          <ul className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {recent.slice(0, 6).map((c, i) => {
              const state = caseState({ status: c.status as "complete" }, c.to_review);
              return (
                <motion.li key={c.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}>
                  <Link
                    to={`/cases/${c.id}`}
                    className="panel group block p-5 transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-1 hover:border-[rgba(var(--color-glow),0.35)] hover:shadow-[0_0_0_1px_rgba(var(--color-glow),0.15),0_20px_48px_-22px_rgba(var(--color-glow),0.55)]"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] tracking-[0.14em] text-ink-3">{caseCode(c.id)}</span>
                      <RiskPlate risk={c.risk_level as RiskLevel} assessed={c.status === "complete"} />
                    </div>
                    <div className="mt-3 truncate text-[16px] font-semibold text-ink">{c.name}</div>
                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11.5px] text-ink-2">
                      <span>{c.documents} evidence</span>
                      <span className={c.findings ? "text-inc" : ""}>{c.findings} findings</span>
                      <span className={c.conflicts ? "text-man" : ""}>{c.conflicts} conflicts</span>
                    </div>
                    <div className="relative mt-4 flex items-center justify-between border-t border-line pt-3 text-[12.5px] text-ink-3">
                      <span className="transition-opacity group-hover:opacity-0">Opened {timeAgo(c.created_at)}</span>
                      <span className="absolute left-0 font-mono text-[11px] tracking-[0.1em] opacity-0 transition-opacity group-hover:opacity-100">
                        {state.label.toUpperCase()} · {c.to_review} TO REVIEW
                      </span>
                      <span className="flex items-center gap-1 font-mono text-[11px] tracking-[0.14em] text-ink-2 group-hover:text-accent">
                        OPEN <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-1" aria-hidden />
                      </span>
                    </div>
                  </Link>
                </motion.li>
              );
            })}
          </ul>
        </section>
      )}
      {load.isError && <ErrorState title="Could not open that demo case" error={load.error} />}
    </div>
  );
}

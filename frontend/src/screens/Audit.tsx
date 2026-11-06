import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ShieldCheck, ShieldX } from "lucide-react";
import { api } from "@/api";
import type { AuditEntry, AuditVerification } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { PageHeading } from "@/components/Shell";
import { docSays } from "@/lib/assistant";
import { cn, humanize } from "@/lib/utils";

const STAGE_LABEL: Record<string, string> = {
  submission: "Evidence secured",
  classification: "Evidence read and classified",
  ocr_extraction: "Entity extraction complete",
  structure: "Document structure mapped",
  visual_forensics: "Forensic checks complete",
  contextual_verification: "Internal consistency verified",
  cross_document: "Cross-document comparison complete",
  anomaly_investigation: "Anomaly investigation complete",
  evidence: "Evidence graph built",
  dossier: "Report compiled",
};

function describe(e: AuditEntry): { label: string; tone: "cyan" | "amber" | "red" | "green" | "muted" } {
  const p = e.payload as Record<string, unknown>;
  if (e.action.startsWith("stage.")) {
    const stage = e.action.slice(6);
    const failed = p.state === "failed" || p.state === "degraded";
    return { label: `${STAGE_LABEL[stage] ?? humanize(stage)}${failed ? " (with problems)" : ""}`, tone: failed ? "amber" : "cyan" };
  }
  if (e.action === "finding.recorded") {
    const status = String(p.status ?? "");
    const title = String(p.title ?? humanize(String(p.detector ?? "finding")));
    if (status === "POTENTIAL_MANIPULATION") return { label: `Potential manipulation: ${title}`, tone: "red" };
    if (status === "INCONSISTENCY") return { label: `Inconsistency: ${title}`, tone: "amber" };
    return { label: `Observation: ${title}`, tone: "muted" };
  }
  if (e.action === "finding.review") return { label: `Reviewer ${String(p.decision ?? "decided")} a finding`, tone: "green" };
  if (e.action === "case.created") return { label: "Investigation opened", tone: "cyan" };
  if (e.action === "case.started") return { label: "Forensic analysis started", tone: "cyan" };
  if (e.action === "case.finished") return { label: "Forensic analysis complete", tone: "green" };
  if (e.action === "document.submitted") return { label: `Evidence submitted: ${String(p.filename ?? "file")}`, tone: "cyan" };
  if (e.action.includes("tamper")) return { label: humanize(e.action.replace("audit.", "")), tone: "amber" };
  return { label: humanize(e.action), tone: "muted" };
}

const DOT = { cyan: "bg-accent shadow-[0_0_10px_rgba(var(--color-glow),0.9)]", amber: "bg-inc shadow-[0_0_10px_var(--color-inc)]", red: "bg-man shadow-[0_0_10px_var(--color-man)]", green: "bg-ok shadow-[0_0_8px_var(--color-ok)]", muted: "bg-line-strong" };
const TEXT = { cyan: "text-ink", amber: "text-inc", red: "text-man", green: "text-ok", muted: "text-ink-3" };

function Row({ e, bad, afterBad }: { e: AuditEntry; bad: boolean; afterBad: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (bad) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [bad]);
  const d = describe(e);
  const time = new Date(e.ts).toLocaleTimeString(undefined, { hour12: false });
  return (
    <li ref={ref} className={cn("relative", afterBad && "opacity-45")}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={cn("grid w-full cursor-pointer grid-cols-[78px_28px_minmax(0,1fr)_auto] items-start gap-2 rounded-lg py-2 pr-3 text-left transition-colors hover:bg-hover", bad && "bg-man-dim")}
      >
        <span className="pt-0.5 text-right font-mono text-[11.5px] text-ink-3">{time}</span>
        <span className="relative flex justify-center pt-1.5">
          <span className={cn("relative z-10 size-2 rounded-full", bad ? "bg-man shadow-[0_0_12px_var(--color-man)]" : DOT[d.tone])} />
        </span>
        <span className="min-w-0">
          <span className={cn("block truncate text-[13.5px] font-medium", bad ? "text-man" : TEXT[d.tone])}>{d.label}</span>
          <span className="font-mono text-[10.5px] text-ink-3">
            #{e.seq} · {e.actor.startsWith("reviewer:") ? `REVIEWER ${e.actor.slice(9).toUpperCase()}` : e.actor.toUpperCase()}
          </span>
        </span>
        <ChevronRight className={cn("mt-1 size-3.5 text-ink-3 transition-transform", open && "rotate-90")} aria-hidden />
      </button>
      {open && (
        <div className="mb-2 ml-[114px] rounded-lg border border-line bg-ground px-3 py-2">
          <div className="code mb-1 break-all text-ink-3">
            PREV {e.prev_hash}
            <br />
            HASH {e.entry_hash}
          </div>
          <pre className="code max-h-64 overflow-auto whitespace-pre-wrap break-words text-ink-2">{JSON.stringify(e.payload, null, 2)}</pre>
        </div>
      )}
    </li>
  );
}

function Verdict({ v }: { v: AuditVerification }) {
  const ok = v.ok;
  const Icon = ok ? ShieldCheck : ShieldX;
  return (
    <motion.div
      key={`${ok}-${v.first_bad_seq}-${v.head_hash}`}
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      role="status"
      className={cn("flex items-start gap-3 rounded-md border p-4", ok ? "border-ok bg-ok-dim" : "border-man bg-man-dim")}
    >
      <Icon className={cn("pop size-6 shrink-0", ok ? "text-ok" : "text-man")} aria-hidden />
      <div className="min-w-0">
        <div className={cn("text-[18px] font-semibold leading-tight", ok ? "text-ok" : "text-man")}>
          {ok ? "Nothing has been changed" : `Entry #${v.first_bad_seq} was changed after it was written`}
        </div>
        <p className="mt-1 text-ink-2">
          {ok
            ? `We rechecked all ${v.entries_checked} entries, and each still matches what was recorded.`
            : "What's saved no longer matches what was originally recorded."}
        </p>
        {ok ? (
          <p className="code mt-1 break-all text-ink-3">Fingerprint {v.head_hash ?? "n/a"}</p>
        ) : (
          <p className="mt-1 text-[14px] text-ink-3">Anything after this entry can't be trusted until it's looked into.</p>
        )}
      </div>
    </motion.div>
  );
}

export function AuditScreen() {
  const { caseId = "" } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["audit", caseId], queryFn: () => api.audit(caseId) });
  const [result, setResult] = useState<AuditVerification | null>(null);
  const [tampered, setTampered] = useState<number | null>(null);

  const verify = useMutation({
    mutationFn: () => api.verifyAudit(caseId),
    onSuccess: (r) => {
      setResult(r);
      if (r.ok) docSays("All good. Nothing has been changed.");
      else docSays(`Hold on! Entry #${r.first_bad_seq} was changed after it was written.`, "oops");
    },
  });
  const tamper = useMutation({
    mutationFn: () => api.tamperAudit(),
    onSuccess: (r) => {
      setTampered(r.tampered_seq);
      setResult(null);
      qc.invalidateQueries({ queryKey: ["audit", caseId] });
    },
  });
  const restore = useMutation({
    mutationFn: () => api.restoreAudit(),
    onSuccess: () => {
      setTampered(null);
      setResult(null);
      qc.invalidateQueries({ queryKey: ["audit", caseId] });
    },
  });

  const bad = result && !result.ok ? result.first_bad_seq : null;
  const err = verify.error ?? tamper.error ?? restore.error;

  return (
    <div className="flex h-full flex-col">
      <PageHeading
        eyebrow="Tamper-evident record"
        title="Investigation timeline"
        actions={
          <>
            <Button variant="primary" onClick={() => verify.mutate()} disabled={verify.isPending}>
              Verify integrity
            </Button>
            {tampered === null ? (
              <Button onClick={() => tamper.mutate()} disabled={tamper.isPending}>
                Try editing an entry
              </Button>
            ) : (
              <Button onClick={() => restore.mutate()} disabled={restore.isPending}>
                Undo the edit to entry #{tampered}
              </Button>
            )}
          </>
        }
      >
        Every step and decision, in order. Each entry is chained to the one before it by hash, so any later edit is detected.
      </PageHeading>

      <div className="flex min-h-0 flex-1 flex-col gap-4 p-6">
        {err && <ErrorState title="That action failed" error={err} className="border border-line" />}
        {tampered !== null && !result && (
          <p role="status" className="flex items-center gap-2 rounded-md border border-inc bg-inc-dim px-3 py-2 text-[14px] text-inc">
            Entry #{tampered} was just edited directly in the database, as a test. Press Verify integrity to see if it gets noticed.
          </p>
        )}
        <AnimatePresence mode="wait">{result && <Verdict v={result} />}</AnimatePresence>
        {bad !== null && q.data && !q.data.some((e) => e.seq === bad) && (
          <p className="text-[13px] text-ink-2">
            Entry #{bad} belongs to another case in the same chain, so it is not listed below. Verification covers the whole chain.
          </p>
        )}
        <div className="panel relative min-h-[260px] flex-1 overflow-y-auto p-3">
          <span aria-hidden className="pointer-events-none absolute bottom-4 left-[105px] top-4 w-px bg-gradient-to-b from-transparent via-[rgba(var(--color-glow),0.45)] to-transparent" />
          {q.isLoading && <Loading label="Loading history" />}
          {q.isError && <ErrorState title="The history could not load" error={q.error} onRetry={() => q.refetch()} />}
          {q.data?.length === 0 && <Empty title="Nothing has happened on this case yet" />}
          <ol className="relative">
            {q.data?.map((e) => (
              <Row key={e.seq} e={e} bad={bad === e.seq} afterBad={bad !== null && e.seq > bad} />
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}

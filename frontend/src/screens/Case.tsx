import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Eye,
  FileText,
  Loader2,
  Network,
  ShieldAlert,
  Upload as UploadIcon,
} from "lucide-react";
import { api } from "@/api";
import { useCase, useCaseDocuments, useFindings } from "@/api/hooks";
import type { AuditEntry, Document, DocumentSummary, Field, Finding } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/ui/states";
import { ProcBadge, RiskPlate, StatusBadge } from "@/components/StatusBadge";
import { DocOrb } from "@/components/DocOrb";
import { ConfidenceBar, CountUp, Ring } from "@/components/Metrics";
import { openDocChat } from "@/lib/assistant";
import { caseCode, caseState } from "@/lib/case";
import { charDiff, comparisonSources, findingLabels, groupSources, sortFindings } from "@/lib/findings";
import { startTour } from "@/lib/tour";
import { cn, humanize } from "@/lib/utils";

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

function lead(explanation: string): string {
  return explanation.split(/\s*(?:Other signals on this region|Why it matters:|Corroboration:|AI reasoning)/)[0].trim();
}

function viewerLink(caseId: string, f: Finding) {
  const q = new URLSearchParams({ finding: f.id });
  if (f.doc_id) q.set("doc", f.doc_id);
  if (f.page !== null) q.set("page", String(f.page));
  return `/cases/${caseId}/viewer?${q}`;
}

function Upload({ caseId, large }: { caseId: string; large: boolean }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const upload = useMutation({
    mutationFn: (files: File[]) => api.uploadDocuments(caseId, files),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", caseId] }),
  });
  const onFiles = useCallback(
    (list: FileList | null) => {
      const files = list ? Array.from(list) : [];
      if (files.length) upload.mutate(files);
    },
    [upload],
  );
  return (
    <>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          onFiles(e.dataTransfer.files);
        }}
        className={cn(
          "scanline flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 text-center transition-[border-color,background-color,box-shadow] duration-200",
          large ? "py-16" : "py-7",
          over ? "scanning border-accent bg-[rgba(var(--color-glow),0.06)] glow-cyan" : "border-line-strong bg-[color-mix(in_srgb,var(--color-panel)_70%,transparent)]",
          upload.isPending && "scanning",
        )}
      >
        <span className="flex size-11 items-center justify-center rounded-xl border border-[rgba(var(--color-glow),0.35)] bg-[rgba(var(--color-glow),0.06)] text-accent">
          {upload.isPending ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <UploadIcon className="size-5" aria-hidden />}
        </span>
        <p className="text-[15px] text-ink">
          {upload.isPending ? "Securing evidence" : "Drop evidence files here, or "}
          {!upload.isPending && (
            <button type="button" className="cursor-pointer font-medium text-accent hover:underline" onClick={() => input.current?.click()}>
              browse
            </button>
          )}
        </p>
        <p className="font-mono text-[11px] tracking-[0.1em] text-ink-3">PNG · JPG · PDF · EVERY DOCUMENT FROM ONE APPLICATION</p>
        <input
          ref={input}
          type="file"
          multiple
          className="sr-only"
          aria-label="Choose documents to upload"
          onChange={(e) => {
            onFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {upload.isError && <ErrorState title="That upload didn't work" error={upload.error} />}
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div>
      <div className="mono-label">{label}</div>
      <CountUp value={value} className={cn("mt-1 block font-mono text-[26px] font-semibold leading-none", tone ?? "text-ink")} />
    </div>
  );
}

/** How the findings split by kind, as one bar. Counts only, straight from the results. */
function SignalMix({ findings }: { findings: Finding[] }) {
  const parts = [
    { label: "Potential manipulation", n: findings.filter((f) => f.status === "POTENTIAL_MANIPULATION").length, bg: "bg-man", text: "text-man" },
    { label: "Inconsistency", n: findings.filter((f) => f.status === "INCONSISTENCY").length, bg: "bg-inc", text: "text-inc" },
    { label: "Observation", n: findings.filter((f) => f.status === "OBSERVATION").length, bg: "bg-obs", text: "text-obs" },
  ];
  const total = findings.length;
  return (
    <div className="relative mb-5 mt-7">
      <div className="mono-label mb-2">Signal breakdown</div>
      <div className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-line" aria-hidden>
        {parts.map(
          (p) =>
            p.n > 0 && (
              <div key={p.label} className={cn("grow-in h-full first:rounded-l-full last:rounded-r-full", p.bg)} style={{ width: `${(p.n / total) * 100}%` }} />
            ),
        )}
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-2">
        {parts.map((p) => (
          <li key={p.label} className="flex items-center gap-1.5">
            <span aria-hidden className={cn("size-2 rounded-full", p.bg)} />
            {p.label} <span className={cn("font-mono", p.text)}>{p.n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FindingBrief({ f, number, caseId, fieldsById, byId, index }: { f: Finding; number: string; caseId: string; fieldsById: Map<string, Field>; byId: Map<string, Document>; index: number }) {
  const serious = f.status === "POTENTIAL_MANIPULATION";
  // One source per distinct value, so a "differs" card shows the two values that actually disagree.
  const groups = groupSources(comparisonSources(f, fieldsById).filter((s) => s.value));
  const sides = groups.length >= 2 ? groups.slice(0, 2).map((g) => g.sources[0]) : [];
  const parts = sides.length === 2 ? charDiff(sides[0].value ?? "", sides[1].value ?? "") : null;
  const diffTone = serious ? "text-man" : "text-inc";
  const score = f.fused_score ?? f.confidence;
  return (
    <motion.li initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 * index }}>
      <Link
        to={viewerLink(caseId, f)}
        className={cn(
          "panel group flex h-full flex-col p-5 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5",
          serious ? "hover:glow-red" : "hover:glow-amber",
          index === 0 && (serious ? "glow-red" : "glow-amber"),
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <span className={cn("flex items-center gap-1.5 font-mono text-[10.5px] font-semibold tracking-[0.14em]", serious ? "text-man" : "text-inc")}>
            {serious ? <ShieldAlert className="size-3.5" aria-hidden /> : <AlertTriangle className="size-3.5" aria-hidden />}
            {f.severity === "high" ? "HIGH PRIORITY" : f.severity === "medium" ? "REVIEW" : "LOW PRIORITY"}
          </span>
          <span className="font-mono text-[11px] text-ink-3">{number}</span>
        </div>
        <h3 className="mt-3 text-[16px] font-semibold leading-snug text-ink">{f.title}</h3>
        {sides.length === 2 ? (
          <div className="mt-4 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-end gap-2 rounded-lg border border-line bg-ground/60 p-3">
            {sides.map((s, i) => (
              <div key={s.key} className={cn("min-w-0", i === 1 && "order-3")}>
                <div className="mono-label truncate !text-[10px]" title={byId.get(s.docId)?.filename}>
                  {humanize(byId.get(s.docId)?.doc_type ?? s.label)}
                </div>
                <div className="mt-1 truncate font-mono text-[15px] font-semibold text-ink">
                  {parts
                    ? parts[i].map((p, j) => (
                        <span key={j} className={p.changed ? cn(diffTone, "underline decoration-2 underline-offset-4") : undefined}>
                          {p.text}
                        </span>
                      ))
                    : s.value}
                </div>
              </div>
            ))}
            <span
              aria-label="does not match"
              className={cn("order-2 mb-0.5 rounded border bg-panel px-1 font-mono text-[12px]", diffTone, serious ? "border-man/50" : "border-inc/50")}
            >
              ≠
            </span>
          </div>
        ) : (
          <p className="mt-2 line-clamp-2 text-[13.5px] leading-relaxed text-ink-2">{lead(f.explanation)}</p>
        )}
        <div className="mt-auto pt-4">
          <div className="mb-1.5 flex items-center justify-between font-mono text-[11px] tracking-[0.08em]">
            <span className="text-ink-3">CONFIDENCE</span>
            <span className="text-ink">{Math.round(score * 100)}%</span>
          </div>
          <ConfidenceBar value={score} tone={serious ? "bg-man" : "bg-inc"} />
          <div className="mt-4 flex items-center justify-between">
            <StatusBadge status={f.status} />
            <span className="flex items-center gap-1 font-mono text-[11px] tracking-[0.14em] text-ink-2 group-hover:text-accent">
              VIEW EVIDENCE <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-1" aria-hidden />
            </span>
          </div>
        </div>
      </Link>
    </motion.li>
  );
}

function TimelinePreview({ caseId }: { caseId: string }) {
  const q = useQuery({ queryKey: ["audit", caseId], queryFn: () => api.audit(caseId) });
  const items = (q.data ?? []).filter((e: AuditEntry) => !e.action.startsWith("finding.recorded")).slice(-7);
  return (
    <div className="panel flex flex-col p-5">
      <div className="flex items-center justify-between">
        <div className="mono-label">Investigation timeline</div>
        <Link to={`/cases/${caseId}/audit`} className="group flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink">
          Full timeline <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </Link>
      </div>
      <ol className="relative mt-4 space-y-3 border-l border-line pl-4">
        {items.map((e) => {
          const alert = e.action.includes("review") || e.action.includes("tamper");
          return (
            <li key={e.seq} className="relative">
              <span className={cn("absolute -left-[21px] top-1.5 size-2 rounded-full ring-4 ring-panel", alert ? "bg-inc" : "bg-accent")} />
              <div className="font-mono text-[11px] text-ink-3">{new Date(e.ts).toLocaleTimeString(undefined, { hour12: false })}</div>
              <div className="text-[13px] text-ink">{humanize(e.action.replace(/^stage\./, "").replace(/^case\./, "case ").replace("finding.review", "review decision"))}</div>
            </li>
          );
        })}
        {items.length === 0 && <li className="text-[13px] text-ink-3">Nothing recorded yet.</li>}
      </ol>
    </div>
  );
}

export function CaseScreen() {
  const { caseId = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const c = useCase(caseId);
  const findings = useFindings(caseId);
  const { fieldsById, byId } = useCaseDocuments(caseId);
  const ordered = useMemo(() => sortFindings(findings.data ?? []), [findings.data]);
  const labels = useMemo(() => findingLabels(findings.data ?? []), [findings.data]);
  const attention = ordered.filter((f) => f.status !== "OBSERVATION");
  const decided = attention.filter((f) => f.review.decision !== "pending").length;
  const conflicts = attention.filter((f) => f.discrepancy_type).length;
  const run = useMutation({
    mutationFn: () => api.runCase(caseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["case", caseId] });
      nav(`/cases/${caseId}/pipeline`);
    },
  });

  if (c.isLoading) return <Loading label="Opening investigation" className="h-full" />;
  if (c.isError) return <ErrorState title="This investigation could not load" error={c.error} onRetry={() => c.refetch()} />;
  const { case: cs, documents } = c.data!;
  const done = cs.status === "complete";
  const running = cs.status === "running";
  const nothingRead = done && documents.length > 0 && documents.every((d) => d.page_count === 0);
  const state = caseState(cs, attention.length - decided);
  const strongest = attention[0];

  if (!done) {
    return (
      <div className="mx-auto flex max-w-[900px] flex-col gap-6 px-6 pb-16 pt-8">
        <div>
          <div className="mono-label text-accent">{caseCode(caseId)} · {state.label}</div>
          <h2 className="mt-2 text-[28px] font-semibold tracking-tight">{documents.length ? "Evidence ready for analysis" : "Add evidence to begin"}</h2>
          <p className="mt-1.5 text-ink-2">Submit every document from one application together. The relationships between them are where most problems show.</p>
        </div>
        {run.isError && <ErrorState title="The analysis didn't start" error={run.error} />}
        {!running && <Upload caseId={caseId} large={documents.length === 0} />}
        {documents.length > 0 && <EvidenceList documents={documents} running={running} attention={attention} />}
        <div>
          {running ? (
            <Button asChild variant="primary" size="lg">
              <Link to={`/cases/${caseId}/pipeline`}>
                <Loader2 className="animate-spin" aria-hidden /> View analysis
              </Link>
            </Button>
          ) : (
            <Button variant="primary" size="lg" disabled={documents.length === 0 || run.isPending} onClick={() => run.mutate()}>
              Run forensic analysis <ArrowRight aria-hidden />
            </Button>
          )}
        </div>
      </div>
    );
  }

  const ringTone = attention.length === 0 ? "var(--color-ok)" : decided === attention.length ? "var(--color-ok)" : "var(--color-accent)";

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-6 px-6 pb-16 pt-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <section data-tour="status" className="panel relative flex flex-col overflow-hidden p-6">
          <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-[radial-gradient(circle,rgba(var(--color-glow),0.12),transparent_70%)]" />
          <div className="relative flex flex-wrap items-center gap-8">
            <div className="min-w-0 flex-1">
              <div className="mono-label">Case status</div>
              <div className="mt-2 text-[30px] font-semibold uppercase leading-none tracking-tight text-ink">
                {nothingRead ? "No usable evidence" : attention.length === 0 ? "Nothing flagged" : decided === attention.length ? "Review complete" : "Under review"}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <RiskPlate risk={cs.risk_level} large />
                <span className="font-mono text-[11px] tracking-[0.12em] text-ink-3">REQUIRES HUMAN REVIEW</span>
              </div>
              <div className="mt-7 grid grid-cols-2 gap-6 sm:grid-cols-4">
                <Stat label="Evidence" value={documents.length} />
                <Stat label="Findings" value={attention.length} tone={attention.length ? "text-inc" : "text-ok"} />
                <Stat label="Conflicts" value={conflicts} tone={conflicts ? "text-man" : undefined} />
                <Stat label="Minor" value={ordered.length - attention.length} tone="text-ink-3" />
              </div>
            </div>
            <div className="flex flex-col items-center">
              <Ring fraction={attention.length ? decided / attention.length : 1} tone={ringTone}>
                <CountUp value={attention.length ? Math.round((decided / attention.length) * 100) : 100} className="font-mono text-[30px] font-semibold text-ink" />
                <span className="font-mono text-[10px] tracking-[0.16em] text-ink-3">% REVIEWED</span>
              </Ring>
              <div className="mt-2 font-mono text-[11px] text-ink-3">
                {decided}/{attention.length} DECISIONS
              </div>
            </div>
          </div>
          {nothingRead && <p className="relative mt-5 text-[14px] text-ink-2">None of these files could be read, so nothing was analyzed. The evidence list explains why.</p>}
          {ordered.length > 0 && <SignalMix findings={ordered} />}
          <p className="relative mt-auto border-t border-line pt-4 text-[12.5px] text-ink-3">
            The risk level sets review priority only. It isn't a decision about the applicant.{" "}
            <button type="button" className="cursor-pointer text-accent hover:underline" onClick={() => startTour("case")}>
              Take the tour
            </button>
          </p>
        </section>

        <section data-tour="doc-panel" className="panel glow-cyan relative flex flex-col overflow-hidden p-5">
          <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-[radial-gradient(ellipse_at_top,rgba(var(--color-glow),0.16),transparent_70%)]" />
          <div className="relative flex items-center gap-3">
            <DocOrb state={attention.length ? "alert" : "done"} size={36} />
            <div>
              <div className="flex items-center gap-2 font-mono text-[12px] font-semibold tracking-[0.2em] text-ink">
                DOC <span className="status-dot" />
              </div>
              <div className="mono-label !text-[10px]">Investigation assistant</div>
            </div>
          </div>
          <p className="relative mt-5 text-[15px] text-ink">
            {attention.length ? `I found ${plural(attention.length, "thing")} worth reviewing.` : "Nothing in this case needs attention."}
          </p>
          <ul className="relative mt-3 space-y-2">
            {attention.slice(0, 3).map((f) => (
              <li key={f.id} className="flex items-start gap-2 text-[13.5px] text-ink-2">
                {f.status === "POTENTIAL_MANIPULATION" ? (
                  <ShieldAlert className="mt-0.5 size-4 shrink-0 text-man" aria-hidden />
                ) : (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-inc" aria-hidden />
                )}
                <span className="line-clamp-1">{f.title}</span>
              </li>
            ))}
            {attention.length === 0 && (
              <li className="flex items-start gap-2 text-[13.5px] text-ink-2">
                <Eye className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden /> A clean result doesn't prove the documents are genuine.
              </li>
            )}
          </ul>
          {strongest && (
            <blockquote className="relative mt-4 border-l-2 border-accent pl-3 text-[13.5px] italic text-ink-2">
              "The strongest signal here is {labels.get(strongest.id)}, {strongest.title.toLowerCase()}, at {Math.round((strongest.fused_score ?? strongest.confidence) * 100)}% confidence."
            </blockquote>
          )}
          <button
            type="button"
            onClick={openDocChat}
            className="group relative mt-auto flex cursor-pointer items-center justify-between rounded-lg border border-[rgba(var(--color-glow),0.35)] px-3 py-2.5 pt-2.5 font-mono text-[12px] font-semibold tracking-[0.16em] text-accent transition-colors hover:bg-[rgba(var(--color-glow),0.08)]"
            style={{ marginTop: "1.25rem" }}
          >
            ASK DOC
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden />
          </button>
        </section>
      </div>

      {attention.length > 0 && (
        <section data-tour="top-findings">
          <div className="flex items-end justify-between">
            <div className="mono-label">Priority findings</div>
            <Link to={`/cases/${caseId}/viewer`} className="group flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink">
              All {attention.length} findings <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          </div>
          <ul className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {attention.slice(0, 3).map((f, i) => (
              <FindingBrief key={f.id} f={f} number={labels.get(f.id) ?? ""} caseId={caseId} fieldsById={fieldsById} byId={byId} index={i} />
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="flex flex-col gap-6">
          <EvidenceList documents={documents} running={false} attention={attention} />
          {conflicts > 0 && (
            <Link to={`/cases/${caseId}/graph`} className="panel group relative flex items-center gap-4 overflow-hidden p-5 transition-[box-shadow] hover:glow-cyan">
              <span className="flex size-11 items-center justify-center rounded-xl border border-[rgba(var(--color-glow),0.35)] bg-[rgba(var(--color-glow),0.06)] text-accent">
                <Network className="size-5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-ink">Evidence graph</span>
                <span className="block text-[13px] text-ink-3">See how {plural(conflicts, "conflict")} connect the documents.</span>
              </span>
              <ArrowRight className="size-5 text-ink-3 transition-transform group-hover:translate-x-1 group-hover:text-accent" aria-hidden />
            </Link>
          )}
        </div>
        <TimelinePreview caseId={caseId} />
      </div>

      <details className="text-[13.5px]">
        <summary>Add more evidence or run the analysis again</summary>
        <div className="mt-3 flex flex-col gap-3">
          <Upload caseId={caseId} large={false} />
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={run.isPending} onClick={() => run.mutate()}>
              Run again
            </Button>
            <Link className="link" to={`/cases/${caseId}/pipeline`}>
              See the last analysis
            </Link>
          </div>
        </div>
      </details>
    </div>
  );
}

function EvidenceList({ documents, running, attention }: { documents: DocumentSummary[]; running: boolean; attention: Finding[] }) {
  return (
    <section className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <div className="mono-label">Evidence</div>
        <span className="font-mono text-[11px] text-ink-3">{documents.length} FILES</span>
      </div>
      <ul>
        {documents.map((d, i) => {
          const toReview = attention.filter((f) => f.doc_id === d.id || f.evidence.some((e) => e.doc_id === d.id)).length;
          return (
            <motion.li
              key={d.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.03 * i }}
              className="flex items-center gap-3 border-b border-line px-5 py-3 last:border-b-0"
            >
              <FileText className="size-4 shrink-0 text-ink-3" aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[14px] text-ink">{d.doc_type === "unknown" ? d.filename : humanize(d.doc_type)}</div>
                <div className="truncate font-mono text-[11px] text-ink-3">
                  {d.filename} · {d.format.replace("_", " ").toUpperCase()}
                </div>
                {d.status_message && <div className="mt-0.5 text-[12.5px] text-ink-2">{d.status_message}</div>}
              </div>
              {toReview > 0 && <span className="font-mono text-[11px] text-inc">{toReview} TO REVIEW</span>}
              {d.status === "processing" && !running ? <span className="text-[13px] text-ink-3">Ready</span> : <ProcBadge status={d.status} />}
            </motion.li>
          );
        })}
      </ul>
    </section>
  );
}

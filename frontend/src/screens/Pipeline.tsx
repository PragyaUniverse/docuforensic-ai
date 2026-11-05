import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Check, Circle, Loader2, Play, RotateCw, WifiOff, X } from "lucide-react";
import { api } from "@/api";
import { useCase } from "@/api/hooks";
import type { Case, PipelineStage, ProgressEvent, StageProgress } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/ui/states";
import { PageHeading } from "@/components/Shell";
import { ProcBadge, RiskPlate } from "@/components/StatusBadge";
import { cn, fmtMs } from "@/lib/utils";

const STAGES: { id: PipelineStage; label: string; detail: string }[] = [
  { id: "submission", label: "Document submission", detail: "Hash, sniff real type, render pages" },
  { id: "classification", label: "Classification", detail: "Read each page (OCR), then identify the document type" },
  { id: "ocr_extraction", label: "OCR & extraction", detail: "Turn words, with confidence and boxes, into fields and tables" },
  { id: "structure", label: "Structural understanding", detail: "Sections, missing and duplicated fields" },
  { id: "visual_forensics", label: "Visual forensics", detail: "Pixel and PDF-structure detectors, region fusion" },
  { id: "contextual_verification", label: "Contextual verification", detail: "Arithmetic, dates and checksums within a document" },
  { id: "cross_document", label: "Cross-document correlation", detail: "Entity matching and reconciliation" },
  { id: "anomaly_investigation", label: "Anomaly investigation", detail: "Explanations and benign alternatives" },
  { id: "evidence", label: "Evidence generation", detail: "Regions, crops, evidence graph" },
  { id: "dossier", label: "Investigation dossier", detail: "Structured report and audit head" },
];

function StageIcon({ state }: { state: string }) {
  const cls = "size-[18px]";
  if (state === "running") return <Loader2 className={cn(cls, "animate-spin text-ink")} aria-hidden />;
  if (state === "done") return <Check className={cn(cls, "text-ok")} aria-hidden />;
  if (state === "degraded") return <AlertTriangle className={cn(cls, "text-inc")} aria-hidden />;
  if (state === "failed") return <X className={cn(cls, "text-man")} aria-hidden />;
  return <Circle className={cn(cls, "text-line-strong")} aria-hidden />;
}

const STATE_LABEL: Record<string, string> = {
  pending: "Waiting",
  running: "Running",
  done: "Done",
  degraded: "Degraded",
  failed: "Failed",
};

export function PipelineScreen() {
  const { caseId = "" } = useParams();
  const qc = useQueryClient();
  const c = useCase(caseId);
  const [live, setLive] = useState<ProgressEvent | null>(null);
  const [streamLost, setStreamLost] = useState(false);
  const status = live?.status ?? c.data?.case.status;
  const running = status === "running";

  useEffect(() => {
    if (!running) return;
    setStreamLost(false);
    const stop = api.subscribeProgress(caseId, {
      onProgress: (e) => {
        setLive(e);
        qc.invalidateQueries({ queryKey: ["case", caseId] });
      },
      onDone: () => {
        // Every derived view is stale once a run ends.
        qc.invalidateQueries({ predicate: (q) => q.queryKey.includes(caseId) });
      },
      onConnectionLost: () => setStreamLost(true),
    });
    return stop;
  }, [caseId, running, qc]);

  // When the stream drops, keep the screen truthful by polling instead.
  useEffect(() => {
    if (!streamLost || !running) return;
    const t = window.setInterval(() => {
      api
        .getCase(caseId)
        .then((d) => {
          setLive({ case_id: caseId, status: d.case.status, stages: d.case.progress });
          qc.setQueryData(["case", caseId], d);
        })
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(t);
  }, [streamLost, running, caseId, qc]);

  const run = useMutation({
    mutationFn: () => api.runCase(caseId),
    onSuccess: () => {
      setLive(null);
      qc.setQueryData<{ case: Case } | undefined>(["case", caseId], (old) =>
        old ? { ...old, case: { ...old.case, status: "running", progress: [] } } : old,
      );
      qc.invalidateQueries({ queryKey: ["case", caseId] });
    },
  });

  const stages = useMemo(() => {
    const src: StageProgress[] = live?.stages ?? c.data?.case.progress ?? [];
    const m = new Map(src.map((s) => [s.stage, s]));
    return STAGES.map((s) => ({ ...s, p: m.get(s.id) }));
  }, [live, c.data]);

  if (c.isLoading) return <Loading label="Loading pipeline" className="h-full" />;
  if (c.isError) return <ErrorState title="Pipeline state could not load" error={c.error} onRetry={() => c.refetch()} />;
  const { case: cs, documents } = c.data!;
  const maxMs = Math.max(1, ...stages.map((s) => s.p?.duration_ms ?? 0));
  const totalMs = stages.reduce((a, s) => a + (s.p?.duration_ms ?? 0), 0);
  const finished = status === "complete" || status === "failed";
  const hasDegraded = stages.some((s) => s.p?.state === "degraded" || s.p?.state === "failed");

  return (
    <div className="flex flex-col">
      <PageHeading
        eyebrow="Pipeline"
        title={running ? "Investigation running" : status === "complete" ? "Investigation complete" : status === "failed" ? "Investigation failed" : "Ready to run"}
        actions={
          <>
            {status === "complete" && (
              <Button asChild variant="primary">
                <Link to={`/cases/${caseId}/viewer`}>
                  Review findings <ArrowRight aria-hidden />
                </Link>
              </Button>
            )}
            {!running && (
              <Button variant={status === "complete" ? "secondary" : "primary"} disabled={documents.length === 0 || run.isPending} onClick={() => run.mutate()}>
                {finished ? <RotateCw aria-hidden /> : <Play aria-hidden />}
                {finished ? "Run again" : "Run investigation"}
              </Button>
            )}
          </>
        }
      />
      {run.isError && <ErrorState title="The investigation did not start" error={run.error} />}
      {streamLost && running && (
        <div role="status" className="flex items-center gap-2 border-b border-line bg-inc-dim px-6 py-2 text-[13px] text-inc">
          <WifiOff className="size-3.5" aria-hidden /> Live stream lost. Polling the service for status instead.
        </div>
      )}

      <div className="grid gap-6 p-6 xl:grid-cols-[minmax(0,3fr)_minmax(320px,2fr)]">
        <ol aria-label="Pipeline stages" className="border-x border-t border-line bg-panel">
          {stages.map((s, i) => {
            const state = s.p?.state ?? "pending";
            const active = state === "running";
            return (
              <motion.li
                key={s.id}
                layout="position"
                className={cn(
                  "grid grid-cols-[28px_18px_minmax(0,1fr)_auto] items-start gap-3 border-b border-line px-4 py-2.5 transition-colors",
                  active && "bg-raised",
                )}
              >
                <span className="pt-px font-mono text-xs text-ink-3">{String(i + 1).padStart(2, "0")}</span>
                <span className="pt-px">
                  <StageIcon state={state} />
                </span>
                <div className="min-w-0">
                  <div className={cn("font-medium", state === "pending" ? "text-ink-3" : "text-ink")}>{s.label}</div>
                  <div className="text-[13px] text-ink-3">{s.detail}</div>
                  {s.p?.message && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className={cn("mt-1 text-[13px]", state === "degraded" || state === "failed" ? "text-inc" : "text-ink-2")}
                    >
                      {s.p.message}
                    </motion.div>
                  )}
                  {s.p?.duration_ms !== null && s.p?.duration_ms !== undefined && (
                    <div aria-hidden className="mt-1.5 h-[3px] bg-line">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${(s.p.duration_ms / maxMs) * 100}%` }}
                        transition={{ duration: 0.3 }}
                        className={cn("h-full", state === "degraded" ? "bg-inc" : state === "failed" ? "bg-man" : "bg-ink-2")}
                      />
                    </div>
                  )}
                </div>
                <div className="text-right">
                  <div className={cn("font-mono text-[11px]", state === "degraded" ? "text-inc" : state === "failed" ? "text-man" : "text-ink-3")}>
                    {STATE_LABEL[state] ?? state}
                  </div>
                  <div className="font-mono text-xs text-ink-2">{fmtMs(s.p?.duration_ms)}</div>
                </div>
              </motion.li>
            );
          })}
        </ol>

        <div className="flex flex-col gap-6">
          <section className="border border-line bg-panel p-4">
            <h2 className="eyebrow mb-2">Result</h2>
            {status === "complete" ? (
              <div className="flex flex-col items-start gap-2">
                <RiskPlate risk={cs.risk_level} large />
                <p className="text-ink-2">
                  This is a triage level, not a decision. Every finding stays open until an examiner confirms, dismisses or escalates it.
                </p>
                {hasDegraded && <p className="text-[13px] text-inc">At least one stage ran degraded. See the messages beside each stage.</p>}
              </div>
            ) : status === "failed" ? (
              <p className="text-ink-2">The run stopped. Stage messages say why, and no results were invented for the stages that did not finish.</p>
            ) : running ? (
              <p className="text-ink-2">No conclusions are shown until the run finishes.</p>
            ) : (
              <p className="text-ink-2">Nothing has been assessed yet.</p>
            )}
            {totalMs > 0 && <p className="mt-3 font-mono text-xs text-ink-3">Elapsed in stages: {fmtMs(totalMs)}</p>}
          </section>

          <section className="border border-line bg-panel">
            <h2 className="eyebrow border-b border-line px-4 py-2">Per-document status</h2>
            <ul>
              {documents.map((d) => (
                <li key={d.id} className="border-b border-line px-4 py-2 last:border-b-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-xs">{d.filename}</span>
                    <ProcBadge status={d.status} />
                  </div>
                  {d.status_message && <p className="mt-1 text-[13px] text-ink-3">{d.status_message}</p>}
                </li>
              ))}
              {documents.length === 0 && <li className="px-4 py-3 text-ink-3">No documents in this case.</li>}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}

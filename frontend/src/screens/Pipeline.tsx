import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Circle, Loader2, WifiOff, X } from "lucide-react";
import { api } from "@/api";
import { useCase } from "@/api/hooks";
import type { Case, PipelineStage, ProgressEvent, StageProgress } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/ui/states";
import { Mascot } from "@/components/Mascot";
import { CountUp, Ring } from "@/components/Metrics";
import { ProcBadge } from "@/components/StatusBadge";
import { caseCode } from "@/lib/case";
import { cn, fmtMs } from "@/lib/utils";

const STAGES: { id: PipelineStage; label: string }[] = [
  { id: "submission", label: "Securing evidence" },
  { id: "classification", label: "Reading evidence" },
  { id: "ocr_extraction", label: "Extracting entities" },
  { id: "structure", label: "Mapping document structure" },
  { id: "visual_forensics", label: "Running forensic checks" },
  { id: "contextual_verification", label: "Verifying internal consistency" },
  { id: "cross_document", label: "Comparing documents" },
  { id: "anomaly_investigation", label: "Detecting anomalies" },
  { id: "evidence", label: "Building evidence graph" },
  { id: "dossier", label: "Compiling report" },
];

function StageIcon({ state }: { state: string }) {
  const cls = "size-[18px]";
  if (state === "running") return <Loader2 className={cn(cls, "animate-spin text-accent drop-shadow-[0_0_6px_rgba(var(--color-glow),0.9)]")} aria-hidden />;
  if (state === "done") return <Check className={cn(cls, "pop text-ok")} aria-hidden />;
  if (state === "degraded") return <AlertTriangle className={cn(cls, "pop text-inc")} aria-hidden />;
  if (state === "failed") return <X className={cn(cls, "text-man")} aria-hidden />;
  return <Circle className={cn(cls, "text-line-strong")} aria-hidden />;
}

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

  if (c.isLoading) return <Loading label="Loading progress" className="h-full" />;
  if (c.isError) return <ErrorState title="Progress could not load" error={c.error} onRetry={() => c.refetch()} />;
  const { documents } = c.data!;
  const finished = status === "complete" || status === "failed";
  const stepsDone = stages.filter((s) => s.p?.state === "done" || s.p?.state === "degraded").length;
  const problems = documents.filter((d) => d.status === "unsupported" || d.status === "failed" || d.status === "degraded");

  const percent = Math.round((stepsDone / stages.length) * 100);
  const current = stages.find((x) => x.p?.state === "running");

  return (
    <div className="mx-auto flex max-w-[980px] flex-col gap-6 px-6 pb-16 pt-8">
      {run.isError && <ErrorState title="The analysis didn't start" error={run.error} />}
      {streamLost && running && (
        <p role="status" className="flex items-center gap-2 rounded-lg border border-inc/30 bg-inc-dim px-3 py-2 text-[13.5px] text-inc">
          <WifiOff className="size-4" aria-hidden /> Live updates dropped. Checking progress every few seconds instead.
        </p>
      )}

      <section className={cn("panel relative overflow-hidden p-8", running && "glow-cyan")}>
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_30%_0%,rgba(var(--color-glow),0.12),transparent_60%)]" />
        <div className="relative grid items-center gap-10 md:grid-cols-[auto_minmax(0,1fr)]">
          <div className="flex flex-col items-center gap-4">
            <div className={cn("scanline relative flex h-[168px] w-[132px] flex-col gap-2 rounded-lg border border-[rgba(var(--color-glow),0.35)] bg-ground p-4", running && "scanning")}>
              {[70, 92, 55, 88, 64, 80, 46].map((w, i) => (
                <span key={i} className="h-1.5 rounded-full bg-line-strong" style={{ width: `${w}%`, opacity: stepsDone > i ? 0.9 : 0.35 }} />
              ))}
              <span className="mt-auto flex items-center justify-between font-mono text-[9px] tracking-[0.14em] text-ink-3">
                <span>EVIDENCE</span>
                <span>{documents.length}</span>
              </span>
            </div>
            <span className="font-mono text-[11px] tracking-[0.14em] text-ink-3">CASE {caseCode(caseId)}</span>
          </div>
          <div>
            <div className="flex items-center gap-3">
              <Mascot mood={running ? "thinking" : status === "complete" ? "happy" : status === "failed" ? "oops" : "idle"} size={64} />
              <div className="mono-label text-accent">{running ? "Doc is analyzing" : status === "complete" ? "Analysis complete" : status === "failed" ? "Analysis stopped" : "Ready"}</div>
            </div>
            <h1 className="mt-3 text-[30px] font-semibold uppercase tracking-tight text-ink">
              {running ? "Analyzing investigation" : status === "complete" ? "Investigation ready" : status === "failed" ? "Analysis stopped" : "Not analyzed yet"}
            </h1>
            <p className="mt-1.5 text-[14.5px] text-ink-2" aria-live="polite">
              {running ? `${current?.label ?? "Starting"}…` : status === "complete" ? "Every step finished. Review the findings next." : status === "failed" ? "The step messages below say why. Nothing was made up for steps that didn't run." : "Add evidence, then run the analysis."}
            </p>
            <div className="mt-6 flex items-center gap-6">
              <Ring fraction={stepsDone / stages.length} size={104} tone={status === "complete" ? "var(--color-ok)" : "var(--color-accent)"}>
                <span className="font-mono text-[22px] font-semibold text-ink">
                  <CountUp value={percent} />%
                </span>
              </Ring>
              <div className="flex flex-col gap-2">
                {status === "complete" && (
                  <>
                    <Button asChild variant="primary">
                      <Link to={`/cases/${caseId}`}>Open investigation</Link>
                    </Button>
                    <Link to={`/cases/${caseId}/viewer`} className="text-[13.5px] text-ink-2 hover:text-ink">
                      Go straight to findings →
                    </Link>
                  </>
                )}
                {!running && status !== "complete" && (
                  <Button variant="primary" disabled={documents.length === 0 || run.isPending} onClick={() => run.mutate()}>
                    {finished ? "Run again" : "Run forensic analysis"}
                  </Button>
                )}
                {running && <span className="font-mono text-[12px] text-ink-3">{stepsDone} OF {stages.length} STEPS</span>}
              </div>
            </div>
          </div>
        </div>
      </section>

      <ol aria-label="Steps" className="panel divide-y divide-line">
        {stages.map((s, i) => {
          const state = s.p?.state ?? "pending";
          const warn = state === "degraded" || state === "failed";
          return (
            <li key={s.id} className={cn("flex items-start gap-4 px-5 py-3 transition-colors duration-300", state === "running" && "bg-[rgba(var(--color-glow),0.06)]")}>
              <span className="w-6 pt-0.5 font-mono text-[11px] text-ink-3">{String(i + 1).padStart(2, "0")}</span>
              <span className="pt-0.5">
                <StageIcon state={state} />
              </span>
              <div className="min-w-0 flex-1">
                <div className={cn("text-[14px] transition-colors duration-300", state === "pending" ? "text-ink-3" : "text-ink", state === "running" && "font-medium")}>{s.label}</div>
                {s.p?.message && <div className={cn("fade-in mt-0.5 text-[13px]", warn ? "text-inc" : "text-ink-3")}>{s.p.message}</div>}
              </div>
              {!!s.p?.duration_ms && <span className="fade-in shrink-0 font-mono text-[11.5px] text-ink-3">{fmtMs(s.p.duration_ms)}</span>}
            </li>
          );
        })}
      </ol>

      {problems.length > 0 && (
        <section className="panel">
          <div className="mono-label border-b border-line px-5 py-3">Evidence with problems</div>
          <ul className="divide-y divide-line">
            {problems.map((d) => (
              <li key={d.id} className="px-5 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-[13px] text-ink">{d.filename}</span>
                  <ProcBadge status={d.status} />
                </div>
                {d.status_message && <p className="mt-0.5 text-[13px] text-ink-2">{d.status_message}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {status === "complete" && (
        <div>
          <Button disabled={documents.length === 0 || run.isPending} onClick={() => run.mutate()}>
            Run again
          </Button>
        </div>
      )}
    </div>
  );
}

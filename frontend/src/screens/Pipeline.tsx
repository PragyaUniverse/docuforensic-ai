import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Circle, Loader2, WifiOff, X } from "lucide-react";
import { api } from "@/api";
import { useCase } from "@/api/hooks";
import type { Case, PipelineStage, ProgressEvent, StageProgress } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/ui/states";
import { PageHeading } from "@/components/Shell";
import { Mascot } from "@/components/Mascot";
import { ProcBadge } from "@/components/StatusBadge";
import { openDocChat } from "@/lib/assistant";
import { cn, fmtMs } from "@/lib/utils";

const STAGES: { id: PipelineStage; label: string }[] = [
  { id: "submission", label: "Receiving the documents" },
  { id: "classification", label: "Reading each page and working out what it is" },
  { id: "ocr_extraction", label: "Pulling out fields and tables" },
  { id: "structure", label: "Understanding the layout" },
  { id: "visual_forensics", label: "Looking for signs of editing" },
  { id: "contextual_verification", label: "Checking each document adds up" },
  { id: "cross_document", label: "Comparing the documents with each other" },
  { id: "anomaly_investigation", label: "Writing up what was found" },
  { id: "evidence", label: "Collecting the evidence" },
  { id: "dossier", label: "Preparing the report" },
];

function StageIcon({ state }: { state: string }) {
  const cls = "size-[18px]";
  if (state === "running") return <Loader2 className={cn(cls, "animate-spin text-accent")} aria-hidden />;
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

  return (
    <div className="mx-auto flex max-w-[760px] flex-col gap-4 pb-10">
      <PageHeading
        title={running ? "on it… 🔎" : status === "complete" ? "all done 🎉" : status === "failed" ? "the check stopped 😬" : "not checked yet"}
      >
        {running ? "This usually takes under a minute." : undefined}
      </PageHeading>
      {run.isError && <ErrorState title="The check didn't start" error={run.error} />}
      {streamLost && running && (
        <p role="status" className="mx-6 flex items-center gap-2 rounded-md bg-inc-dim px-3 py-2 text-[14px] text-inc">
          <WifiOff className="size-4" aria-hidden /> Live updates dropped, so we're checking for progress every few seconds.
        </p>
      )}

      <div className="flex flex-col gap-5 px-6">
        {status === "complete" && (
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild variant="primary">
              <Link to={`/cases/${caseId}/viewer`}>Review findings</Link>
            </Button>
            <Button asChild>
              <Link to={`/cases/${caseId}`}>See the summary</Link>
            </Button>
          </div>
        )}
        {status === "failed" && <p className="text-ink-2">The messages below say why. Nothing was made up for the steps that didn't run.</p>}

        <div className="flex items-center gap-4 card p-4">
          <button type="button" onClick={openDocChat} title="Ask Doc a question" aria-label="Ask Doc a question" className="shrink-0 cursor-pointer">
            <Mascot mood={running ? "thinking" : status === "complete" ? "happy" : status === "failed" ? "oops" : "idle"} size={84} />
          </button>
          <div className="min-w-0 flex-1" aria-live="polite">
            <p className="font-medium">
              {running
                ? `${stages.find((x) => x.p?.state === "running")?.label ?? "Getting started"}…`
                : status === "complete"
                  ? "Finished! Have a look at what I found."
                  : status === "failed"
                    ? "Something stopped the check."
                    : "Ready when you are."}
            </p>
            {running && <p className="text-[14px] text-ink-3">{stepsDone} of {stages.length} steps done</p>}
          </div>
        </div>

        {running && (
          <div>
            <div className="h-3 overflow-hidden rounded-full border-2 border-[var(--color-edge)] bg-panel" aria-hidden>
              <motion.div
                className="h-full rounded-full bg-[linear-gradient(90deg,var(--color-accent),var(--color-pink))]"
                initial={false}
                animate={{ width: `${(stepsDone / stages.length) * 100}%` }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              />
            </div>
          </div>
        )}

        <ol aria-label="Steps" className="card">
          {stages.map((s) => {
            const state = s.p?.state ?? "pending";
            const warn = state === "degraded" || state === "failed";
            return (
              <li key={s.id} className={cn("flex items-start gap-3 border-b border-line px-4 py-2.5 transition-colors duration-200 last:border-b-0", state === "running" && "bg-lime/35")}>
                <span className="pt-0.5">
                  <StageIcon state={state} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className={cn("transition-colors duration-200", state === "pending" ? "text-ink-3" : "text-ink")}>{s.label}</div>
                  {s.p?.message && <div className={cn("fade-in mt-0.5 text-[14px]", warn ? "text-inc" : "text-ink-3")}>{s.p.message}</div>}
                </div>
                {!!s.p?.duration_ms && <span className="fade-in shrink-0 text-[13px] text-ink-3">{fmtMs(s.p.duration_ms)}</span>}
              </li>
            );
          })}
        </ol>

        {problems.length > 0 && (
          <section>
            <h2 className="mb-2 text-[17px] font-semibold">Files with problems</h2>
            <ul className="card">
              {problems.map((d) => (
                <li key={d.id} className="border-b border-line px-4 py-2.5 last:border-b-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium">{d.filename}</span>
                    <ProcBadge status={d.status} />
                  </div>
                  {d.status_message && <p className="mt-0.5 text-[14px] text-ink-2">{d.status_message}</p>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {!running && (
          <div>
            <Button variant={status === "complete" ? "secondary" : "primary"} disabled={documents.length === 0 || run.isPending} onClick={() => run.mutate()}>
              {finished ? "Check again" : "Check these documents"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

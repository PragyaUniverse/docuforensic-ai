import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "@/api";
import { useCase, useFindings } from "@/api/hooks";
import type { DocumentSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/ui/states";
import { HumanReviewPlate, ProcBadge, RiskPlate } from "@/components/StatusBadge";
import { PageHeading } from "@/components/Shell";
import { cn, humanize } from "@/lib/utils";

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

function DocRow({ d, caseRunning, toReview }: { d: DocumentSummary; caseRunning: boolean; toReview: number }) {
  const type = d.doc_type === "unknown" ? null : humanize(d.doc_type);
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-0.5 border-b border-line px-4 py-3 last:border-b-0">
      <div className="min-w-[220px] flex-1">
        <div className="font-medium">{type ?? d.filename}</div>
        {type && <div className="break-all text-[13px] text-ink-3">{d.filename}</div>}
        {d.status_message && <div className="mt-0.5 text-[14px] text-ink-2">{d.status_message}</div>}
      </div>
      {toReview > 0 && <div className="text-[14px] text-ink-2">{toReview} to review</div>}
      {d.status === "processing" && !caseRunning ? (
        <span className="text-[14px] text-ink-3">Ready to check</span>
      ) : (
        <ProcBadge status={d.status} />
      )}
    </li>
  );
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
          "flex flex-col items-center justify-center gap-2 rounded-md border border-dashed px-6 text-center",
          large ? "py-12" : "py-5",
          over ? "border-accent bg-obs-dim" : "border-line-strong bg-panel",
        )}
      >
        {upload.isPending ? (
          <p className="flex items-center gap-2 text-ink-2">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Uploading
          </p>
        ) : (
          <>
            <p className="text-ink">
              Drag files here, or{" "}
              <button type="button" className="link cursor-pointer" onClick={() => input.current?.click()}>
                choose files
              </button>
            </p>
            <p className="text-[13px] text-ink-3">PNG, JPG or PDF. Add every document from the application together.</p>
          </>
        )}
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

export function CaseScreen() {
  const { caseId = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const c = useCase(caseId);
  const findings = useFindings(caseId);
  const counts = useMemo(() => {
    const out = { POTENTIAL_MANIPULATION: 0, INCONSISTENCY: 0, OBSERVATION: 0 };
    (findings.data ?? []).forEach((f) => out[f.status]++);
    return out;
  }, [findings.data]);
  const run = useMutation({
    mutationFn: () => api.runCase(caseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["case", caseId] });
      nav(`/cases/${caseId}/pipeline`);
    },
  });

  if (c.isLoading) return <Loading label="Loading case" className="h-full" />;
  if (c.isError) return <ErrorState title="This case could not load" error={c.error} onRetry={() => c.refetch()} />;
  const { case: cs, documents } = c.data!;
  const done = cs.status === "complete";
  const running = cs.status === "running";
  const needsAttention = counts.POTENTIAL_MANIPULATION + counts.INCONSISTENCY;
  const nothingRead = documents.length > 0 && documents.every((d) => d.page_count === 0);

  return (
    <div className="mx-auto flex max-w-[860px] flex-col gap-5 pb-10">
      <PageHeading title={done ? "Results" : documents.length ? "Ready when you are" : "Add your documents"} />
      {run.isError && <ErrorState title="The check didn't start" error={run.error} />}

      <div className="flex flex-col gap-6 px-6">
        {done && (
          <section className="rounded-md border border-line bg-panel p-5">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <RiskPlate risk={cs.risk_level} large />
              <HumanReviewPlate />
            </div>
            {needsAttention > 0 ? (
              <ul className="mt-3 space-y-0.5 text-ink-2">
                {counts.POTENTIAL_MANIPULATION > 0 && (
                  <li>
                    <strong className="font-semibold text-man">{plural(counts.POTENTIAL_MANIPULATION, "potential manipulation")}</strong>: signs a
                    document may have been altered
                  </li>
                )}
                {counts.INCONSISTENCY > 0 && (
                  <li>
                    <strong className="font-semibold text-inc">{plural(counts.INCONSISTENCY, "inconsistency", "inconsistencies")}</strong>: values
                    that should match but don't
                  </li>
                )}
              </ul>
            ) : nothingRead ? (
              <p className="mt-3 text-ink-2">None of these files could be read, so nothing was checked. The list below says why.</p>
            ) : (
              <p className="mt-3 text-ink-2">Nothing stood out. That doesn't prove the documents are genuine.</p>
            )}
            {counts.OBSERVATION > 0 && (
              <p className="mt-1 text-[14px] text-ink-3">Plus {plural(counts.OBSERVATION, "minor observation")}, usually nothing to worry about.</p>
            )}
            <div className={cn("mt-4 flex flex-wrap items-center gap-3", nothingRead && "hidden")}>
              <Button asChild variant="primary">
                <Link to={`/cases/${caseId}/viewer`}>Review findings</Link>
              </Button>
              <Button asChild>
                <Link to={`/cases/${caseId}/dossier`}>Open the report</Link>
              </Button>
            </div>
            <p className={cn("mt-3 text-[13px] text-ink-3", nothingRead && "hidden")}>
              The risk level helps you decide what to look at first. It isn't a decision about the applicant.
            </p>
          </section>
        )}

        {!done && !running && <Upload caseId={caseId} large={documents.length === 0} />}

        {documents.length > 0 && (
          <section aria-labelledby="docs-h">
            <h2 id="docs-h" className="mb-2 text-[17px] font-semibold">
              {plural(documents.length, "document")}
            </h2>
            <ul className="rounded-md border border-line bg-panel">
              {documents.map((d) => (
                <DocRow
                  key={d.id}
                  d={d}
                  caseRunning={running}
                  toReview={(findings.data ?? []).filter((f) => f.status !== "OBSERVATION" && (f.doc_id === d.id || f.evidence.some((e) => e.doc_id === d.id))).length}
                />
              ))}
            </ul>
          </section>
        )}

        {!done && (
          <div>
            {running ? (
              <Button asChild variant="primary">
                <Link to={`/cases/${caseId}/pipeline`}>
                  <Loader2 className="animate-spin" aria-hidden /> See progress
                </Link>
              </Button>
            ) : (
              <Button variant="primary" size="lg" disabled={documents.length === 0 || run.isPending} onClick={() => run.mutate()}>
                Check these documents
              </Button>
            )}
          </div>
        )}

        {done && (
          <details className="text-[14px]">
            <summary>Add more documents or check again</summary>
            <div className="mt-3 flex flex-col gap-3">
              <Upload caseId={caseId} large={false} />
              <div className="flex flex-wrap items-center gap-3">
                <Button disabled={run.isPending} onClick={() => run.mutate()}>
                  Check again
                </Button>
                <Link className="link" to={`/cases/${caseId}/pipeline`}>
                  See each step of the last check
                </Link>
              </div>
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

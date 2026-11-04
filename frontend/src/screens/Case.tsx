import { useCallback, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileWarning, Loader2, Play, RotateCw, UploadCloud } from "lucide-react";
import { api } from "@/api";
import { useCase } from "@/api/hooks";
import type { DocumentSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { ConfidenceMeter, ProcBadge } from "@/components/StatusBadge";
import { PageHeading } from "@/components/Shell";
import { cn, humanize } from "@/lib/utils";

function DocRow({ d }: { d: DocumentSummary }) {
  const problem = d.status === "unsupported" || d.status === "failed" || d.status === "degraded";
  return (
    <tr className="border-b border-line align-top">
      <td className="px-4 py-2.5">
        <div className="break-all font-mono text-[13px] text-ink">{d.filename}</div>
        {d.status_message && (
          <div className={cn("mt-1 flex items-start gap-1.5 text-[13px]", problem ? "text-ink-2" : "text-ink-3")}>
            {problem && <FileWarning className="mt-0.5 size-3.5 shrink-0 text-inc" aria-hidden />}
            <span>{d.status_message}</span>
          </div>
        )}
      </td>
      <td className="px-3 py-2.5">
        <ProcBadge status={d.status} />
      </td>
      <td className="px-3 py-2.5 font-mono text-xs text-ink-2">{d.format}</td>
      <td className="px-3 py-2.5">
        <div className="text-[13px]">{d.doc_type === "unknown" ? <span className="text-ink-3">Not classified</span> : humanize(d.doc_type)}</div>
        {d.doc_type !== "unknown" && <ConfidenceMeter value={d.doc_type_confidence} label="Classification confidence" />}
      </td>
      <td className="px-3 py-2.5 text-right font-mono text-xs text-ink-2">{d.page_count}</td>
      <td className="px-3 py-2.5 text-right font-mono text-xs text-ink-2">{d.field_count}</td>
      <td className="px-4 py-2.5 text-right font-mono text-xs text-ink-2">{d.finding_count}</td>
    </tr>
  );
}

export function CaseScreen() {
  const { caseId = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const c = useCase(caseId);
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const upload = useMutation({
    mutationFn: (files: File[]) => api.uploadDocuments(caseId, files),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["case", caseId] }),
  });
  const run = useMutation({
    mutationFn: () => api.runCase(caseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["case", caseId] });
      nav(`/cases/${caseId}/pipeline`);
    },
  });

  const onFiles = useCallback(
    (list: FileList | null) => {
      const files = list ? Array.from(list) : [];
      if (files.length) upload.mutate(files);
    },
    [upload],
  );

  if (c.isLoading) return <Loading label="Loading case" className="h-full" />;
  if (c.isError) return <ErrorState title="This case could not load" error={c.error} onRetry={() => c.refetch()} />;
  const { case: cs, documents } = c.data!;
  const runnable = documents.length > 0 && cs.status !== "running";
  const done = cs.status === "complete";

  return (
    <div className="flex flex-col">
      <PageHeading
        eyebrow="Step 1 · Submission"
        title={cs.name}
        actions={
          <>
            {done && (
              <Button asChild>
                <Link to={`/cases/${caseId}/viewer`}>Review findings</Link>
              </Button>
            )}
            {cs.status === "running" ? (
              <Button asChild variant="primary">
                <Link to={`/cases/${caseId}/pipeline`}>
                  <Loader2 className="animate-spin" aria-hidden /> View progress
                </Link>
              </Button>
            ) : (
              <Button variant={done ? "secondary" : "primary"} disabled={!runnable || run.isPending} onClick={() => run.mutate()}>
                {done ? <RotateCw aria-hidden /> : <Play aria-hidden />}
                {done ? "Run again" : "Run investigation"}
              </Button>
            )}
          </>
        }
      >
        Submit every document for one application together. Relationships between them are the point.
      </PageHeading>
      {run.isError && <ErrorState title="The investigation did not start" error={run.error} />}

      <div className="flex flex-col gap-6 p-6">
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
            "flex flex-col items-center justify-center gap-2 border border-dashed px-6 py-8 text-center transition-colors",
            over ? "border-ink bg-hover" : "border-line-strong bg-panel",
          )}
        >
          {upload.isPending ? (
            <>
              <Loader2 className="size-5 animate-spin text-ink-2" aria-hidden />
              <p className="text-ink-2">Uploading and hashing</p>
            </>
          ) : (
            <>
              <UploadCloud className="size-5 text-ink-2" aria-hidden />
              <p className="text-ink">Drop documents here, or</p>
              <Button size="sm" onClick={() => input.current?.click()}>
                Choose files
              </Button>
              <p className="font-mono text-[11px] text-ink-3">PNG, JPG, scanned PDF, digital PDF. Other files are recorded as unsupported.</p>
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
        {upload.isError && <ErrorState title="Upload rejected" error={upload.error} className="border border-line" />}

        <section aria-labelledby="docs-h">
          <h2 id="docs-h" className="eyebrow mb-2">
            Documents in this case
          </h2>
          {documents.length === 0 ? (
            <Empty title="No documents yet" className="border border-line">
              Add at least one document to start the investigation.
            </Empty>
          ) : (
            <div className="overflow-x-auto border border-line bg-panel">
              <table className="w-full min-w-[720px] text-left">
                <thead>
                  <tr className="eyebrow border-b border-line-strong">
                    <th scope="col" className="px-4 py-2 font-medium">File</th>
                    <th scope="col" className="px-3 py-2 font-medium">Status</th>
                    <th scope="col" className="px-3 py-2 font-medium">Format</th>
                    <th scope="col" className="px-3 py-2 font-medium">Type</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">Pages</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">Fields</th>
                    <th scope="col" className="px-4 py-2 text-right font-medium">Findings</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((d) => (
                    <DocRow key={d.id} d={d} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

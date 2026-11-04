import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, FileStack, Loader2, Plus } from "lucide-react";
import { api } from "@/api";
import type { Case } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { RiskPlate } from "@/components/StatusBadge";
import { fmtTime } from "@/lib/utils";

function CaseRow({ c }: { c: Case }) {
  return (
    <li>
      <Link to={`/cases/${c.id}`} className="flex items-center gap-3 border-b border-line px-4 py-2.5 hover:bg-hover">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{c.name}</div>
          <div className="truncate font-mono text-[11px] text-ink-3">
            {c.id} · {fmtTime(c.created_at)} · {c.status}
          </div>
        </div>
        <RiskPlate risk={c.risk_level} assessed={c.status === "complete"} />
      </Link>
    </li>
  );
}

export function HomeScreen() {
  const nav = useNavigate();
  const [name, setName] = useState("");
  const demos = useQuery({ queryKey: ["demo-cases"], queryFn: () => api.demoCases() });
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api.listCases() });
  const load = useMutation({
    mutationFn: (key: string) => api.loadDemoCase(key),
    onSuccess: (c) => nav(`/cases/${c.id}`),
  });
  const create = useMutation({
    mutationFn: () => api.createCase(name.trim() || "Untitled investigation"),
    onSuccess: (c) => nav(`/cases/${c.id}`),
  });

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-8 px-6 py-8">
      <section className="max-w-[72ch]">
        <h1 className="display text-[32px] leading-[1.1]">
          OCR reads a document.
          <br />
          This examines whether to believe it.
        </h1>
        <p className="mt-3 text-[15px] text-ink-2">
          Pixel and PDF-structure forensics, cross-document reconciliation, and evidence you can trace to the exact
          source region. Findings are stated as observations, inconsistencies or hypotheses for an examiner. The system
          never issues a verdict.
        </p>
      </section>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="demo-h">
          <h2 id="demo-h" className="eyebrow mb-2">
            Demo cases (synthetic documents)
          </h2>
          {demos.isLoading && <Loading label="Loading demo cases" />}
          {demos.isError && <ErrorState title="Demo cases are unavailable" error={demos.error} onRetry={() => demos.refetch()} className="border border-line" />}
          {demos.data?.length === 0 && (
            <Empty title="No demo cases found" className="border border-line">
              Generate them with scripts/generate_dataset.py.
            </Empty>
          )}
          <ul className="grid gap-2 sm:grid-cols-2">
            {demos.data?.map((d) => (
              <li key={d.key} className="flex flex-col border border-line bg-panel">
                <div className="flex-1 p-3">
                  <div className="font-mono text-[11px] text-ink-3">{d.key}</div>
                  <div className="display mt-0.5 text-[15px]">{d.name}</div>
                  <p className="mt-1 text-[13px] leading-snug text-ink-2">{d.description}</p>
                  <div className="mt-2 flex items-center gap-1 font-mono text-[11px] text-ink-3">
                    <FileStack className="size-3" aria-hidden /> {d.documents.length} documents
                  </div>
                </div>
                <Button
                  variant="ghost"
                  className="w-full justify-between rounded-none border-t border-line px-3 text-ink"
                  disabled={load.isPending}
                  onClick={() => load.mutate(d.key)}
                >
                  Load demo case
                  {load.isPending && load.variables === d.key ? <Loader2 className="animate-spin" aria-hidden /> : <ArrowRight aria-hidden />}
                </Button>
              </li>
            ))}
          </ul>
          {load.isError && <ErrorState title="Could not load that demo case" error={load.error} />}
        </section>

        <div className="flex flex-col gap-8">
          <section aria-labelledby="new-h">
            <h2 id="new-h" className="eyebrow mb-2">
              New investigation
            </h2>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                create.mutate();
              }}
            >
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Case name"
                aria-label="Case name"
                className="h-9 min-w-0 flex-1 border border-line-strong bg-panel px-3 text-ink placeholder:text-ink-3"
              />
              <Button variant="primary" type="submit" disabled={create.isPending}>
                <Plus aria-hidden /> Create
              </Button>
            </form>
            {create.isError && <ErrorState title="Could not create the case" error={create.error} />}
            <p className="mt-2 text-[13px] text-ink-3">Use only authorized or synthetic documents.</p>
          </section>

          <section aria-labelledby="recent-h">
            <h2 id="recent-h" className="eyebrow mb-2">
              Recent cases
            </h2>
            <div className="border-x border-t border-line bg-panel">
              {cases.isLoading && <Loading label="Loading cases" className="border-b border-line" />}
              {cases.isError && <ErrorState title="Cases are unavailable" error={cases.error} onRetry={() => cases.refetch()} className="border-b border-line" />}
              {cases.data?.length === 0 && <Empty title="No cases yet" className="border-b border-line" />}
              <ul>
                {cases.data?.slice(0, 8).map((c) => (
                  <CaseRow key={c.id} c={c} />
                ))}
              </ul>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Download, FileJson, FileText } from "lucide-react";
import { api } from "@/api";
import { useCaseDocuments } from "@/api/hooks";
import type { Dossier, Field, Finding } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { PageHeading } from "@/components/Shell";
import { Provenance } from "@/components/FindingCard";
import { ConfidenceMeter, HumanReviewPlate, ProcBadge, ReviewBadge, RiskPlate, StatusBadge } from "@/components/StatusBadge";
import { cn, fmtBBox, fmtTime, humanize, shortHash } from "@/lib/utils";

const SECTIONS = [
  ["s71", "7.1", "Document Overview"],
  ["s72", "7.2", "Extracted Information"],
  ["s73", "7.3", "Contextual Analysis"],
  ["s74", "7.4", "Visual Forensic Findings"],
  ["s75", "7.5", "Evidence & Traceability"],
  ["s76", "7.6", "Investigation Summary"],
] as const;

function H({ id, n, title }: { id: string; n: string; title: string }) {
  return (
    <h2 id={id} className="display mb-3 flex scroll-mt-4 items-baseline gap-3 border-b border-line-strong pb-1.5 text-[18px]">
      <span className="font-mono text-[13px] font-medium text-ink-3">{n}</span>
      {title}
    </h2>
  );
}

function FindingRow({ f, docName, caseId }: { f: Finding; docName: string; caseId: string }) {
  const q = new URLSearchParams({ finding: f.id });
  if (f.doc_id) q.set("doc", f.doc_id);
  if (f.page !== null) q.set("page", String(f.page));
  return (
    <li className="border-b border-line py-2.5 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={f.status} />
        <Link to={{ pathname: `/cases/${caseId}/viewer`, search: q.toString() }} className="font-medium underline-offset-2 hover:underline">
          {f.title}
        </Link>
        <span className="ml-auto">
          <ConfidenceMeter value={f.fused_score ?? f.confidence} />
        </span>
      </div>
      <p className="mt-1 leading-relaxed text-ink-2">{f.explanation}</p>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-ink-3">
        <span>{docName}</span>
        {f.page !== null && <span>p{f.page + 1}</span>}
        {f.bbox && <span>{fmtBBox(f.bbox)}</span>}
        <span>{f.detector}</span>
        {f.review.decision !== "pending" && <ReviewBadge decision={f.review.decision} />}
      </div>
    </li>
  );
}

function Bullets({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p className="text-ink-3">{empty}</p>;
  return (
    <ul className="list-disc space-y-1 pl-5 text-ink-2 marker:text-ink-3">
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  );
}

function downloadJson(d: Dossier) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `dossier_${d.case_id}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export function DossierScreen() {
  const { caseId = "" } = useParams();
  const q = useQuery({ queryKey: ["dossier", caseId], queryFn: () => api.dossier(caseId), retry: 0 });
  const { byId } = useCaseDocuments(caseId);
  const d = q.data;

  const names = useMemo(() => {
    const m = new Map<string, string>();
    d?.overview.forEach((o) => m.set(o.doc_id, o.filename));
    return m;
  }, [d]);
  const nameOf = (id: string | null) => (id ? (names.get(id) ?? byId.get(id)?.filename ?? id) : "Case level");

  if (q.isLoading) return <Loading label="Assembling dossier" className="h-full" />;
  if (q.isError) {
    return (
      <div className="flex flex-col">
        <PageHeading eyebrow="Step 10 · Dossier" title="Investigation dossier" />
        <ErrorState title="The dossier is not available" error={q.error} onRetry={() => q.refetch()} />
        <p className="px-6 text-ink-3">
          A dossier exists once the investigation has finished.{" "}
          <Link className="underline" to={`/cases/${caseId}/pipeline`}>
            Go to pipeline
          </Link>
        </p>
      </div>
    );
  }
  if (!d) return <Empty title="No dossier yet" className="h-full" />;

  return (
    <div className="flex flex-col">
      <PageHeading
        eyebrow="Step 10 · Dossier"
        title={d.case_name}
        actions={
          <>
            <Button asChild variant="primary">
              <a href={api.dossierPdfUrl(caseId)} download>
                <Download aria-hidden /> <FileText aria-hidden /> PDF
              </a>
            </Button>
            <Button onClick={() => downloadJson(d)}>
              <Download aria-hidden /> <FileJson aria-hidden /> JSON
            </Button>
          </>
        }
      >
        Generated {fmtTime(d.generated_at)}. Text produced by:{" "}
        <span className="font-mono text-[13px]">{d.reasoning_modes.join(", ") || "not recorded"}</span>.
      </PageHeading>

      <div className="grid gap-8 px-6 py-6 xl:grid-cols-[190px_minmax(0,1fr)]">
        <nav aria-label="Dossier sections" className="hidden xl:block">
          <ul className="sticky top-4 flex flex-col gap-1">
            {SECTIONS.map(([id, n, t]) => (
              <li key={id}>
                <a href={`#${id}`} className="flex gap-2 px-1 py-0.5 text-[13px] text-ink-2 hover:text-ink">
                  <span className="font-mono text-ink-3">{n}</span>
                  {t}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <article className="flex min-w-0 max-w-[920px] flex-col gap-10">
          <div className="flex flex-col gap-2 border border-line bg-panel p-4">
            <div className="flex flex-wrap items-center gap-2">
              <RiskPlate risk={d.risk_level} large />
              <HumanReviewPlate />
            </div>
            <p className="text-ink-2">{d.disclaimer}</p>
            {d.audit_head_hash && <p className="font-mono text-[11px] text-ink-3">Audit head at generation: {shortHash(d.audit_head_hash, 32)}</p>}
          </div>

          <section>
            <H id="s71" n="7.1" title="Document Overview" />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-[13px]">
                <thead>
                  <tr className="eyebrow border-b border-line">
                    <th scope="col" className="py-1.5 pr-3 font-medium">Source file</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Type</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Format</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Pages</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">SHA-256</th>
                    <th scope="col" className="py-1.5 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {d.overview.map((o) => (
                    <tr key={o.doc_id} className="border-b border-line align-top">
                      <td className="py-1.5 pr-3 font-mono text-xs">{o.filename}</td>
                      <td className="py-1.5 pr-3">
                        {humanize(o.doc_type)} <span className="font-mono text-[11px] text-ink-3">{Math.round(o.doc_type_confidence * 100)}%</span>
                      </td>
                      <td className="py-1.5 pr-3 font-mono text-xs">{o.format}</td>
                      <td className="py-1.5 pr-3 font-mono text-xs">{o.pages}</td>
                      <td className="py-1.5 pr-3 font-mono text-[11px] text-ink-3" title={o.sha256}>
                        {shortHash(o.sha256, 14)}
                      </td>
                      <td className="py-1.5">
                        <ProcBadge status={o.status} />
                        {o.status_message && <div className="mt-1 max-w-56 text-xs text-ink-3">{o.status_message}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <H id="s72" n="7.2" title="Extracted Information" />
            <div className="flex flex-col gap-5">
              {d.overview.map((o) => {
                const fields: Field[] = d.extracted[o.doc_id] ?? [];
                const secs = d.structure[o.doc_id] ?? [];
                const tables = d.tables?.[o.doc_id] ?? [];
                return (
                  <div key={o.doc_id}>
                    <h3 className="mb-1 font-mono text-xs text-ink-2">{o.filename}</h3>
                    {secs.length > 0 && <p className="mb-1 text-xs text-ink-3">Structure: {secs.map((s) => humanize(s.name)).join(" › ")}</p>}
                    {fields.length === 0 ? (
                      <p className="text-ink-3">No fields extracted from this document.</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[560px] text-left text-[13px]">
                          <tbody>
                            {fields.map((f) => (
                              <tr key={f.id} className="border-b border-line align-baseline">
                                <td className="w-48 py-1 pr-3 text-ink-2">{humanize(f.name)}</td>
                                <td className="py-1 pr-3 font-mono text-xs">{f.value_raw}</td>
                                <td className="w-20 whitespace-nowrap py-1 pr-3">
                                  <ConfidenceMeter value={f.confidence} low={f.confidence < 0.55} />
                                </td>
                                <td className="w-44 whitespace-nowrap py-1 font-mono text-[11px] text-ink-3">
                                  p{f.page + 1} {fmtBBox(f.bbox)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {tables.map((t) => (
                      <p key={t.id} className="mt-1 text-xs text-ink-3">
                        Table “{humanize(t.name)}”: {t.rows.length} rows, {t.headers.join(", ")}
                      </p>
                    ))}
                  </div>
                );
              })}
            </div>
          </section>

          <section>
            <H id="s73" n="7.3" title="Contextual Analysis" />
            <h3 className="eyebrow mb-1">Within documents</h3>
            {d.contextual_findings.length === 0 ? (
              <p className="mb-4 text-ink-3">No within-document inconsistencies recorded.</p>
            ) : (
              <ul className="mb-4">
                {d.contextual_findings.map((f) => (
                  <FindingRow key={f.id} f={f} docName={nameOf(f.doc_id)} caseId={caseId} />
                ))}
              </ul>
            )}
            <h3 className="eyebrow mb-1">Across documents</h3>
            {d.cross_document_findings.length === 0 ? (
              <p className="mb-4 text-ink-3">No cross-document conflicts recorded.</p>
            ) : (
              <ul className="mb-4">
                {d.cross_document_findings.map((f) => (
                  <FindingRow key={f.id} f={f} docName={nameOf(f.doc_id)} caseId={caseId} />
                ))}
              </ul>
            )}
            <h3 className="eyebrow mb-1">Missing or duplicated information</h3>
            {Object.entries(d.missing_or_duplicated).filter(([, v]) => (v.missing?.length ?? 0) + (v.duplicated?.length ?? 0) > 0).length === 0 ? (
              <p className="text-ink-3">None recorded.</p>
            ) : (
              <ul className="space-y-1 text-[13px]">
                {Object.entries(d.missing_or_duplicated).map(([id, v]) =>
                  (v.missing?.length ?? 0) + (v.duplicated?.length ?? 0) > 0 ? (
                    <li key={id}>
                      <span className="font-mono text-xs text-ink-2">{nameOf(id)}</span>
                      {v.missing?.length ? <span className="ml-2 text-ink-2">missing {v.missing.join(", ")}</span> : null}
                      {v.duplicated?.length ? <span className="ml-2 text-ink-2">duplicated {v.duplicated.join(", ")}</span> : null}
                    </li>
                  ) : null,
                )}
              </ul>
            )}
          </section>

          <section>
            <H id="s74" n="7.4" title="Visual Forensic Findings" />
            {d.visual_findings.length === 0 ? (
              <p className="text-ink-3">No visual or structural signals were raised. This does not establish authenticity.</p>
            ) : (
              <ul>
                {d.visual_findings.map((f) => (
                  <FindingRow key={f.id} f={f} docName={nameOf(f.doc_id)} caseId={caseId} />
                ))}
              </ul>
            )}
          </section>

          <section>
            <H id="s75" n="7.5" title="Evidence & Traceability" />
            {d.traceability.length === 0 ? (
              <p className="text-ink-3">No traceability records.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left font-mono text-[11px]">
                  <thead>
                    <tr className="eyebrow border-b border-line">
                      {Object.keys(d.traceability[0]).map((k) => (
                        <th key={k} scope="col" className="py-1.5 pr-3 font-medium">{humanize(k)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {d.traceability.map((row, i) => (
                      <tr key={i} className="border-b border-line align-top text-ink-2">
                        {Object.keys(d.traceability[0]).map((k) => (
                          <td key={k} className={cn("max-w-64 break-words py-1 pr-3")}>
                            {typeof row[k] === "object" ? JSON.stringify(row[k]) : String(row[k] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="flex flex-col gap-4">
            <H id="s76" n="7.6" title="Investigation Summary" />
            <p className="whitespace-pre-line text-[15px] leading-relaxed">{d.summary}</p>
            <div>
              <h3 className="eyebrow mb-1">Potential explanations</h3>
              <Bullets items={d.potential_explanations} empty="None recorded." />
            </div>
            <div>
              <h3 className="eyebrow mb-1">Areas requiring additional verification</h3>
              <Bullets items={d.areas_for_verification} empty="None recorded." />
            </div>
            <div>
              <h3 className="eyebrow mb-1">Investigation limitations</h3>
              <Bullets items={d.limitations} empty="None recorded." />
            </div>
            {d.reasoning_modes.includes("deterministic") && <Provenance r={{ mode: "deterministic", provider: null, model: null, prompt_hash: null }} />}
          </section>
        </article>
      </div>
    </div>
  );
}

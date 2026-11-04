import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, Search } from "lucide-react";
import { api } from "@/api";
import { useCaseDocuments } from "@/api/hooks";
import type { BBox, CaseField, Document, Section, Table } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { DocCanvas } from "@/components/DocCanvas";
import { ConfidenceMeter } from "@/components/StatusBadge";
import { cn, fmtBBox, humanize } from "@/lib/utils";

const LOW = 0.55;

type Tab = "fields" | "tables" | "structure";
interface Target {
  docId: string;
  page: number;
  bbox: BBox;
  label: string;
  key: string;
}

export function DataScreen() {
  const { caseId = "" } = useParams();
  const fieldsQ = useQuery({ queryKey: ["fields", caseId], queryFn: () => api.fields(caseId) });
  const { summaries, byId } = useCaseDocuments(caseId);
  const [tab, setTab] = useState<Tab>("fields");
  const [query, setQuery] = useState("");
  const [docFilter, setDocFilter] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [target, setTarget] = useState<Target | null>(null);

  const rows = useMemo(() => {
    const q = query.toLowerCase();
    return (fieldsQ.data ?? []).filter(
      (f) =>
        (!docFilter || f.doc_id === docFilter) &&
        (!lowOnly || f.confidence < LOW) &&
        (!q || f.name.toLowerCase().includes(q) || f.value_raw.toLowerCase().includes(q) || f.doc_filename.toLowerCase().includes(q)),
    );
  }, [fieldsQ.data, query, docFilter, lowOnly]);

  const docs = useMemo(() => [...byId.values()], [byId]);
  const targetDoc = target ? byId.get(target.docId) : undefined;
  const lowCount = (fieldsQ.data ?? []).filter((f) => f.confidence < LOW).length;

  const pick = (f: CaseField) =>
    setTarget({ docId: f.doc_id, page: f.page, bbox: f.bbox, key: f.id, label: `${f.label_raw ?? f.name}: ${f.value_raw}` });

  return (
    <div className="grid h-full min-h-[560px] grid-rows-[minmax(0,1fr)_minmax(0,38%)] lg:grid-cols-[minmax(0,1fr)_minmax(300px,38%)] lg:grid-rows-1">
      <div className="flex min-h-0 min-w-0 flex-col border-b border-line lg:border-b-0 lg:border-r">
        <div className="shrink-0 border-b border-line px-4 pt-3">
          <div className="eyebrow">Steps 3 and 4 · Extraction and structure</div>
          <div className="mt-2 flex gap-1" role="tablist" aria-label="Extracted data views">
            {(["fields", "tables", "structure"] as Tab[]).map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={cn(
                  "cursor-pointer border-b-2 px-3 py-1.5 capitalize",
                  tab === t ? "border-ink text-ink" : "border-transparent text-ink-3 hover:text-ink",
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {tab === "fields" && (
          <>
            <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-line bg-panel px-4 py-2">
              <div className="relative">
                <Search className="absolute left-2 top-2 size-3.5 text-ink-3" aria-hidden />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter fields"
                  aria-label="Filter fields"
                  className="h-7 w-44 border border-line-strong bg-ground pl-7 pr-2 text-[13px] text-ink placeholder:text-ink-3"
                />
              </div>
              <select
                value={docFilter}
                onChange={(e) => setDocFilter(e.target.value)}
                aria-label="Filter by document"
                className="h-7 max-w-48 border border-line-strong bg-ground px-1 text-[13px] text-ink"
              >
                <option value="">All documents</option>
                {summaries.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.filename}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1.5 text-[13px] text-ink-2">
                <Switch checked={lowOnly} onCheckedChange={setLowOnly} label="Low confidence only" />
                Low confidence only ({lowCount})
              </label>
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              {fieldsQ.isLoading && <Loading label="Loading extracted fields" />}
              {fieldsQ.isError && <ErrorState title="Fields could not load" error={fieldsQ.error} onRetry={() => fieldsQ.refetch()} />}
              {fieldsQ.data && rows.length === 0 && (
                <Empty title={fieldsQ.data.length === 0 ? "No fields extracted yet" : "No fields match"}>
                  {fieldsQ.data.length === 0 ? "Fields appear after the investigation runs." : "Clear the filters to see all fields."}
                </Empty>
              )}
              {rows.length > 0 && (
                <table className="w-full text-left">
                  <thead className="sticky top-0 z-10 bg-panel">
                    <tr className="eyebrow border-b border-line-strong">
                      <th scope="col" className="px-4 py-2 font-medium">Field</th>
                      <th scope="col" className="px-2 py-2 font-medium">Value</th>
                      <th scope="col" className="px-2 py-2 font-medium">Confidence</th>
                      <th scope="col" className="px-4 py-2 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((f) => {
                      const low = f.confidence < LOW;
                      const on = target?.key === f.id;
                      return (
                        <tr
                          key={f.id}
                          onClick={() => pick(f)}
                          tabIndex={0}
                          aria-selected={on}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              pick(f);
                            }
                          }}
                          className={cn("cursor-pointer border-b border-line align-top hover:bg-hover", on && "bg-raised shadow-[inset_3px_0_0_0_var(--color-ink)]")}
                        >
                          <td className="px-4 py-1.5">
                            <div className="text-[13px]">{humanize(f.name)}</div>
                            {f.label_raw && <div className="text-[11px] text-ink-3">“{f.label_raw}”</div>}
                          </td>
                          <td className="px-2 py-1.5">
                            <div className="break-words font-mono text-[13px]">{f.value_raw}</div>
                            {f.value_norm && f.value_norm !== f.value_raw && (
                              <div className="break-words font-mono text-[11px] text-ink-3">norm {f.value_norm}</div>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-2 py-1.5">
                            <ConfidenceMeter value={f.confidence} low={low} />
                            {low && (
                              <div className="mt-0.5 flex items-center gap-1 text-[11px] text-inc">
                                <AlertTriangle className="size-3" aria-hidden /> Low, verify
                              </div>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-4 py-1.5 font-mono text-[11px] text-ink-3">
                            <div className="max-w-44 truncate text-ink-2" title={f.doc_filename}>{f.doc_filename}</div>
                            <div>
                              p{f.page + 1} {fmtBBox(f.bbox)}
                            </div>
                            <div>{f.source}</div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <p className="shrink-0 border-t border-line bg-panel px-4 py-1.5 text-xs text-ink-3">
              Extracted values are machine readings, not verified facts. Each keeps its confidence and source location.
            </p>
          </>
        )}

        {tab === "tables" && <TablesView docs={docs} target={target} onPick={setTarget} />}
        {tab === "structure" && <StructureView docs={docs} onPick={setTarget} />}
      </div>

      <div className="flex min-h-0 min-w-0 flex-col">
        <div className="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-line bg-panel px-3">
          <span className="truncate font-mono text-xs text-ink-2">{targetDoc?.filename ?? "Source location"}</span>
          {target && (
            <Button asChild size="sm" variant="ghost">
              <Link to={{ pathname: `/cases/${caseId}/viewer`, search: new URLSearchParams({ doc: target.docId, page: String(target.page), ...(target.key.startsWith("fld") ? { field: target.key } : {}) }).toString() }}>
                Open in viewer <ArrowUpRight aria-hidden />
              </Link>
            </Button>
          )}
        </div>
        {target && targetDoc ? (
          <DocCanvas
            caseId={caseId}
            doc={targetDoc}
            page={target.page}
            highlight={{ bbox: target.bbox, label: target.label }}
            focus={target.bbox}
            focusKey={target.key}
            className="min-h-0 flex-1"
          />
        ) : (
          <Empty title="Select a row" className="flex-1">
            The original page opens here with the source region highlighted.
          </Empty>
        )}
      </div>
    </div>
  );
}

function TablesView({ docs, target, onPick }: { docs: Document[]; target: Target | null; onPick: (t: Target) => void }) {
  const tables = docs.flatMap((d) => d.tables.map((t) => ({ d, t })));
  if (tables.length === 0) return <Empty title="No tables extracted" className="flex-1" />;
  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      {tables.map(({ d, t }) => (
        <TableBlock key={t.id} doc={d} table={t} target={target} onPick={onPick} />
      ))}
    </div>
  );
}

function TableBlock({ doc, table, target, onPick }: { doc: Document; table: Table; target: Target | null; onPick: (t: Target) => void }) {
  return (
    <section className="mb-6">
      <h3 className="mb-1 flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium">{humanize(table.name)}</span>
        <span className="font-mono text-[11px] text-ink-3">
          {doc.filename} · p{table.page + 1} · {table.rows.length} rows
        </span>
      </h3>
      <div className="overflow-x-auto border border-line">
        <table className="w-full text-left font-mono text-xs">
          <thead>
            <tr className="eyebrow border-b border-line-strong bg-panel">
              {table.headers.map((h) => (
                <th key={h} scope="col" className="px-2 py-1.5 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i} className="border-b border-line last:border-b-0">
                {row.map((c, j) => {
                  const key = `${table.id}:${i}:${j}`;
                  const low = c.confidence < LOW;
                  return (
                    <td key={j} className={cn("p-0", target?.key === key && "bg-raised")}>
                      <button
                        type="button"
                        disabled={!c.bbox}
                        onClick={() => c.bbox && onPick({ docId: doc.id, page: table.page, bbox: c.bbox, label: c.text, key })}
                        title={`Confidence ${Math.round(c.confidence * 100)}%`}
                        className={cn("block w-full px-2 py-1 text-left enabled:cursor-pointer enabled:hover:bg-hover", low && "text-inc underline decoration-dotted")}
                      >
                        {c.text || " "}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SectionNode({ s, doc, onPick, depth = 0 }: { s: Section; doc: Document; onPick: (t: Target) => void; depth?: number }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onPick({ docId: doc.id, page: s.page, bbox: s.bbox, label: s.name, key: `sec:${doc.id}:${s.name}:${depth}` })}
        className="flex w-full cursor-pointer items-baseline justify-between gap-2 px-2 py-1 text-left hover:bg-hover"
      >
        <span>{humanize(s.name)}</span>
        <span className="font-mono text-[11px] text-ink-3">
          {s.field_ids.length} field{s.field_ids.length === 1 ? "" : "s"}
        </span>
      </button>
      {s.children.length > 0 && (
        <ul className="ml-3 border-l border-line pl-1">
          {s.children.map((c, i) => (
            <SectionNode key={i} s={c} doc={doc} onPick={onPick} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

function StructureView({ docs, onPick }: { docs: Document[]; onPick: (t: Target) => void }) {
  if (docs.length === 0) return <Empty title="No documents loaded" className="flex-1" />;
  return (
    <div className="grid min-h-0 flex-1 content-start gap-3 overflow-auto p-4 xl:grid-cols-2">
      {docs.map((d) => (
        <section key={d.id} className="border border-line bg-panel">
          <header className="border-b border-line px-3 py-2">
            <div className="eyebrow">{humanize(d.doc_type)}</div>
            <div className="truncate font-mono text-xs text-ink-2">{d.filename}</div>
          </header>
          {d.sections.length === 0 ? (
            <p className="px-3 py-2 text-[13px] text-ink-3">No layout sections identified.</p>
          ) : (
            <ul className="p-1 text-[13px]">
              {d.sections.map((s, i) => (
                <SectionNode key={i} s={s} doc={d} onPick={onPick} />
              ))}
            </ul>
          )}
          {(d.missing_fields.length > 0 || d.duplicated_fields.length > 0) && (
            <div className="border-t border-line px-3 py-2 text-[13px]">
              {d.missing_fields.length > 0 && (
                <p className="text-ink-2">
                  <span className="text-inc">Missing:</span> <span className="font-mono text-xs">{d.missing_fields.join(", ")}</span>
                </p>
              )}
              {d.duplicated_fields.length > 0 && (
                <p className="text-ink-2">
                  <span className="text-inc">Duplicated:</span> <span className="font-mono text-xs">{d.duplicated_fields.join(", ")}</span>
                </p>
              )}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

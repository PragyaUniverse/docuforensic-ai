import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, FileX } from "lucide-react";
import { api } from "@/api";
import { useCase, useCaseDocuments, useFindings } from "@/api/hooks";
import type { BBox, Finding, FindingStatus } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Slider } from "@/components/ui/slider";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { ComparisonPanel } from "@/components/ComparisonPanel";
import { DocCanvas } from "@/components/DocCanvas";
import { FindingCard } from "@/components/FindingCard";
import { ProcBadge } from "@/components/StatusBadge";
import { comparisonSources, findingLabels, regionsForPage, sortFindings } from "@/lib/findings";
import { cn, humanize } from "@/lib/utils";

export function locationOf(f: Finding): { docId: string; page: number; bbox: BBox | null } | null {
  if (f.doc_id && f.page !== null) return { docId: f.doc_id, page: f.page, bbox: f.bbox };
  const ev = f.evidence.find((e) => e.doc_id && e.page !== null);
  if (ev) return { docId: ev.doc_id!, page: ev.page!, bbox: ev.bbox };
  if (f.doc_id) return { docId: f.doc_id, page: 0, bbox: null };
  return null;
}

export function ViewerScreen() {
  const { caseId = "" } = useParams();
  const [sp, setSp] = useSearchParams();
  const caseQ = useCase(caseId);
  const { summaries, byId, fieldsById, isLoading: docsLoading, error: docsError } = useCaseDocuments(caseId);
  const findingsQ = useFindings(caseId);
  const findings = useMemo(() => sortFindings(findingsQ.data ?? []), [findingsQ.data]);
  const labels = useMemo(() => findingLabels(findingsQ.data ?? []), [findingsQ.data]);

  const firstViewable = summaries.find((s) => s.page_count > 0)?.id ?? summaries[0]?.id;
  const selectedId = sp.get("finding");
  // A link naming only a finding opens at that finding's own location.
  const linked = !sp.get("doc") && selectedId ? findings.find((f) => f.id === selectedId) : undefined;
  const linkedLoc = linked ? locationOf(linked) : null;
  const docId = sp.get("doc") ?? linkedLoc?.docId ?? firstViewable ?? null;
  const page = Number(sp.get("page") ?? linkedLoc?.page ?? 0) || 0;
  const fieldId = sp.get("field");
  const doc = docId ? byId.get(docId) : undefined;
  const selected = findings.find((f) => f.id === selectedId) ?? null;
  const field = fieldId ? fieldsById.get(fieldId) : undefined;

  // Minor observations stay out of the way until someone asks for them.
  const [showMinor, setShowMinor] = useState(false);
  const minorOpen = showMinor || selected?.status === "OBSERVATION";
  const statuses = useMemo<Record<FindingStatus, boolean>>(
    () => ({ OBSERVATION: minorOpen, INCONSISTENCY: true, POTENTIAL_MANIPULATION: true }),
    [minorOpen],
  );
  const [heatKind, setHeatKind] = useState<string | null>(null);
  const [heatOpacity, setHeatOpacity] = useState(70);
  const [showLinks, setShowLinks] = useState(true);
  const [onlyThisDoc, setOnlyThisDoc] = useState(false);
  const [focusNonce, setFocusNonce] = useState(0);
  const [compare, setCompare] = useState<Finding | null>(null);

  const overlays = useQuery({
    queryKey: ["overlays", caseId, docId, page],
    queryFn: () => api.listOverlays(caseId, docId!, page),
    enabled: !!doc && doc.pages.length > 0,
  });
  useEffect(() => {
    if (heatKind && overlays.data && !overlays.data.some((o) => o.kind === heatKind)) setHeatKind(null);
  }, [overlays.data, heatKind]);
  const activeOverlay = overlays.data?.find((o) => o.kind === heatKind) ?? null;

  const update = useCallback(
    (patch: Record<string, string | null>) => {
      setSp(
        (prev) => {
          const n = new URLSearchParams(prev);
          Object.entries(patch).forEach(([k, v]) => (v === null ? n.delete(k) : n.set(k, v)));
          return n;
        },
        { replace: true },
      );
    },
    [setSp],
  );

  const selectFinding = useCallback(
    (f: Finding, move: boolean) => {
      const deselect = selectedId === f.id && !move;
      if (deselect) {
        update({ finding: null, field: null });
        return;
      }
      const loc = move ? locationOf(f) : null;
      const alreadyHere = loc?.docId === docId && loc?.page === page;
      update({
        finding: f.id,
        field: null,
        ...(loc && !alreadyHere ? { doc: loc.docId, page: String(loc.page) } : {}),
      });
      setFocusNonce((n) => n + 1);
    },
    [update, selectedId, docId, page],
  );

  const pageRegions = useMemo(
    () => (docId ? regionsForPage(findings, docId, page).filter((r) => statuses[r.finding.status]) : []),
    [findings, docId, page, statuses],
  );

  const links = useMemo(() => {
    if (!showLinks || !docId) return [] as Array<[BBox, BBox]>;
    const out: Array<[BBox, BBox]> = [];
    findings
      .filter((f) => f.detector.includes("copy_move") && statuses[f.status])
      .forEach((f) => {
        const rs = regionsForPage([f], docId, page);
        for (let i = 1; i < rs.length; i++) out.push([rs[0].bbox, rs[i].bbox]);
      });
    return out;
  }, [findings, docId, page, statuses, showLinks]);

  const focusBox = useMemo(() => {
    if (field && field.doc_id === docId && field.page === page) return field.bbox;
    if (selected && docId) {
      const rs = regionsForPage([selected], docId, page);
      return rs.find((r) => r.primary)?.bbox ?? rs[0]?.bbox ?? null;
    }
    return null;
  }, [field, selected, docId, page]);

  const matchesDoc = useCallback(
    (f: Finding) =>
      !onlyThisDoc || !docId || f.doc_id === docId || f.related_doc_ids.includes(docId) || f.evidence.some((e) => e.doc_id === docId),
    [onlyThisDoc, docId],
  );
  const important = useMemo(() => findings.filter((f) => f.status !== "OBSERVATION" && matchesDoc(f)), [findings, matchesDoc]);
  const minor = useMemo(() => findings.filter((f) => f.status === "OBSERVATION" && matchesDoc(f)), [findings, matchesDoc]);

  const docCounts = useCallback(
    (id: string) =>
      findings.filter((f) => f.status !== "OBSERVATION" && (f.doc_id === id || f.evidence.some((e) => e.doc_id === id))).length,
    [findings],
  );

  if (caseQ.isLoading || docsLoading) return <Loading label="Loading" className="h-full" />;
  if (docsError) return <ErrorState title="Documents could not load" error={docsError} />;
  if (summaries.length === 0) {
    return (
      <Empty
        title="No documents yet"
        className="h-full"
        action={
          <Button asChild>
            <Link to={`/cases/${caseId}`}>Add documents</Link>
          </Button>
        }
      />
    );
  }
  const renderCard = (f: Finding) => (
    <FindingCard
      key={f.id}
      finding={f}
      label={labels.get(f.id) ?? ""}
      caseId={caseId}
      docs={byId}
      labelsById={labels}
      selected={f.id === selectedId}
      onSelect={() => selectFinding(f, true)}
      onSelectRelated={(id) => {
        const r = findings.find((x) => x.id === id);
        if (r) selectFinding(r, true);
      }}
      onCompare={comparisonSources(f, fieldsById).length >= 2 ? () => setCompare(f) : undefined}
    />
  );
  const notRun = caseQ.data?.case.status !== "complete";
  const noneAnalysed = summaries.every((s) => s.page_count === 0);

  return (
    <div className="grid h-full min-h-[560px] grid-rows-[minmax(0,55fr)_minmax(0,45fr)] lg:grid-cols-[minmax(0,1fr)_400px] lg:grid-rows-1 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="flex min-h-0 min-w-0 flex-col border-b border-line lg:border-b-0 lg:border-r">
        <div role="tablist" aria-label="Documents" data-tour="doc-tabs" className="flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-panel px-2">
          {summaries.map((s) => {
            const active = s.id === docId;
            const n = docCounts(s.id);
            return (
              <button
                key={s.id}
                role="tab"
                aria-selected={active}
                type="button"
                title={s.filename}
                onClick={() => update({ doc: s.id, page: "0", field: null })}
                className={cn(
                  "relative shrink-0 cursor-pointer px-2.5 py-2 text-[14px] transition-colors duration-150",
                  active ? "font-medium text-ink" : "text-ink-2 hover:text-ink",
                )}
              >
                {s.doc_type === "unknown" ? s.filename : humanize(s.doc_type)}
                {n > 0 && <span className="ml-1.5 text-[13px] font-normal text-ink-3">{n}</span>}
                {active && <motion.span layoutId="doc-tab" transition={{ duration: 0.2, ease: "easeOut" }} className="absolute inset-x-0 bottom-0 h-0.5 bg-accent" />}
              </button>
            );
          })}
        </div>

        {doc && doc.pages.length > 0 && (
          <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-line bg-panel px-3 py-1.5 text-[14px]">
            {doc.pages.length > 1 && (
              <div className="flex items-center gap-1">
                <Button size="icon" variant="ghost" aria-label="Previous page" disabled={page <= 0} onClick={() => update({ page: String(page - 1) })}>
                  <ChevronLeft aria-hidden />
                </Button>
                <span className="text-ink-2">
                  Page {page + 1} of {doc.pages.length}
                </span>
                <Button size="icon" variant="ghost" aria-label="Next page" disabled={page >= doc.pages.length - 1} onClick={() => update({ page: String(page + 1) })}>
                  <ChevronRight aria-hidden />
                </Button>
              </div>
            )}
            {!!overlays.data?.length && (
              <label data-tour="show" className="flex items-center gap-1.5 text-ink-2">
                Show
                <select
                  value={heatKind ?? ""}
                  onChange={(e) => setHeatKind(e.target.value || null)}
                  className="h-8 rounded-md border border-line-strong bg-panel px-1.5 text-ink"
                >
                  <option value="">The document</option>
                  {overlays.data.map((o) => (
                    <option key={o.kind} value={o.kind}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {heatKind && <Slider value={heatOpacity} onChange={setHeatOpacity} label="Overlay strength" />}
            {links.length > 0 && (
              <label className="flex items-center gap-1.5 text-ink-2">
                <input type="checkbox" checked={showLinks} onChange={(e) => setShowLinks(e.target.checked)} />
                Show copied-region links
              </label>
            )}
          </div>
        )}

        {doc && doc.pages.length > 0 ? (
          <DocCanvas
            tourTarget="canvas"
            caseId={caseId}
            doc={doc}
            page={Math.min(page, doc.pages.length - 1)}
            regions={pageRegions}
            labels={labels}
            selectedFindingId={selectedId}
            onSelectFinding={(id) => {
              const f = findings.find((x) => x.id === id);
              if (f) selectFinding(f, false);
            }}
            highlight={field && field.doc_id === docId && field.page === page ? { bbox: field.bbox, label: `${field.label_raw ?? field.name}: ${field.value_raw}` } : null}
            heatmap={activeOverlay ? { url: activeOverlay.url, opacity: heatOpacity / 100 } : null}
            links={links}
            focus={focusBox}
            focusKey={focusNonce}
            className="flex-1"
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 bg-ground p-8 text-center">
            <FileX className="size-6 text-ink-3" aria-hidden />
            <p className="font-medium">We can't show this file</p>
            {doc && <ProcBadge status={doc.status} />}
            <p className="max-w-md text-ink-2">{doc?.status_message ?? "It couldn't be opened, so it wasn't checked."}</p>
          </div>
        )}
      </div>

      <aside aria-label="Findings" data-tour="findings" className="flex min-h-0 flex-col bg-panel">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h1 className="text-[17px] font-semibold">
            Findings{findingsQ.data ? <span className="ml-1.5 font-normal text-ink-3">{important.length}</span> : null}
          </h1>
          <label className="flex items-center gap-1.5 text-[13px] text-ink-2">
            <input type="checkbox" checked={onlyThisDoc} onChange={(e) => setOnlyThisDoc(e.target.checked)} />
            This document only
          </label>
        </div>
        <div className="relative min-h-0 flex-1 overflow-y-auto">
          {findingsQ.isLoading && <Loading label="Loading findings" />}
          {findingsQ.isError && <ErrorState title="Findings could not load" error={findingsQ.error} onRetry={() => findingsQ.refetch()} />}
          {findingsQ.data && important.length + minor.length === 0 && (
            <Empty
              title={findings.length === 0 ? (notRun ? "Not checked yet" : noneAnalysed ? "None of these files could be read" : "Nothing stood out") : "Nothing on this document"}
              action={
                notRun ? (
                  <Button asChild size="sm">
                    <Link to={`/cases/${caseId}`}>Go to overview</Link>
                  </Button>
                ) : undefined
              }
            >
              {findings.length === 0
                ? notRun
                  ? "Run the check to see findings here."
                  : noneAnalysed
                    ? "The overview says what went wrong with each file."
                    : "That doesn't prove the documents are genuine."
                : "Untick \"This document only\" to see the rest."}
            </Empty>
          )}
          {findingsQ.data && important.length === 0 && minor.length > 0 && (
            <p className="border-b border-line px-4 py-3 text-[14px] text-ink-2">Nothing here needs attention. A clean result doesn't prove the documents are genuine.</p>
          )}
          {important.map((f, i) => (
            <div key={f.id} className="rise" style={{ "--i": i } as React.CSSProperties}>
              {renderCard(f)}
            </div>
          ))}
          {minor.length > 0 && (
            <>
              <button
                type="button"
                aria-expanded={minorOpen}
                onClick={() => setShowMinor((v) => !v)}
                className="flex w-full cursor-pointer items-center gap-1.5 border-b border-line bg-raised px-4 py-2.5 text-left text-[14px] text-ink-2 hover:bg-hover"
              >
                <ChevronRight className={cn("size-4 shrink-0 text-ink-3 transition-transform duration-150", minorOpen && "rotate-90")} aria-hidden />
                {minor.length} minor observation{minor.length === 1 ? "" : "s"}
                <span className="text-ink-3">, usually nothing to worry about</span>
              </button>
              {minorOpen &&
                minor.map((f, i) => (
                  <div key={f.id} className="rise" style={{ "--i": i } as React.CSSProperties}>
                    {renderCard(f)}
                  </div>
                ))}
            </>
          )}
        </div>
      </aside>

      <Dialog open={!!compare} onOpenChange={(o) => !o && setCompare(null)}>
        {compare && (
          <DialogContent title="Side by side" description="The original regions from each document.">
            <div className="p-5">
              <ComparisonPanel caseId={caseId} finding={compare} docs={byId} fieldsById={fieldsById} label={labels.get(compare.id)} />
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}


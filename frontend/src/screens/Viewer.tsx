import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FileX, Link2 } from "lucide-react";
import { api } from "@/api";
import { useCase, useCaseDocuments, useFindings } from "@/api/hooks";
import type { BBox, Finding, FindingStatus } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { ComparisonPanel } from "@/components/ComparisonPanel";
import { DocCanvas } from "@/components/DocCanvas";
import { FindingCard } from "@/components/FindingCard";
import { ProcBadge, StatusBadge } from "@/components/StatusBadge";
import { STATUS_META, STATUS_ORDER, comparisonSources, findingLabels, regionsForPage, sortFindings } from "@/lib/findings";
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
  const docId = sp.get("doc") ?? firstViewable ?? null;
  const page = Number(sp.get("page") ?? 0) || 0;
  const selectedId = sp.get("finding");
  const fieldId = sp.get("field");
  const doc = docId ? byId.get(docId) : undefined;
  const selected = findings.find((f) => f.id === selectedId) ?? null;
  const field = fieldId ? fieldsById.get(fieldId) : undefined;

  const [statuses, setStatuses] = useState<Record<FindingStatus, boolean>>({
    OBSERVATION: true,
    INCONSISTENCY: true,
    POTENTIAL_MANIPULATION: true,
  });
  const [heatKind, setHeatKind] = useState<string | null>(null);
  const [heatOpacity, setHeatOpacity] = useState(70);
  const [showLinks, setShowLinks] = useState(true);
  const [onlyThisDoc, setOnlyThisDoc] = useState(false);
  const [focusNonce, setFocusNonce] = useState(0);
  const [compare, setCompare] = useState<Finding | null>(null);
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());

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

  const counts = useMemo(() => {
    const c: Record<FindingStatus, number> = { OBSERVATION: 0, INCONSISTENCY: 0, POTENTIAL_MANIPULATION: 0 };
    findings.forEach((f) => c[f.status]++);
    return c;
  }, [findings]);

  const listed = useMemo(
    () =>
      findings.filter((f) => {
        if (!statuses[f.status]) return false;
        if (onlyThisDoc && docId) {
          return f.doc_id === docId || f.related_doc_ids.includes(docId) || f.evidence.some((e) => e.doc_id === docId);
        }
        return true;
      }),
    [findings, statuses, onlyThisDoc, docId],
  );

  // Routine observations repeat; group them so the hypotheses and conflicts stay in view.
  const groups = useMemo(() => {
    const out: { key: string; items: Finding[] }[] = [];
    const seen = new Map<string, { key: string; items: Finding[] }>();
    for (const f of listed) {
      if (f.status !== "OBSERVATION") {
        out.push({ key: f.id, items: [f] });
        continue;
      }
      const key = `${f.detector}|${f.title}`;
      const g = seen.get(key);
      if (g) g.items.push(f);
      else {
        const n = { key, items: [f] };
        seen.set(key, n);
        out.push(n);
      }
    }
    return out;
  }, [listed]);

  const docCounts = useCallback(
    (id: string) =>
      findings.filter((f) => f.doc_id === id || f.evidence.some((e) => e.doc_id === id)).length,
    [findings],
  );

  if (caseQ.isLoading || docsLoading) return <Loading label="Loading documents and findings" className="h-full" />;
  if (docsError) return <ErrorState title="Documents could not load" error={docsError} />;
  if (summaries.length === 0) {
    return (
      <Empty
        title="No documents in this case"
        className="h-full"
        action={
          <Button asChild>
            <Link to={`/cases/${caseId}`}>Add documents</Link>
          </Button>
        }
      />
    );
  }
  const notRun = caseQ.data?.case.status !== "complete";

  return (
    <div className="grid h-full min-h-[560px] grid-rows-[minmax(0,58fr)_minmax(0,42fr)] lg:grid-cols-[minmax(0,1fr)_360px] lg:grid-rows-1 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="flex min-h-0 min-w-0 flex-col border-b border-line lg:border-b-0 lg:border-r">
        <div role="tablist" aria-label="Documents" className="flex shrink-0 overflow-x-auto border-b border-line bg-panel">
          {summaries.map((s) => {
            const active = s.id === docId;
            const n = docCounts(s.id);
            return (
              <button
                key={s.id}
                role="tab"
                aria-selected={active}
                type="button"
                onClick={() => update({ doc: s.id, page: "0", field: null })}
                className={cn(
                  "flex max-w-[210px] shrink-0 cursor-pointer flex-col gap-0.5 border-b-2 border-r border-r-line px-3 py-1.5 text-left hover:bg-hover",
                  active ? "border-b-ink bg-raised" : "border-b-transparent",
                )}
              >
                <span className="truncate font-mono text-xs text-ink">{s.filename}</span>
                <span className="flex items-center gap-1.5 text-[11px] text-ink-3">
                  {s.page_count === 0 ? <ProcBadge status={s.status} /> : <span className="truncate">{humanize(s.doc_type)}</span>}
                  {n > 0 && <span className="font-mono text-ink-2">{n} finding{n === 1 ? "" : "s"}</span>}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-panel px-3 py-1.5">
          {doc && doc.pages.length > 1 && (
            <div className="flex items-center gap-1">
              <Button size="icon" variant="ghost" aria-label="Previous page" disabled={page <= 0} onClick={() => update({ page: String(page - 1) })}>
                <ChevronLeft aria-hidden />
              </Button>
              <span className="font-mono text-xs text-ink-2">
                {page + 1}/{doc.pages.length}
              </span>
              <Button size="icon" variant="ghost" aria-label="Next page" disabled={page >= doc.pages.length - 1} onClick={() => update({ page: String(page + 1) })}>
                <ChevronRight aria-hidden />
              </Button>
            </div>
          )}
          <fieldset className="flex items-center gap-1.5">
            <legend className="sr-only">Forensic overlay</legend>
            <span className="eyebrow">Overlay</span>
            <div className="flex flex-wrap gap-1">
              <Chip active={!heatKind} onClick={() => setHeatKind(null)}>
                None
              </Chip>
              {overlays.data?.map((o) => (
                <Chip key={o.kind} active={heatKind === o.kind} onClick={() => setHeatKind(o.kind)}>
                  {o.label}
                </Chip>
              ))}
              {overlays.isError && <span className="text-xs text-ink-3">Overlays unavailable</span>}
              {overlays.data?.length === 0 && <span className="self-center text-xs text-ink-3">None generated for this page</span>}
            </div>
          </fieldset>
          {heatKind && <Slider value={heatOpacity} onChange={setHeatOpacity} label="Overlay opacity" />}
          {links.length > 0 && (
            <label className="flex items-center gap-1.5 text-xs text-ink-2">
              <Link2 className="size-3.5" aria-hidden />
              Copy-move links
              <Switch checked={showLinks} onCheckedChange={setShowLinks} label="Show copy-move links" />
            </label>
          )}
        </div>

        {doc && doc.pages.length > 0 ? (
          <DocCanvas
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
            <p className="font-medium">This document has no viewable pages</p>
            {doc && <ProcBadge status={doc.status} />}
            <p className="max-w-md text-ink-2">{doc?.status_message ?? "It was not rendered, and no analysis was run on it."}</p>
          </div>
        )}
      </div>

      <aside aria-label="Findings" className="flex min-h-0 flex-col bg-panel">
        <div className="shrink-0 border-b border-line p-2">
          <div className="grid grid-cols-3 gap-1">
            {STATUS_ORDER.map((s) => {
              const m = STATUS_META[s];
              const Icon = m.icon;
              const on = statuses[s];
              return (
                <button
                  key={s}
                  type="button"
                  aria-pressed={on}
                  title={m.meaning}
                  onClick={() => setStatuses((v) => ({ ...v, [s]: !v[s] }))}
                  className={cn(
                    "flex cursor-pointer flex-col gap-0.5 border px-2 py-1 text-left",
                    on ? cn(m.border, m.bg) : "border-line opacity-55 hover:opacity-100",
                  )}
                >
                  <span className={cn("flex items-center gap-1 font-mono text-[15px] font-medium", m.text)}>
                    <Icon className="size-3.5" aria-hidden />
                    {counts[s]}
                  </span>
                  <span className="text-[11px] leading-tight text-ink-2">{m.label}</span>
                </button>
              );
            })}
          </div>
          <label className="mt-2 flex items-center justify-between gap-2 px-0.5 text-xs text-ink-2">
            Only findings touching this document
            <Switch checked={onlyThisDoc} onCheckedChange={setOnlyThisDoc} label="Only findings touching this document" />
          </label>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {findingsQ.isLoading && <Loading label="Loading findings" />}
          {findingsQ.isError && <ErrorState title="Findings could not load" error={findingsQ.error} onRetry={() => findingsQ.refetch()} />}
          {findingsQ.data && listed.length === 0 && (
            <Empty
              title={findings.length === 0 ? (notRun ? "No findings yet" : "Nothing was flagged") : "No findings match these filters"}
              action={
                notRun ? (
                  <Button asChild size="sm">
                    <Link to={`/cases/${caseId}/pipeline`}>Go to pipeline</Link>
                  </Button>
                ) : undefined
              }
            >
              {findings.length === 0
                ? notRun
                  ? "Run the investigation to produce findings."
                  : "No detector raised a finding on these documents. That is not proof of authenticity."
                : "Adjust the status toggles above."}
            </Empty>
          )}
          {groups.map((g) => {
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
            if (g.items.length === 1) return renderCard(g.items[0]);
            const open = openGroups.has(g.key) || g.items.some((f) => f.id === selectedId);
            return (
              <div key={g.key}>
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() =>
                    setOpenGroups((prev) => {
                      const n = new Set(prev);
                      if (n.has(g.key)) n.delete(g.key);
                      else n.add(g.key);
                      return n;
                    })
                  }
                  className="flex w-full cursor-pointer items-center gap-2 border-b border-line px-3 py-2 text-left hover:bg-hover"
                >
                  <ChevronRight className={cn("size-3.5 shrink-0 text-ink-3 transition-transform", open && "rotate-90")} aria-hidden />
                  <StatusBadge status={g.items[0].status} compact />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-ink-2">{g.items[0].title}</span>
                  <span className="font-mono text-xs text-ink-3">{g.items.length}</span>
                </button>
                {open && <div className="border-l border-line-strong">{g.items.map(renderCard)}</div>}
              </div>
            );
          })}
        </div>
      </aside>

      <Dialog open={!!compare} onOpenChange={(o) => !o && setCompare(null)}>
        {compare && (
          <DialogContent title="Source comparison" description="Each source region shown side by side.">
            <div className="p-5">
              <ComparisonPanel caseId={caseId} finding={compare} docs={byId} fieldsById={fieldsById} label={labels.get(compare.id)} />
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "cursor-pointer border px-1.5 py-0.5 text-xs",
        active ? "border-ink bg-ink text-ground" : "border-line-strong text-ink-2 hover:bg-hover hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

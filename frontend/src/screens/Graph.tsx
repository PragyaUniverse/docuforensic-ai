import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { ArrowUpRight, FileText, Fingerprint, X } from "lucide-react";
import { api } from "@/api";
import { useCaseDocuments, useFindings } from "@/api/hooks";
import type { Entity, EvidenceGraph, Finding, FindingStatus, GraphEdge, GraphNode } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { ComparisonPanel } from "@/components/ComparisonPanel";
import { PageCrop } from "@/components/PageCrop";
import { StatusBadge } from "@/components/StatusBadge";
import { findingLabels } from "@/lib/findings";
import { cn, fmtBBox, humanize } from "@/lib/utils";

type NodeData = {
  label: string;
  sub?: string;
  conflict?: boolean;
  status?: FindingStatus;
  selected?: boolean;
  dim?: boolean;
};

const handleCls = "!h-1.5 !w-1.5 !min-h-0 !min-w-0 !rounded-none !border-0 !bg-line-strong";

function DocNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={cn("w-[210px] border bg-raised px-2.5 py-2 transition-opacity", data.selected ? "border-ink" : "border-line-strong", data.dim && "opacity-30")}>
      <Handle type="source" position={Position.Right} className={handleCls} />
      <Handle type="target" position={Position.Right} className={handleCls} />
      <div className="eyebrow flex items-center gap-1 !text-[10px]">
        <FileText className="size-3" aria-hidden /> {data.sub}
      </div>
      <div className="mt-0.5 truncate font-mono text-xs text-ink">{data.label}</div>
    </div>
  );
}

function EntityNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={cn("w-[230px] border bg-panel px-2.5 py-1.5 transition-opacity", data.conflict ? "border-man" : "border-line-strong", data.selected && "outline outline-1 outline-ink", data.dim && "opacity-30")}>
      <Handle type="target" position={Position.Left} className={handleCls} />
      <Handle type="source" position={Position.Right} className={handleCls} />
      <div className="eyebrow flex items-center justify-between !text-[10px]">
        <span className="flex items-center gap-1">
          <Fingerprint className="size-3" aria-hidden /> {data.sub}
        </span>
        {data.conflict && <span className="text-man">Conflict</span>}
      </div>
      <div className="mt-0.5 line-clamp-2 text-xs leading-snug text-ink">{data.label}</div>
    </div>
  );
}

function FindingNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={cn("w-[250px] border bg-panel px-2.5 py-1.5 transition-opacity", data.selected ? "border-ink" : "border-line-strong", data.dim && "opacity-30")}>
      <Handle type="target" position={Position.Left} className={handleCls} />
      <Handle type="source" position={Position.Left} className={handleCls} />
      <div className="flex items-center justify-between gap-2">
        {data.status && <StatusBadge status={data.status} compact />}
        <span className="font-mono text-[10px] text-ink-3">{data.sub}</span>
      </div>
      <div className="mt-1 line-clamp-2 text-xs leading-snug text-ink">{data.label}</div>
    </div>
  );
}

const nodeTypes = { document: DocNode, entity: EntityNode, finding: FindingNode };

const COL = { document: 0, entity: 300, finding: 620 } as const;
const ROW = { document: 92, entity: 74, finding: 84 } as const;

/** Layered layout: each column ordered by the mean position of its neighbours, to cut crossings. */
function layout(graph: EvidenceGraph) {
  const byKind = (k: string) => graph.nodes.filter((n) => n.kind === k);
  const adj = new Map<string, string[]>();
  graph.edges.forEach((e) => {
    adj.set(e.source, [...(adj.get(e.source) ?? []), e.target]);
    adj.set(e.target, [...(adj.get(e.target) ?? []), e.source]);
  });
  const y = new Map<string, number>();
  const place = (list: GraphNode[], gap: number) => {
    const scored = list.map((n, i) => {
      const ys = (adj.get(n.id) ?? []).map((id) => y.get(id)).filter((v): v is number => v !== undefined);
      return { n, s: ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : i * gap };
    });
    scored.sort((a, b) => a.s - b.s);
    scored.forEach((o, i) => y.set(o.n.id, i * gap));
  };
  const docs = byKind("document");
  const ents = byKind("entity");
  const finds = byKind("finding");
  place(docs, ROW.document);
  place(ents, ROW.entity);
  place(finds, ROW.finding);
  place(docs, ROW.document);
  const heights = [docs.length * ROW.document, ents.length * ROW.entity, finds.length * ROW.finding];
  const H = Math.max(...heights, 1);
  const off = (list: GraphNode[], gap: number) => (H - list.length * gap) / 2;
  const pos = new Map<string, { x: number; y: number }>();
  docs.forEach((n) => pos.set(n.id, { x: COL.document, y: y.get(n.id)! + off(docs, ROW.document) }));
  ents.forEach((n) => pos.set(n.id, { x: COL.entity, y: y.get(n.id)! + off(ents, ROW.entity) }));
  finds.forEach((n) => pos.set(n.id, { x: COL.finding, y: y.get(n.id)! + off(finds, ROW.finding) }));
  return pos;
}

type Selection = { type: "node"; node: GraphNode } | { type: "edge"; edge: GraphEdge } | null;

export default function GraphScreen() {
  const { caseId = "" } = useParams();
  const graphQ = useQuery({ queryKey: ["graph", caseId], queryFn: () => api.graph(caseId) });
  const entitiesQ = useQuery({ queryKey: ["entities", caseId], queryFn: () => api.entities(caseId) });
  const findingsQ = useFindings(caseId);
  const { byId, fieldsById } = useCaseDocuments(caseId);
  const [sel, setSel] = useState<Selection>(null);
  const [conflictsOnly, setConflictsOnly] = useState(false);
  const [showObs, setShowObs] = useState(false);

  const labels = useMemo(() => findingLabels(findingsQ.data ?? []), [findingsQ.data]);
  const findingsById = useMemo(() => new Map((findingsQ.data ?? []).map((f) => [f.id, f])), [findingsQ.data]);
  const entById = useMemo(() => new Map((entitiesQ.data ?? []).map((e) => [e.id, e])), [entitiesQ.data]);

  // Routine observations can outnumber everything else, so they start hidden.
  const visible = useMemo<EvidenceGraph | undefined>(() => {
    const g = graphQ.data;
    if (!g || showObs) return g;
    const isObs = (n: GraphNode) => n.kind === "finding" && (findingsById.get(n.ref_id)?.status ?? n.meta.status) === "OBSERVATION";
    const nodes = g.nodes.filter((n) => !isObs(n));
    const ids = new Set(nodes.map((n) => n.id));
    return { ...g, nodes, edges: g.edges.filter((e) => ids.has(e.source) && ids.has(e.target)) };
  }, [graphQ.data, showObs, findingsById]);
  const hiddenObs = (graphQ.data?.nodes.length ?? 0) - (visible?.nodes.length ?? 0);

  const selectedId = sel?.type === "node" ? sel.node.id : null;
  const selectedEdge = sel?.type === "edge" ? sel.edge.id : null;
  const neighbors = useMemo(() => {
    const g = visible;
    if (!g) return null;
    if (sel?.type === "node") {
      const s = new Set([sel.node.id]);
      g.edges.forEach((e) => {
        if (e.source === sel.node.id) s.add(e.target);
        if (e.target === sel.node.id) s.add(e.source);
      });
      return s;
    }
    if (sel?.type === "edge") return new Set([sel.edge.source, sel.edge.target]);
    return null;
  }, [visible, sel]);

  const { nodes, edges } = useMemo(() => {
    const g = visible;
    if (!g) return { nodes: [] as Node<NodeData>[], edges: [] as Edge[] };
    const pos = layout(g);
    const conflictNodes = new Set<string>();
    g.edges.filter((e) => e.conflict).forEach((e) => {
      conflictNodes.add(e.source);
      conflictNodes.add(e.target);
    });
    const nodes: Node<NodeData>[] = g.nodes.map((n) => {
      let data: NodeData = { label: n.label, selected: n.id === selectedId, dim: !!neighbors && !neighbors.has(n.id) };
      if (conflictsOnly && !conflictNodes.has(n.id)) data.dim = true;
      if (n.kind === "document") {
        const d = byId.get(n.ref_id);
        data = { ...data, label: d?.filename ?? n.label, sub: humanize(d?.doc_type ?? (n.meta.doc_type as string) ?? "document") };
      } else if (n.kind === "entity") {
        const e = entById.get(n.ref_id);
        data = { ...data, sub: humanize(e?.type ?? (n.meta.type as string) ?? "entity"), conflict: e?.conflict ?? !!n.meta.conflict };
      } else {
        const f = findingsById.get(n.ref_id);
        data = { ...data, label: f?.title ?? n.label, status: f?.status ?? (n.meta.status as FindingStatus), sub: labels.get(n.ref_id) ?? "" };
      }
      return {
        id: n.id,
        type: n.kind === "document" || n.kind === "entity" || n.kind === "finding" ? n.kind : "entity",
        position: pos.get(n.id) ?? { x: 0, y: 0 },
        data,
        draggable: true,
        connectable: false,
      };
    });
    const edges: Edge[] = g.edges.map((e) => {
      const on = e.id === selectedEdge || (!!neighbors && sel?.type === "node" && (e.source === selectedId || e.target === selectedId));
      const dim = (!!neighbors && !on) || (conflictsOnly && !e.conflict);
      const color = e.conflict ? "#ff5a4f" : on ? "#b4b9c1" : "#3a424e";
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.conflict ? (e.label ?? "conflict") : undefined,
        labelStyle: { fill: "#ff5a4f", fontFamily: "var(--font-mono)", fontSize: 10 },
        labelBgStyle: { fill: "#0a0c0f" },
        labelBgPadding: [4, 2] as [number, number],
        style: {
          stroke: color,
          strokeWidth: e.conflict ? (on ? 3 : 2) : 1,
          strokeDasharray: e.kind === "supports" ? "4 3" : undefined,
          opacity: dim ? 0.15 : 1,
        },
        markerEnd: e.conflict ? { type: MarkerType.ArrowClosed, color, width: 14, height: 14 } : undefined,
        interactionWidth: 18,
      };
    });
    return { nodes, edges };
  }, [visible, byId, entById, findingsById, labels, selectedId, selectedEdge, neighbors, sel, conflictsOnly]);

  const onNodeClick = useCallback(
    (_: unknown, n: Node) => {
      const g = graphQ.data?.nodes.find((x) => x.id === n.id);
      if (g) setSel({ type: "node", node: g });
    },
    [graphQ.data],
  );
  const onEdgeClick = useCallback(
    (_: unknown, e: Edge) => {
      const g = graphQ.data?.edges.find((x) => x.id === e.id);
      if (g) setSel({ type: "edge", edge: g });
    },
    [graphQ.data],
  );

  if (graphQ.isLoading) return <Loading label="Building evidence graph" className="h-full" />;
  if (graphQ.isError) return <ErrorState title="The evidence graph could not load" error={graphQ.error} onRetry={() => graphQ.refetch()} />;
  if (!graphQ.data || graphQ.data.nodes.length === 0) {
    return (
      <Empty
        title="No evidence graph yet"
        className="h-full"
        action={
          <Button asChild size="sm">
            <Link to={`/cases/${caseId}/pipeline`}>Go to pipeline</Link>
          </Button>
        }
      >
        The graph is built when the investigation runs.
      </Empty>
    );
  }
  const conflictCount = graphQ.data.edges.filter((e) => e.conflict).length;

  return (
    <div className={cn("grid h-full min-h-[560px]", sel ? "grid-rows-[minmax(0,1fr)_minmax(0,50%)] lg:grid-cols-[minmax(0,1fr)_400px] lg:grid-rows-1 xl:grid-cols-[minmax(0,1fr)_460px]" : "grid-cols-1")}>
      <div className="relative min-h-0">
        <div className="absolute left-3 top-3 z-10 flex flex-col gap-2 border border-line bg-panel p-2.5">
          <div className="eyebrow">Evidence graph</div>
          <div className="flex items-center gap-3 font-mono text-[11px] text-ink-2">
            <span className="flex items-center gap-1.5">
              <span aria-hidden className="block h-[2px] w-5 bg-man" /> conflict
            </span>
            <span className="flex items-center gap-1.5">
              <span aria-hidden className="block h-px w-5 bg-line-strong" /> agrees / mentions
            </span>
            <span className="flex items-center gap-1.5">
              <span aria-hidden className="block w-5 border-t border-dashed border-line-strong" /> supports
            </span>
          </div>
          <label className="flex items-center gap-1.5 text-xs text-ink-2">
            <input type="checkbox" checked={conflictsOnly} onChange={(e) => setConflictsOnly(e.target.checked)} className="accent-[#eceae4]" />
            Emphasize conflicts ({conflictCount})
          </label>
          <label className="flex items-center gap-1.5 text-xs text-ink-2">
            <input type="checkbox" checked={showObs} onChange={(e) => setShowObs(e.target.checked)} className="accent-[#eceae4]" />
            Show observations{!showObs && hiddenObs > 0 ? ` (${hiddenObs} hidden)` : ""}
          </label>
        </div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          colorMode="dark"
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.2}
          maxZoom={1.6}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={() => setSel(null)}
          proOptions={{ hideAttribution: true }}
          style={{ background: "transparent" }}
          aria-label="Evidence graph of documents, entities and findings"
        >
          <Background color="#1c2128" gap={18} size={1} />
          <Controls showInteractive={false} position="bottom-left" />
        </ReactFlow>
      </div>
      {sel && (
        <aside aria-label="Selection details" className="flex min-h-0 flex-col overflow-y-auto border-t border-line bg-panel lg:border-l lg:border-t-0">
          <div className="flex items-center justify-between border-b border-line px-4 py-2">
            <span className="eyebrow">{sel.type === "edge" ? (sel.edge.conflict ? "Conflict edge" : "Relationship") : humanize(sel.node.kind)}</span>
            <button type="button" aria-label="Close details" onClick={() => setSel(null)} className="cursor-pointer rounded-sm p-1 text-ink-3 hover:bg-hover hover:text-ink">
              <X className="size-4" />
            </button>
          </div>
          <div className="p-4">
            <SelectionDetail
              caseId={caseId}
              sel={sel}
              graph={graphQ.data}
              findingsById={findingsById}
              entById={entById}
              labels={labels}
              docs={byId}
              fieldsById={fieldsById}
            />
          </div>
        </aside>
      )}
    </div>
  );
}

function EntityDetail({ caseId, e, docs }: { caseId: string; e: Entity; docs: ReturnType<typeof useCaseDocuments>["byId"] }) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className="eyebrow">{humanize(e.type)}</div>
        <div className="display mt-0.5 text-[15px]">{e.canonical_value}</div>
        {e.conflict && <div className="mt-1 text-[13px] text-man">The mentions of this entity disagree.</div>}
      </div>
      <ul className="flex flex-col gap-2">
        {e.mentions.map((m) => {
          const d = docs.get(m.doc_id);
          return (
            <li key={m.field_id} className="border border-line bg-raised">
              <div className="flex items-center justify-between gap-2 px-2 py-1.5">
                <span className="truncate font-mono text-[11px] text-ink-2">{d?.filename ?? m.doc_id}</span>
                <Link
                  to={{ pathname: `/cases/${caseId}/viewer`, search: new URLSearchParams({ doc: m.doc_id, page: String(m.page), field: m.field_id }).toString() }}
                  className="flex shrink-0 items-center gap-0.5 text-xs text-ink-2 hover:text-ink hover:underline"
                >
                  Open <ArrowUpRight className="size-3" aria-hidden />
                </Link>
              </div>
              <div className="px-2 pb-1.5 font-mono text-[13px]">{m.value_raw}</div>
              <PageCrop caseId={caseId} doc={d} page={m.page} bbox={m.bbox} className="max-h-28" />
              <div className="px-2 py-1 font-mono text-[10.5px] text-ink-3">
                p{m.page + 1} {fmtBBox(m.bbox)}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function FindingDetail({ caseId, f, label, docs, fieldsById }: { caseId: string; f: Finding; label?: string; docs: ReturnType<typeof useCaseDocuments>["byId"]; fieldsById: ReturnType<typeof useCaseDocuments>["fieldsById"] }) {
  const q = new URLSearchParams({ finding: f.id });
  if (f.doc_id) q.set("doc", f.doc_id);
  if (f.page !== null) q.set("page", String(f.page));
  return (
    <div className="flex flex-col gap-3">
      <ComparisonPanel caseId={caseId} finding={f} docs={docs} fieldsById={fieldsById} label={label} compact />
      <Button asChild size="sm" className="self-start">
        <Link to={{ pathname: `/cases/${caseId}/viewer`, search: q.toString() }}>
          Open finding in viewer <ArrowUpRight aria-hidden />
        </Link>
      </Button>
    </div>
  );
}

function SelectionDetail({
  caseId,
  sel,
  graph,
  findingsById,
  entById,
  labels,
  docs,
  fieldsById,
}: {
  caseId: string;
  sel: NonNullable<Selection>;
  graph: EvidenceGraph;
  findingsById: Map<string, Finding>;
  entById: Map<string, Entity>;
  labels: Map<string, string>;
  docs: ReturnType<typeof useCaseDocuments>["byId"];
  fieldsById: ReturnType<typeof useCaseDocuments>["fieldsById"];
}) {
  if (sel.type === "edge") {
    const e = sel.edge;
    const f = e.finding_id ? findingsById.get(e.finding_id) : undefined;
    if (f) return <FindingDetail caseId={caseId} f={f} label={labels.get(f.id)} docs={docs} fieldsById={fieldsById} />;
    const src = graph.nodes.find((n) => n.id === e.source);
    const dst = graph.nodes.find((n) => n.id === e.target);
    const ent = [src, dst].find((n) => n?.kind === "entity");
    const entity = ent ? entById.get(ent.ref_id) : undefined;
    return (
      <div className="flex flex-col gap-3">
        <p className="font-mono text-xs text-ink-2">
          {src?.label} → {e.kind} → {dst?.label}
        </p>
        {entity && <EntityDetail caseId={caseId} e={entity} docs={docs} />}
      </div>
    );
  }
  const n = sel.node;
  if (n.kind === "finding") {
    const f = findingsById.get(n.ref_id);
    return f ? <FindingDetail caseId={caseId} f={f} label={labels.get(f.id)} docs={docs} fieldsById={fieldsById} /> : <p className="text-ink-3">Finding details unavailable.</p>;
  }
  if (n.kind === "entity") {
    const e = entById.get(n.ref_id);
    return e ? <EntityDetail caseId={caseId} e={e} docs={docs} /> : <p className="text-ink-3">Entity details unavailable.</p>;
  }
  const d = docs.get(n.ref_id);
  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className="eyebrow">{humanize(d?.doc_type ?? "document")}</div>
        <div className="mt-0.5 break-all font-mono text-[13px]">{d?.filename ?? n.label}</div>
      </div>
      {d && d.pages.length > 0 && (
        <PageCrop caseId={caseId} doc={d} page={0} bbox={{ x0: 0, y0: 0, x1: d.pages[0].width, y1: d.pages[0].height }} pad={0} stroke="transparent" className="max-h-96" />
      )}
      <Button asChild size="sm" className="self-start">
        <Link to={{ pathname: `/cases/${caseId}/viewer`, search: new URLSearchParams({ doc: n.ref_id, page: "0" }).toString() }}>
          Open document <ArrowUpRight aria-hidden />
        </Link>
      </Button>
    </div>
  );
}

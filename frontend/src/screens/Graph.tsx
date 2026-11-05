import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useInternalNode,
  type Edge,
  type EdgeProps,
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
import { findingLabels, sortFindings } from "@/lib/findings";
import { cn, fmtBBox, humanize } from "@/lib/utils";
import { useTheme } from "@/lib/theme";

type NodeData = {
  label: string;
  sub?: string;
  conflict?: boolean;
  count?: number;
  status?: FindingStatus;
  selected?: boolean;
  dim?: boolean;
};

const handleCls = "!h-1.5 !w-1.5 !min-h-0 !min-w-0 !rounded-none !border-0 !bg-line-strong";
const hiddenHandle = "!h-px !w-px !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0";

function DocNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={cn("w-[210px] border bg-raised px-2.5 py-2 transition-opacity", data.selected ? "border-ink" : "border-line-strong", data.dim && "opacity-30")}>
      <Handle type="source" position={Position.Right} className={handleCls} />
      <Handle type="target" position={Position.Right} className={handleCls} />
      <div className="eyebrow flex items-center justify-between gap-1 !text-[13px]">
        <span className="flex items-center gap-1 truncate">
          <FileText className="size-3 shrink-0" aria-hidden /> {data.sub}
        </span>
        {!!data.count && <span className="shrink-0 text-man">{data.count} conflict{data.count === 1 ? "" : "s"}</span>}
      </div>
      <div className="mt-0.5 truncate font-mono text-[13px] text-ink">{data.label}</div>
    </div>
  );
}

/** Document as a point on the ring. Edges attach to the centre through a floating edge. */
function RingNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={cn("w-[190px] cursor-pointer border bg-raised px-2.5 py-2 transition-opacity", data.selected ? "border-ink" : data.count ? "border-man" : "border-line-strong", data.dim && "opacity-30")}>
      <Handle type="source" position={Position.Top} className={hiddenHandle} />
      <Handle type="target" position={Position.Top} className={hiddenHandle} />
      <div className="eyebrow flex items-center gap-1 truncate !text-[13px]">
        <FileText className="size-3 shrink-0" aria-hidden /> {data.sub}
      </div>
      <div className="mt-0.5 truncate font-mono text-[13px] text-ink">{data.label}</div>
      <div className={cn("mt-1 font-mono text-[13px]", data.count ? "text-man" : "text-ink-3")}>
        {data.count ? `${data.count} conflict${data.count === 1 ? "" : "s"}` : "no conflicts"}
      </div>
    </div>
  );
}

function EntityNode({ data }: NodeProps<Node<NodeData>>) {
  return (
    <div className={cn("w-[230px] border bg-panel px-2.5 py-1.5 transition-opacity", data.conflict ? "border-man" : "border-line-strong", data.selected && "outline outline-1 outline-ink", data.dim && "opacity-30")}>
      <Handle type="target" position={Position.Left} className={handleCls} />
      <Handle type="source" position={Position.Right} className={handleCls} />
      <Handle id="t" type="target" position={Position.Top} className={hiddenHandle} />
      <Handle id="b" type="source" position={Position.Bottom} className={hiddenHandle} />
      <div className="eyebrow flex items-center justify-between !text-[13px]">
        <span className="flex items-center gap-1">
          <Fingerprint className="size-3" aria-hidden /> {data.sub}
        </span>
        {data.conflict && <span className="text-man">Conflict</span>}
      </div>
      <div className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-ink">{data.label}</div>
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
        <span className="font-mono text-[13px] text-ink-3">{data.sub}</span>
      </div>
      <div className="mt-1 line-clamp-2 text-[13px] leading-snug text-ink">{data.label}</div>
    </div>
  );
}

function centerOf(n: ReturnType<typeof useInternalNode>) {
  if (!n) return null;
  const w = n.measured.width ?? 190;
  const h = n.measured.height ?? 70;
  return { x: n.internals.positionAbsolute.x + w / 2, y: n.internals.positionAbsolute.y + h / 2 };
}

/** Straight line between node centres, with its label kept at a slight offset to reduce overlaps. */
function FloatingEdge({ id, source, target, label, style, data, selected }: EdgeProps<Edge<{ dim?: boolean; on?: boolean; labelAt?: number }>>) {
  const a = centerOf(useInternalNode(source));
  const b = centerOf(useInternalNode(target));
  if (!a || !b) return null;
  const t = data?.labelAt ?? 0.5;
  const lx = a.x + (b.x - a.x) * t;
  const ly = a.y + (b.y - a.y) * t;
  return (
    <>
      <BaseEdge id={id} path={`M${a.x},${a.y} L${b.x},${b.y}`} style={style} interactionWidth={22} />
      {label && !data?.dim && (
        <EdgeLabelRenderer>
          <div
            style={{ transform: `translate(-50%,-50%) translate(${lx}px,${ly}px)` }}
            className={cn(
              "nodrag nopan pointer-events-none absolute border bg-ground px-1 py-px font-mono text-[13px]",
              data?.on || selected ? "border-man text-man" : "border-transparent text-man",
            )}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const nodeTypes = { document: DocNode, ring: RingNode, entity: EntityNode, finding: FindingNode };
const edgeTypes = { floating: FloatingEdge };

const COL = { document: 0, entity: 300, finding: 620 } as const;
const ROW = { document: 92, entity: 74, finding: 84 } as const;
const TYPE_ORDER = ["person", "date_of_birth", "address", "employer", "id_number", "account_number", "amount"];

/** Layered layout. Entities of one type stay adjacent, so conflicting values sit next to each other. */
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
  const rank = (n: GraphNode) => {
    const i = TYPE_ORDER.indexOf(String(n.meta.type));
    return i < 0 ? TYPE_ORDER.length : i;
  };
  const ents = [...byKind("entity")].sort((a, b) => rank(a) - rank(b));
  ents.forEach((n, i) => y.set(n.id, i * ROW.entity));
  const finds = byKind("finding");
  place(finds, ROW.finding);
  place(docs, ROW.document);
  const H = Math.max(docs.length * ROW.document, ents.length * ROW.entity, finds.length * ROW.finding, 1);
  const off = (list: GraphNode[], gap: number) => (H - list.length * gap) / 2;
  const pos = new Map<string, { x: number; y: number }>();
  docs.forEach((n) => pos.set(n.id, { x: COL.document, y: y.get(n.id)! + off(docs, ROW.document) }));
  ents.forEach((n) => pos.set(n.id, { x: COL.entity, y: y.get(n.id)! + off(ents, ROW.entity) }));
  finds.forEach((n) => pos.set(n.id, { x: COL.finding, y: y.get(n.id)! + off(finds, ROW.finding) }));
  return pos;
}

type View = "documents" | "evidence";
type PairEdge = { id: string; a: string; b: string; findingIds: string[]; types: string[]; conflict: boolean };
type Selection =
  | { type: "node"; node: GraphNode }
  | { type: "edge"; edge: GraphEdge }
  | { type: "pair"; pair: PairEdge }
  | null;

/** Collapses document-to-document edges to one per pair, listing the findings behind it. */
function documentPairs(g: EvidenceGraph): PairEdge[] {
  const kinds = new Map(g.nodes.map((n) => [n.id, n.kind]));
  const pairs = new Map<string, PairEdge>();
  for (const e of g.edges) {
    if (kinds.get(e.source) !== "document" || kinds.get(e.target) !== "document") continue;
    if (e.kind !== "conflicts" && e.kind !== "agrees") continue;
    const [a, b] = [e.source, e.target].sort();
    const id = `${a}|${b}`;
    const p = pairs.get(id) ?? { id, a, b, findingIds: [], types: [], conflict: false };
    if (e.conflict) {
      p.conflict = true;
      if (e.finding_id && !p.findingIds.includes(e.finding_id)) p.findingIds.push(e.finding_id);
      if (e.label && !p.types.includes(e.label)) p.types.push(e.label);
    }
    pairs.set(id, p);
  }
  return [...pairs.values()];
}

export default function GraphScreen() {
  const { caseId = "" } = useParams();
  const graphQ = useQuery({ queryKey: ["graph", caseId], queryFn: () => api.graph(caseId) });
  const entitiesQ = useQuery({ queryKey: ["entities", caseId], queryFn: () => api.entities(caseId) });
  const findingsQ = useFindings(caseId);
  const { byId, fieldsById } = useCaseDocuments(caseId);
  const theme = useTheme();
  const [view, setView] = useState<View>("documents");
  const [sel, setSel] = useState<Selection>(null);
  const [showObs, setShowObs] = useState(false);

  const labels = useMemo(() => findingLabels(findingsQ.data ?? []), [findingsQ.data]);
  const findingsById = useMemo(() => new Map((findingsQ.data ?? []).map((f) => [f.id, f])), [findingsQ.data]);
  const entById = useMemo(() => new Map((entitiesQ.data ?? []).map((e) => [e.id, e])), [entitiesQ.data]);
  const pairs = useMemo(() => (graphQ.data ? documentPairs(graphQ.data) : []), [graphQ.data]);
  const conflictPairs = pairs.filter((p) => p.conflict).length;

  // Evidence view: routine observations and bookkeeping edges would hide the structure, so they start hidden.
  const evidence = useMemo<EvidenceGraph | undefined>(() => {
    const g = graphQ.data;
    if (!g) return g;
    const isObs = (n: GraphNode) => n.kind === "finding" && (findingsById.get(n.ref_id)?.status ?? n.meta.status) === "OBSERVATION";
    const nodes = showObs ? g.nodes : g.nodes.filter((n) => !isObs(n));
    const ids = new Set(nodes.map((n) => n.id));
    const kinds = new Map(nodes.map((n) => [n.id, n.kind]));
    const linkedToEntity = new Set(
      g.edges.filter((e) => kinds.get(e.source) === "finding" && kinds.get(e.target) === "entity").map((e) => e.source),
    );
    const edges = g.edges.filter((e) => {
      if (!ids.has(e.source) || !ids.has(e.target)) return false;
      const s = kinds.get(e.source);
      const t = kinds.get(e.target);
      if (s === "document" && t === "document") return false;
      if (s === "finding" && t === "finding") return false;
      if (s === "finding" && t === "document") return !linkedToEntity.has(e.source);
      return true;
    });
    return { ...g, nodes, edges };
  }, [graphQ.data, showObs, findingsById]);
  const hiddenObs = (graphQ.data?.nodes.length ?? 0) - (evidence?.nodes.length ?? 0);

  const { nodes, edges } = useMemo(() => {
    const g = graphQ.data;
    if (!g) return { nodes: [] as Node<NodeData>[], edges: [] as Edge[] };

    if (view === "documents") {
      const docs = g.nodes.filter((n) => n.kind === "document" && (byId.get(n.ref_id)?.pages.length ?? 1) > 0);
      const R = Math.max(240, docs.length * 62);
      const selNode = sel?.type === "node" ? sel.node.id : null;
      const selPair = sel?.type === "pair" ? sel.pair : null;
      const counts = new Map<string, number>();
      pairs.filter((p) => p.conflict).forEach((p) => {
        counts.set(p.a, (counts.get(p.a) ?? 0) + p.findingIds.length);
        counts.set(p.b, (counts.get(p.b) ?? 0) + p.findingIds.length);
      });
      const nodes: Node<NodeData>[] = docs.map((n, i) => {
        const angle = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, docs.length);
        const d = byId.get(n.ref_id);
        return {
          id: n.id,
          type: "ring",
          position: { x: Math.cos(angle) * R * 1.35 - 95, y: Math.sin(angle) * R - 35 },
          data: {
            label: d?.filename ?? n.label,
            sub: humanize(d?.doc_type ?? (n.meta.doc_type as string) ?? "document"),
            count: counts.get(n.id) ?? 0,
            selected: n.id === selNode,
            dim: !!selPair && n.id !== selPair.a && n.id !== selPair.b,
          },
          connectable: false,
        };
      });
      const ids = new Set(docs.map((n) => n.id));
      const edges: Edge[] = pairs
        .filter((p) => ids.has(p.a) && ids.has(p.b))
        .map((p, i) => {
          const on = selPair?.id === p.id || (!!selNode && (p.a === selNode || p.b === selNode));
          const dim = (!!selPair || !!selNode) && !on;
          const label = p.conflict ? (p.types.length > 2 ? `${p.types.length} conflicts` : p.types.map(humanize).join(", ")) : undefined;
          return {
            id: p.id,
            source: p.a,
            target: p.b,
            type: "floating",
            label,
            data: { dim, on, labelAt: 0.38 + (i % 3) * 0.12 },
            style: {
              stroke: p.conflict ? "var(--color-man)" : "var(--color-line-strong)",
              strokeWidth: p.conflict ? Math.min(1.5 + p.findingIds.length * 0.75, 4) : 1,
              strokeDasharray: p.conflict ? undefined : "2 4",
              opacity: dim ? 0.12 : 1,
            },
          };
        });
      return { nodes, edges };
    }

    const e = evidence!;
    const selectedId = sel?.type === "node" ? sel.node.id : null;
    const selectedEdge = sel?.type === "edge" ? sel.edge.id : null;
    let neighbors: Set<string> | null = null;
    if (sel?.type === "node") {
      neighbors = new Set([sel.node.id]);
      e.edges.forEach((x) => {
        if (x.source === sel.node.id) neighbors!.add(x.target);
        if (x.target === sel.node.id) neighbors!.add(x.source);
      });
    } else if (sel?.type === "edge") {
      neighbors = new Set([sel.edge.source, sel.edge.target]);
    }
    const pos = layout(e);
    const nodes: Node<NodeData>[] = e.nodes.map((n) => {
      let data: NodeData = { label: n.label, selected: n.id === selectedId, dim: !!neighbors && !neighbors.has(n.id) };
      if (n.kind === "document") {
        const d = byId.get(n.ref_id);
        data = { ...data, label: d?.filename ?? n.label, sub: humanize(d?.doc_type ?? (n.meta.doc_type as string) ?? "document") };
      } else if (n.kind === "entity") {
        const en = entById.get(n.ref_id);
        data = { ...data, sub: humanize(en?.type ?? (n.meta.type as string) ?? "entity"), conflict: en?.conflict ?? !!n.meta.conflict };
      } else {
        const f = findingsById.get(n.ref_id);
        data = { ...data, label: f?.title ?? n.label, status: f?.status ?? (n.meta.status as FindingStatus), sub: labels.get(n.ref_id) ?? "" };
      }
      return {
        id: n.id,
        type: n.kind === "document" || n.kind === "entity" || n.kind === "finding" ? n.kind : "entity",
        position: pos.get(n.id) ?? { x: 0, y: 0 },
        data,
        connectable: false,
      };
    });
    const kinds = new Map(e.nodes.map((n) => [n.id, n.kind]));
    const edges: Edge[] = e.edges.map((x) => {
      const on = x.id === selectedEdge || (!!selectedId && (x.source === selectedId || x.target === selectedId));
      const dim = !!neighbors && !on;
      const color = x.conflict ? "var(--color-man)" : on ? "var(--color-ink-3)" : "var(--color-line-strong)";
      const entityPair = kinds.get(x.source) === "entity" && kinds.get(x.target) === "entity";
      // Same-column entity links run vertically, top to bottom, between adjacent values.
      const swap = entityPair && (pos.get(x.source)?.y ?? 0) > (pos.get(x.target)?.y ?? 0);
      return {
        id: x.id,
        source: swap ? x.target : x.source,
        target: swap ? x.source : x.target,
        sourceHandle: entityPair ? "b" : undefined,
        targetHandle: entityPair ? "t" : undefined,
        label: x.conflict && on ? humanize(x.label ?? "conflict") : undefined,
        labelStyle: { fill: "var(--color-man)", fontFamily: "var(--font-mono)", fontSize: 10 },
        labelBgStyle: { fill: "var(--color-panel)" },
        labelBgPadding: [4, 2] as [number, number],
        style: {
          stroke: color,
          strokeWidth: x.conflict ? (on ? 3 : 2) : 1,
          strokeDasharray: x.kind === "supports" ? "4 3" : undefined,
          opacity: dim ? 0.12 : 1,
        },
        markerEnd: x.conflict && !entityPair ? { type: MarkerType.ArrowClosed, color, width: 14, height: 14 } : undefined,
        interactionWidth: 18,
      };
    });
    return { nodes, edges };
  }, [graphQ.data, evidence, view, pairs, byId, entById, findingsById, labels, sel]);

  const onNodeClick = useCallback(
    (_: unknown, n: Node) => {
      const g = graphQ.data?.nodes.find((x) => x.id === n.id);
      if (g) setSel({ type: "node", node: g });
    },
    [graphQ.data],
  );
  const onEdgeClick = useCallback(
    (_: unknown, e: Edge) => {
      if (view === "documents") {
        const p = pairs.find((x) => x.id === e.id);
        if (p) setSel({ type: "pair", pair: p });
        return;
      }
      const g = graphQ.data?.edges.find((x) => x.id === e.id);
      if (g) setSel({ type: "edge", edge: g });
    },
    [graphQ.data, pairs, view],
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

  return (
    <div className={cn("grid h-full min-h-[560px]", sel ? "grid-rows-[minmax(0,1fr)_minmax(0,50%)] lg:grid-cols-[minmax(0,1fr)_400px] lg:grid-rows-1 xl:grid-cols-[minmax(0,1fr)_460px]" : "grid-cols-1")}>
      <div className="relative min-h-0">
        <div className="absolute left-3 top-3 z-10 flex flex-col gap-2 card p-2.5">
          <Link className="link text-[14px]" to={`/cases/${caseId}/conflicts`}>
            Back to the list
          </Link>
          <div className="flex gap-1" role="group" aria-label="Graph view">
            {(
              [
                ["documents", "By document"],
                ["evidence", "Everything"],
              ] as [View, string][]
            ).map(([v, l]) => (
              <button
                key={v}
                type="button"
                aria-pressed={view === v}
                onClick={() => {
                  setView(v);
                  setSel(null);
                }}
                className={cn("cursor-pointer border px-1.5 py-0.5 text-[13px]", view === v ? "border-accent bg-accent text-white" : "border-line-strong text-ink-2 hover:bg-hover hover:text-ink")}
              >
                {l}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[13px] text-ink-2">
            <span className="flex items-center gap-1.5">
              <span aria-hidden className="block h-[2px] w-5 bg-man" /> conflict
            </span>
            {view === "documents" ? (
              <span className="flex items-center gap-1.5">
                <span aria-hidden className="block w-5 border-t border-dotted border-line-strong" /> agree
              </span>
            ) : (
              <>
                <span className="flex items-center gap-1.5">
                  <span aria-hidden className="block h-px w-5 bg-line-strong" /> mentions
                </span>
                <span className="flex items-center gap-1.5">
                  <span aria-hidden className="block w-5 border-t border-dashed border-line-strong" /> supports
                </span>
              </>
            )}
          </div>
          {view === "documents" ? (
            <p className="max-w-64 text-[13px] text-ink-3">
              {conflictPairs} document pair{conflictPairs === 1 ? "" : "s"} in conflict. Click a red line to see the source values.
            </p>
          ) : (
            <label className="flex items-center gap-1.5 text-[13px] text-ink-2">
              <input type="checkbox" checked={showObs} onChange={(e) => setShowObs(e.target.checked)} className="accent-[#20242a]" />
              Show observations{!showObs && hiddenObs > 0 ? ` (${hiddenObs} hidden)` : ""}
            </label>
          )}
        </div>
        <ReactFlow
          key={`${view}-${showObs}`}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          colorMode={theme}
          fitView
          fitViewOptions={{ padding: 0.14 }}
          minZoom={0.15}
          maxZoom={1.6}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={() => setSel(null)}
          proOptions={{ hideAttribution: true }}
          style={{ background: "transparent" }}
          aria-label="Evidence graph of documents, entities and findings"
        >
          <Background color="var(--color-line)" gap={18} size={1} />
          <Controls showInteractive={false} position="bottom-left" />
        </ReactFlow>
      </div>
      {sel && (
        <aside aria-label="Selection details" className="flex min-h-0 flex-col overflow-y-auto border-t border-line bg-panel lg:border-l lg:border-t-0">
          <div className="flex items-center justify-between border-b border-line px-4 py-2">
            <span className="eyebrow">
              {sel.type === "pair" ? (sel.pair.conflict ? "Conflict between documents" : "Documents agree") : sel.type === "edge" ? (sel.edge.conflict ? "Conflict edge" : "Relationship") : humanize(sel.node.kind)}
            </span>
            <button type="button" aria-label="Close details" onClick={() => setSel(null)} className="cursor-pointer rounded-sm p-1 text-ink-3 hover:bg-hover hover:text-ink">
              <X className="size-4" />
            </button>
          </div>
          <div className="p-4">
            <SelectionDetail
              caseId={caseId}
              sel={sel}
              graph={graphQ.data}
              pairs={pairs}
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

type Docs = ReturnType<typeof useCaseDocuments>["byId"];
type Fields = ReturnType<typeof useCaseDocuments>["fieldsById"];

function EntityDetail({ caseId, e, docs }: { caseId: string; e: Entity; docs: Docs }) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className="eyebrow">{humanize(e.type)}</div>
        <div className="display mt-0.5 text-[15px]">{e.canonical_value}</div>
        {e.conflict && <div className="mt-1 text-[13px] text-man">The mentions of this entity disagree with another value in the case.</div>}
      </div>
      <ul className="flex flex-col gap-2">
        {e.mentions.map((m) => {
          const d = docs.get(m.doc_id);
          return (
            <li key={m.field_id} className="border border-line bg-raised">
              <div className="flex items-center justify-between gap-2 px-2 py-1.5">
                <span className="truncate font-mono text-[13px] text-ink-2">{d?.filename ?? m.doc_id}</span>
                <Link
                  to={{ pathname: `/cases/${caseId}/viewer`, search: new URLSearchParams({ doc: m.doc_id, page: String(m.page), field: m.field_id }).toString() }}
                  className="flex shrink-0 items-center gap-0.5 text-[13px] text-ink-2 hover:text-ink hover:underline"
                >
                  Open <ArrowUpRight className="size-3" aria-hidden />
                </Link>
              </div>
              <div className="px-2 pb-1.5 font-mono text-[13px]">{m.value_raw}</div>
              <PageCrop caseId={caseId} doc={d} page={m.page} bbox={m.bbox} className="max-h-28" />
              <div className="px-2 py-1 font-mono text-[13px] text-ink-3">
                p{m.page + 1} {fmtBBox(m.bbox)}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function FindingDetail({ caseId, f, label, docs, fieldsById }: { caseId: string; f: Finding; label?: string; docs: Docs; fieldsById: Fields }) {
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

function FindingList({ caseId, ids, findingsById, labels, docs, fieldsById }: { caseId: string; ids: string[]; findingsById: Map<string, Finding>; labels: Map<string, string>; docs: Docs; fieldsById: Fields }) {
  const list = sortFindings(ids.map((id) => findingsById.get(id)).filter(Boolean) as Finding[]);
  if (list.length === 0) return <p className="text-ink-3">No conflicting findings between these documents.</p>;
  return (
    <div className="flex flex-col gap-6 divide-y divide-line">
      {list.map((f, i) => (
        <div key={f.id} className={i > 0 ? "pt-6" : ""}>
          <FindingDetail caseId={caseId} f={f} label={labels.get(f.id)} docs={docs} fieldsById={fieldsById} />
        </div>
      ))}
    </div>
  );
}

function SelectionDetail({
  caseId,
  sel,
  graph,
  pairs,
  findingsById,
  entById,
  labels,
  docs,
  fieldsById,
}: {
  caseId: string;
  sel: NonNullable<Selection>;
  graph: EvidenceGraph;
  pairs: PairEdge[];
  findingsById: Map<string, Finding>;
  entById: Map<string, Entity>;
  labels: Map<string, string>;
  docs: Docs;
  fieldsById: Fields;
}) {
  if (sel.type === "pair") {
    const p = sel.pair;
    const nameOf = (id: string) => docs.get(graph.nodes.find((n) => n.id === id)?.ref_id ?? "")?.filename ?? id;
    return (
      <div className="flex flex-col gap-3">
        <p className="font-mono text-[13px] text-ink-2">
          {nameOf(p.a)} ↔ {nameOf(p.b)}
        </p>
        {p.conflict ? (
          <FindingList caseId={caseId} ids={p.findingIds} findingsById={findingsById} labels={labels} docs={docs} fieldsById={fieldsById} />
        ) : (
          <p className="text-ink-2">The compared values on these two documents agree. Agreement does not prove either document is authentic.</p>
        )}
      </div>
    );
  }
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
        <p className="font-mono text-[13px] text-ink-2">
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
  const conflicts = [...new Set(pairs.filter((p) => p.conflict && (p.a === n.id || p.b === n.id)).flatMap((p) => p.findingIds))];
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="eyebrow">{humanize(d?.doc_type ?? "document")}</div>
          <div className="mt-0.5 break-all font-mono text-[13px]">{d?.filename ?? n.label}</div>
        </div>
        <Button asChild size="sm" className="shrink-0">
          <Link to={{ pathname: `/cases/${caseId}/viewer`, search: new URLSearchParams({ doc: n.ref_id, page: "0" }).toString() }}>
            Open <ArrowUpRight aria-hidden />
          </Link>
        </Button>
      </div>
      {conflicts.length > 0 ? (
        <FindingList caseId={caseId} ids={conflicts} findingsById={findingsById} labels={labels} docs={docs} fieldsById={fieldsById} />
      ) : (
        d &&
        d.pages.length > 0 && <PageCrop caseId={caseId} doc={d} page={0} bbox={{ x0: 0, y0: 0, x1: d.pages[0].width, y1: d.pages[0].height }} pad={0} stroke="transparent" className="max-h-96" />
      )}
    </div>
  );
}

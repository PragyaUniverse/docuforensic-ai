import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ImageOff, Loader2, Maximize, Minus, Plus } from "lucide-react";
import { api } from "@/api";
import type { BBox, Document } from "@/api/types";
import { STATUS_META, type Region } from "@/lib/findings";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

export interface CanvasHighlight {
  bbox: BBox;
  label: string;
}

interface Props {
  caseId: string;
  doc: Document;
  page: number;
  regions?: Region[];
  labels?: Map<string, string>;
  selectedFindingId?: string | null;
  onSelectFinding?: (id: string) => void;
  highlight?: CanvasHighlight | null;
  heatmap?: { url: string; opacity: number } | null;
  links?: Array<[BBox, BBox]>;
  focus?: BBox | null;
  focusKey?: string | number | null;
  className?: string;
}

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

export function DocCanvas({
  caseId,
  doc,
  page,
  regions = [],
  labels,
  selectedFindingId,
  onSelectFinding,
  highlight,
  heatmap,
  links = [],
  focus,
  focusKey,
  className,
}: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const p = doc.pages[page];
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [view, setView] = useState({ s: 0.3, x: 0, y: 0 });
  const [animate, setAnimate] = useState(false);
  const [imgState, setImgState] = useState<"loading" | "ok" | "error">("loading");
    const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean; id: number } | null>(null);
  const suppressClick = useRef(false);
  const animTimer = useRef<number | undefined>(undefined);

  const pw = p?.width ?? 1;
  const ph = p?.height ?? 1;
  const imgUrl = api.pageImageUrl(caseId, doc.id, page);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => setImgState("loading"), [imgUrl]);

  const fitScale = useMemo(
    () => (size.w && size.h ? Math.min((size.w - 32) / pw, (size.h - 32) / ph) : 0.3),
    [size.w, size.h, pw, ph],
  );

  const applyView = useCallback((v: { s: number; x: number; y: number }, anim: boolean) => {
    window.clearTimeout(animTimer.current);
    setAnimate(anim);
    setView(v);
    if (anim) animTimer.current = window.setTimeout(() => setAnimate(false), 380);
  }, []);

  const fit = useCallback(
    (anim = true) => {
      if (!size.w) return;
      applyView({ s: fitScale, x: (size.w - pw * fitScale) / 2, y: (size.h - ph * fitScale) / 2 }, anim);
    },
    [applyView, fitScale, size.w, size.h, pw, ph],
  );

  const ready = size.w > 0;
  const focusSig = focus ? `${focus.x0},${focus.y0},${focus.x1},${focus.y1}` : "";
  useEffect(() => {
    if (!ready) return;
    if (focus) {
      const bw = Math.max(40, focus.x1 - focus.x0);
      const bh = Math.max(24, focus.y1 - focus.y0);
      const s = clamp(Math.min((size.w * 0.5) / bw, (size.h * 0.3) / bh), fitScale, Math.max(fitScale, 0.8));
      applyView(
        {
          s,
          x: size.w / 2 - ((focus.x0 + focus.x1) / 2) * s,
          y: size.h / 2 - ((focus.y0 + focus.y1) / 2) * s,
        },
        true,
      );
    } else {
      fit(false);
    }
    // Refit only when the subject changes, not on every resize.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, doc.id, page, focusSig, focusKey, pw, ph]);

  const zoomAt = useCallback(
    (cx: number, cy: number, factor: number, anim = false) => {
      setView((v) => {
        const s = clamp(v.s * factor, Math.min(fitScale, 0.1), 5);
        const k = s / v.s;
        return { s, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k };
      });
      setAnimate(anim);
    },
    [fitScale],
  );

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0016)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false, id: e.pointerId };
    suppressClick.current = false;
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) > 4) {
      d.moved = true;
      suppressClick.current = true;
      wrap.current?.setPointerCapture(d.id);
      setAnimate(false);
    }
    if (d.moved) setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }));
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  const onKey = (e: React.KeyboardEvent) => {
    const step = 60;
    const c = { x: size.w / 2, y: size.h / 2 };
    if (e.key === "+" || e.key === "=") zoomAt(c.x, c.y, 1.25, true);
    else if (e.key === "-") zoomAt(c.x, c.y, 0.8, true);
    else if (e.key === "0") fit();
    else if (e.key === "ArrowLeft") setView((v) => ({ ...v, x: v.x + step }));
    else if (e.key === "ArrowRight") setView((v) => ({ ...v, x: v.x - step }));
    else if (e.key === "ArrowUp") setView((v) => ({ ...v, y: v.y + step }));
    else if (e.key === "ArrowDown") setView((v) => ({ ...v, y: v.y - step }));
    else return;
    e.preventDefault();
  };

  const ordered = useMemo(() => {
    const area = (b: BBox) => (b.x1 - b.x0) * (b.y1 - b.y0);
    return [...regions].sort((a, b) => {
      const aSel = a.finding.id === selectedFindingId ? 1 : 0;
      const bSel = b.finding.id === selectedFindingId ? 1 : 0;
      return aSel - bSel || area(b.bbox) - area(a.bbox);
    });
  }, [regions, selectedFindingId]);

  const inv = 1 / view.s;

  if (!p) {
    return (
      <div className={cn("flex items-center justify-center gap-2 bg-ground text-ink-3", className)}>
        <ImageOff className="size-4" aria-hidden /> This page has no rendered image.
      </div>
    );
  }

  return (
    <div className={cn("relative flex min-h-0 flex-col", className)}>
      <div
        ref={wrap}
        tabIndex={0}
        role="application"
        aria-label={`Page ${page + 1} of ${doc.filename}. Drag to pan, scroll or plus and minus to zoom, 0 to fit.`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKey}
        className="relative min-h-0 flex-1 cursor-grab touch-none select-none overflow-hidden bg-[#e6e3dc] active:cursor-grabbing"
        >
        <div
          className={animate ? "transition-transform duration-[360ms] ease-[cubic-bezier(.2,.7,.2,1)]" : ""}
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: pw,
            height: ph,
            transformOrigin: "0 0",
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.s})`,
          }}
        >
          <img
            key={imgUrl}
            src={imgUrl}
            alt={`Page ${page + 1} of ${doc.filename}`}
            width={pw}
            height={ph}
            draggable={false}
            onLoad={() => setImgState("ok")}
            onError={() => setImgState("error")}
            className="absolute inset-0 block bg-white shadow-[0_0_0_1px_#c8c4ba]"
          />
          <AnimatePresence>
            {heatmap && (
              <motion.img
                key={heatmap.url}
                src={api.resolveUrl(heatmap.url)}
                alt=""
                draggable={false}
                width={pw}
                height={ph}
                initial={{ opacity: 0 }}
                animate={{ opacity: heatmap.opacity }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22 }}
                className="pointer-events-none absolute inset-0"
              />
            )}
          </AnimatePresence>
          <svg
            viewBox={`0 0 ${pw} ${ph}`}
            width={pw}
            height={ph}
            className="absolute inset-0"
            style={{ pointerEvents: "none" }}
          >
            {links.map(([a, b], i) => (
              <line
                key={i}
                x1={(a.x0 + a.x1) / 2}
                y1={(a.y0 + a.y1) / 2}
                x2={(b.x0 + b.x1) / 2}
                y2={(b.y0 + b.y1) / 2}
                stroke="#b3261e"
                strokeWidth={1.5}
                strokeDasharray="6 5"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {ordered.map((r, i) => {
              const m = STATUS_META[r.finding.status];
              const sel = r.finding.id === selectedFindingId;
              return (
                <rect
                  key={`${r.finding.id}-${i}`}
                  x={r.bbox.x0}
                  y={r.bbox.y0}
                  width={Math.max(1, r.bbox.x1 - r.bbox.x0)}
                  height={Math.max(1, r.bbox.y1 - r.bbox.y0)}
                  fill={m.stroke}
                  fillOpacity={sel ? 0.16 : r.finding.status === "OBSERVATION" ? 0.03 : 0.07}
                  stroke={m.stroke}
                  strokeOpacity={sel || r.finding.status !== "OBSERVATION" ? 1 : 0.55}
                  strokeWidth={sel ? 2.5 : 1.5}
                  strokeDasharray={r.primary ? undefined : "5 4"}
                  vectorEffect="non-scaling-stroke"
                  className={sel ? "region-selected" : undefined}
                  style={
                    {
                      pointerEvents: onSelectFinding ? "all" : "none",
                      cursor: "pointer",
                      "--sw": "2.5px",
                    } as React.CSSProperties
                  }
                  onClick={(e) => {
                    e.stopPropagation();
                    if (suppressClick.current) return;
                    onSelectFinding?.(r.finding.id);
                  }}
                >
                  <title>
                    {labels?.get(r.finding.id)} {m.label}: {r.finding.title}
                  </title>
                </rect>
              );
            })}
            {highlight && (
              <rect
                x={highlight.bbox.x0}
                y={highlight.bbox.y0}
                width={highlight.bbox.x1 - highlight.bbox.x0}
                height={highlight.bbox.y1 - highlight.bbox.y0}
                fill="#1f5a96"
                fillOpacity={0.12}
                stroke="#1f5a96"
                strokeWidth={2.5}
                vectorEffect="non-scaling-stroke"
                className="region-selected"
                style={{ "--sw": "2.5px" } as React.CSSProperties}
              />
            )}
          </svg>
          {/* Region tags stay a constant screen size at any zoom. */}
          {ordered
            .filter((r) => r.primary && (r.finding.id === selectedFindingId || r.finding.status !== "OBSERVATION"))
            .filter((r, i, all) => all.findIndex((o) => o.finding.id === r.finding.id) === i)
            .map((r, i) => {
              const m = STATUS_META[r.finding.status];
              const sel = r.finding.id === selectedFindingId;
              return (
                <button
                  key={`${r.finding.id}-tag-${i}`}
                  type="button"
                  tabIndex={-1}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (suppressClick.current) return;
                    onSelectFinding?.(r.finding.id);
                  }}
                  style={{
                    position: "absolute",
                    left: r.bbox.x0,
                    top: r.bbox.y0,
                    transformOrigin: "0 100%",
                    transform: `translateY(-100%) scale(${inv})`,
                    background: m.stroke,
                  }}
                  className="flex cursor-pointer items-center gap-1 whitespace-nowrap rounded-sm px-1.5 py-px text-[13px] font-medium text-white"
                >
                  {labels?.get(r.finding.id)}
                  {sel && <span>{m.label}</span>}
                </button>
              );
            })}
          {highlight && (
            <div
              style={{
                position: "absolute",
                left: highlight.bbox.x0,
                top: highlight.bbox.y0,
                transformOrigin: "0 100%",
                transform: `translateY(-100%) scale(${inv})`,
              }}
              className="whitespace-nowrap rounded-sm bg-accent px-1.5 py-px text-[13px] text-white"
            >
              {highlight.label}
            </div>
          )}
        </div>
        {imgState === "loading" && (
          <div className="absolute inset-0 flex items-center justify-center gap-2 text-ink-3">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            <span>Loading page</span>
          </div>
        )}
        {imgState === "error" && (
          <div role="alert" className="absolute inset-0 flex items-center justify-center gap-2 bg-ground/90 text-ink-2">
            <ImageOff className="size-4" aria-hidden /> The page image could not be loaded from the service.
          </div>
        )}
        <div className="absolute right-3 top-3 flex flex-col border border-line-strong bg-panel">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Zoom in"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => zoomAt(size.w / 2, size.h / 2, 1.3, true)}
          >
            <Plus aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Zoom out"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => zoomAt(size.w / 2, size.h / 2, 0.77, true)}
          >
            <Minus aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Fit page"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => fit()}
          >
            <Maximize aria-hidden />
          </Button>
        </div>
      </div>
    </div>
  );
}

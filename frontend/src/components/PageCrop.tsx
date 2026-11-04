import { useMemo } from "react";
import { ImageOff } from "lucide-react";
import { api } from "@/api";
import type { BBox, Document } from "@/api/types";
import { cn } from "@/lib/utils";

/** Renders a region of the original page image, so the crop is always the real source pixels. */
export function PageCrop({
  caseId,
  doc,
  page,
  bbox,
  stroke = "#eceae4",
  pad = 28,
  className,
  title,
}: {
  caseId: string;
  doc: Document | undefined;
  page: number;
  bbox: BBox;
  stroke?: string;
  pad?: number;
  className?: string;
  title?: string;
}) {
  const p = doc?.pages[page];
  const box = useMemo(() => {
    if (!p) return null;
    const x0 = Math.max(0, bbox.x0 - pad);
    const y0 = Math.max(0, bbox.y0 - pad);
    const x1 = Math.min(p.width, bbox.x1 + pad);
    const y1 = Math.min(p.height, bbox.y1 + pad);
    return { x0, y0, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0) };
  }, [p, bbox, pad]);

  if (!doc || !p || !box) {
    return (
      <div className={cn("flex items-center justify-center gap-2 bg-raised p-4 text-ink-3", className)}>
        <ImageOff className="size-4" aria-hidden />
        <span className="text-xs">Source page unavailable</span>
      </div>
    );
  }
  return (
    <svg
      role="img"
      aria-label={title ?? `Region on page ${page + 1} of ${doc.filename}`}
      viewBox={`${box.x0} ${box.y0} ${box.w} ${box.h}`}
      className={cn("block w-full bg-white", className)}
      preserveAspectRatio="xMidYMid meet"
    >
      <image href={api.pageImageUrl(caseId, doc.id, page)} x={0} y={0} width={p.width} height={p.height} />
      <rect
        x={bbox.x0}
        y={bbox.y0}
        width={bbox.x1 - bbox.x0}
        height={bbox.y1 - bbox.y0}
        fill="none"
        stroke={stroke}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpCircle,
  Bot,
  Check,
  Columns2,
  Cpu,
  Database,
  Link2,
  MapPin,
  X,
} from "lucide-react";
import { api } from "@/api";
import type { Document, EvidenceItem, Finding, ReasoningProvenance, ReviewDecision } from "@/api/types";
import { CATEGORY_LABEL, STATUS_META, splitExplanation } from "@/lib/findings";
import { getReviewer, setReviewer } from "@/lib/reviewer";
import { cn, fmtBBox, fmtTime } from "@/lib/utils";
import { Button } from "./ui/button";
import { ConfidenceMeter, ReviewBadge, SeverityText, StatusBadge } from "./StatusBadge";
import { DataList } from "./DataList";
import { PageCrop } from "./PageCrop";

export function Provenance({ r }: { r: ReasoningProvenance }) {
  const parts =
    r.mode === "live_llm"
      ? { icon: Bot, text: `Explanation by live LLM${r.provider ? `: ${r.provider}` : ""}${r.model ? ` / ${r.model}` : ""}` }
      : r.mode === "demo_cache"
        ? { icon: Database, text: `Explanation replayed from a recorded LLM run${r.provider ? `: ${r.provider}` : ""}${r.model ? ` / ${r.model}` : ""}` }
        : { icon: Cpu, text: "Explanation by deterministic rules, no LLM used" };
  const Icon = parts.icon;
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[11px] text-ink-3">
      <Icon className="size-3 shrink-0" aria-hidden />
      {parts.text}
    </span>
  );
}

export function Explanation({ text }: { text: string }) {
  const parts = splitExplanation(text);
  return (
    <div className="flex flex-col gap-2">
      {parts.map((p, i) => (
        <div key={i}>
          {p.heading && <div className="eyebrow mb-0.5">{p.heading}</div>}
          <p className="leading-relaxed text-ink-2">{p.text}</p>
        </div>
      ))}
    </div>
  );
}

function EvidenceBlock({
  ev,
  caseId,
  docs,
  stroke,
}: {
  ev: EvidenceItem;
  caseId: string;
  docs: Map<string, Document>;
  stroke: string;
}) {
  const [failed, setFailed] = useState(false);
  const hasImage = ev.uri && !failed;
  const doc = ev.doc_id ? docs.get(ev.doc_id) : undefined;
  const measurement = ev.kind === "raw_value" || ev.kind === "metadata" || ev.kind === "field_ref";
  const location = ev.doc_id && (
    <span className="font-mono text-[10.5px] text-ink-3">
      {doc?.filename ?? ev.doc_id}
      {ev.page !== null && ` · p${ev.page + 1}`} {ev.bbox && fmtBBox(ev.bbox)}
    </span>
  );

  // Measurements lead with the numbers; their source crop is a small reference.
  if (measurement) {
    return (
      <figure className="flex gap-2 border border-line bg-ground p-2">
        <figcaption className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-xs text-ink-2">{ev.label}</span>
          <DataList data={ev.data} />
          {location}
        </figcaption>
        {hasImage && (
          <img
            src={api.fileUrl(ev.uri!)}
            alt=""
            loading="lazy"
            onError={() => setFailed(true)}
            className="h-auto max-h-16 w-20 shrink-0 self-start bg-white object-contain"
          />
        )}
      </figure>
    );
  }

  return (
    <figure className="border border-line bg-ground">
      {hasImage ? (
        <img
          src={api.fileUrl(ev.uri!)}
          alt={ev.label}
          loading="lazy"
          onError={() => setFailed(true)}
          className={cn("max-h-56 w-full object-contain", ev.kind === "heatmap" ? "bg-[#050608]" : "bg-white")}
        />
      ) : ev.doc_id && ev.page !== null && ev.bbox ? (
        <PageCrop caseId={caseId} doc={doc} page={ev.page} bbox={ev.bbox} stroke={stroke} className="max-h-48" />
      ) : ev.uri ? (
        <div className="p-2 text-xs text-ink-3">Evidence image could not be loaded: {ev.uri}</div>
      ) : null}
      <figcaption className="flex flex-col gap-1 px-2 py-1.5">
        <span className="text-xs text-ink-2">{ev.label}</span>
        {location}
        <DataList data={ev.data} />
      </figcaption>
    </figure>
  );
}

const ACTIONS: { d: ReviewDecision; label: string; icon: typeof Check }[] = [
  { d: "confirmed", label: "Confirm", icon: Check },
  { d: "dismissed", label: "Dismiss", icon: X },
  { d: "escalated", label: "Escalate", icon: ArrowUpCircle },
];

export function FindingCard({
  finding,
  label,
  caseId,
  docs,
  selected,
  labelsById,
  onSelect,
  onSelectRelated,
  onCompare,
}: {
  finding: Finding;
  label: string;
  caseId: string;
  docs: Map<string, Document>;
  selected: boolean;
  labelsById: Map<string, string>;
  onSelect: () => void;
  onSelectRelated: (id: string) => void;
  onCompare?: () => void;
}) {
  const m = STATUS_META[finding.status];
  const ref = useRef<HTMLElement>(null);
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [reviewer, setName] = useState(getReviewer);

  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);

  const review = useMutation({
    mutationFn: (d: ReviewDecision) => api.reviewFinding(finding.id, d, reviewer.trim() || "examiner", note.trim()),
    onSuccess: () => {
      setReviewer(reviewer.trim() || "examiner");
      setNote("");
      qc.invalidateQueries({ queryKey: ["findings", caseId] });
      qc.invalidateQueries({ queryKey: ["audit", caseId] });
      qc.invalidateQueries({ queryKey: ["dossier", caseId] });
    },
  });

  const doc = finding.doc_id ? docs.get(finding.doc_id) : undefined;
  const dismissed = finding.review.decision === "dismissed";

  return (
    <article
      ref={ref}
      className={cn(
        "border-b border-l-[3px] border-b-line bg-panel transition-colors",
        selected ? cn(m.border, "bg-raised") : "border-l-transparent",
      )}
    >
      <button
        type="button"
        aria-expanded={selected}
        onClick={onSelect}
        className={cn("flex w-full cursor-pointer flex-col gap-1.5 px-3 py-2.5 text-left hover:bg-hover", dismissed && "opacity-60")}
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[11px] text-ink-3">{label}</span>
          <StatusBadge status={finding.status} />
          <span className="ml-auto">
            <ConfidenceMeter value={finding.fused_score ?? finding.confidence} label={finding.fused_score !== null ? "Fused score" : "Confidence"} />
          </span>
        </span>
        <span className="font-medium leading-snug text-ink">{finding.title}</span>
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
          <span>{CATEGORY_LABEL[finding.category]}</span>
          {doc && (
            <span className="font-mono">
              {doc.filename}
              {finding.page !== null && ` · p${finding.page + 1}`}
            </span>
          )}
          {finding.review.decision !== "pending" && <ReviewBadge decision={finding.review.decision} />}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {selected && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-3 px-3 pb-3">
              <Explanation text={finding.explanation} />

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <SeverityText severity={finding.severity} />
                <span className="font-mono text-[11px] text-ink-3">{finding.detector}</span>
                {finding.fused_score !== null && (
                  <span className="font-mono text-[11px] text-ink-3">detector conf {Math.round(finding.confidence * 100)}%</span>
                )}
              </div>

              {finding.bbox && (
                <div className="flex items-center gap-1 font-mono text-[11px] text-ink-3">
                  <MapPin className="size-3" aria-hidden />
                  source region {fmtBBox(finding.bbox)}
                </div>
              )}

              {onCompare && (
                <Button size="sm" onClick={onCompare} className="self-start">
                  <Columns2 aria-hidden /> Compare sources side by side
                </Button>
              )}

              {finding.evidence.length > 0 && (
                <section aria-label="Evidence">
                  <h4 className="eyebrow mb-1.5">Evidence</h4>
                  <div className="flex flex-col gap-2">
                    {finding.evidence.map((ev, i) => (
                      <EvidenceBlock key={i} ev={ev} caseId={caseId} docs={docs} stroke={m.stroke} />
                    ))}
                  </div>
                </section>
              )}

              {finding.benign_alternatives.length > 0 && (
                <section>
                  <h4 className="eyebrow mb-1">Benign explanations to rule out</h4>
                  <ul className="list-disc space-y-0.5 pl-4 text-ink-2 marker:text-ink-3">
                    {finding.benign_alternatives.map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                </section>
              )}

              {finding.recommended_verification.length > 0 && (
                <section>
                  <h4 className="eyebrow mb-1">To verify</h4>
                  <ol className="list-decimal space-y-0.5 pl-4 text-ink-2 marker:font-mono marker:text-ink-3">
                    {finding.recommended_verification.map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ol>
                </section>
              )}

              {finding.related_finding_ids.length > 0 && (
                <section>
                  <h4 className="eyebrow mb-1">Related findings</h4>
                  <div className="flex flex-wrap gap-1">
                    {finding.related_finding_ids.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => onSelectRelated(id)}
                        className="inline-flex cursor-pointer items-center gap-1 border border-line-strong px-1.5 py-0.5 font-mono text-[11px] text-ink-2 hover:bg-hover hover:text-ink"
                      >
                        <Link2 className="size-3" aria-hidden />
                        {labelsById.get(id) ?? id}
                      </button>
                    ))}
                  </div>
                </section>
              )}

              <Provenance r={finding.reasoning} />

              <section className="border-t border-line pt-2.5" aria-label="Examiner decision">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <h4 className="eyebrow">Examiner decision</h4>
                  <ReviewBadge decision={finding.review.decision} />
                </div>
                {finding.review.at && (
                  <p className="mb-1.5 font-mono text-[11px] text-ink-3">
                    {finding.review.reviewer} · {fmtTime(finding.review.at)}
                    {finding.review.note && <span className="block text-ink-2">“{finding.review.note}”</span>}
                  </p>
                )}
                <div className="mb-1.5 flex gap-1.5">
                  <input
                    value={reviewer}
                    onChange={(e) => setName(e.target.value)}
                    aria-label="Reviewer name"
                    placeholder="Reviewer"
                    className="h-8 w-28 border border-line-strong bg-ground px-2 font-mono text-xs text-ink placeholder:text-ink-3"
                  />
                  <input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    aria-label="Optional note"
                    placeholder="Note (optional)"
                    className="h-8 min-w-0 flex-1 border border-line-strong bg-ground px-2 text-xs text-ink placeholder:text-ink-3"
                  />
                </div>
                <div className="grid grid-cols-3 gap-1.5">
                  {ACTIONS.map(({ d, label: l, icon: Icon }) => (
                    <Button
                      key={d}
                      size="sm"
                      disabled={review.isPending}
                      aria-pressed={finding.review.decision === d}
                      className={cn(finding.review.decision === d && "border-ink bg-hover")}
                      onClick={() => review.mutate(d)}
                    >
                      <Icon aria-hidden /> {l}
                    </Button>
                  ))}
                </div>
                {review.isError && (
                  <p role="alert" className="mt-1.5 text-xs text-man">
                    Decision not saved: {(review.error as Error).message}
                  </p>
                )}
                <p className="mt-1.5 text-[11px] text-ink-3">Each decision is written to the audit chain.</p>
              </section>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
}

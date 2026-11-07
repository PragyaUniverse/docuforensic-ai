import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Pause, Play, RotateCcw } from "lucide-react";
import type { Document, EvidenceItem, Finding } from "@/api/types";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PageCrop } from "./PageCrop";
import { StatusBadge } from "./StatusBadge";
import { STATUS_META } from "@/lib/findings";
import { cn, humanize } from "@/lib/utils";

const STEP_MS = 1900;

interface Signal {
  label: string;
  detail: string;
}

function fmt(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  if (Array.isArray(v)) return v.map(fmt).join(", ");
  if (v && typeof v === "object") return Object.entries(v).map(([k, x]) => `${humanize(k)} ${fmt(x)}`).join(", ");
  return String(v ?? "");
}

function isFusion(e: EvidenceItem) {
  return e.kind === "raw_value" && "fused_score" in (e.data ?? {}) && "families" in (e.data ?? {});
}

/** What a finding's evidence says, in the order Doc worked through it. Nothing here is new: it's all on the finding. */
function signalsOf(f: Finding, docs: Map<string, Document>): Signal[] {
  const out: Signal[] = [];
  for (const e of f.evidence) {
    if (isFusion(e) || e.kind === "crop" || e.kind === "heatmap") continue;
    const d = e.data ?? {};
    if (e.kind === "field_ref" && d.value !== undefined) {
      const doc = e.doc_id ? docs.get(e.doc_id) : undefined;
      out.push({ label: `Read ${humanize(String(d.field ?? "value")).toLowerCase()}`, detail: `${fmt(d.value)}${doc ? ` on ${doc.filename}` : ""}` });
    } else {
      const entries = Object.entries(d).filter(([k]) => !["formula", "contributing_detectors"].includes(k)).slice(0, 3);
      out.push({ label: e.label, detail: entries.map(([k, v]) => `${humanize(k)}: ${fmt(v)}`).join(" · ") || "Compared" });
    }
    if (out.length >= 5) break;
  }
  return out;
}

function Bar({ value, tone, delay = 0 }: { value: number; tone: string; delay?: number }) {
  return (
    <div className="h-2 flex-1 overflow-hidden rounded-full bg-raised">
      <motion.div
        className={cn("h-full rounded-full", tone)}
        initial={{ width: 0 }}
        animate={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }}
        transition={{ duration: 0.9, delay, ease: "easeOut" }}
      />
    </div>
  );
}

const RAIL: Record<Finding["status"], string> = { OBSERVATION: "bg-obs", INCONSISTENCY: "bg-inc", POTENTIAL_MANIPULATION: "bg-man" };

/** "How Doc reached this": the finding's own evidence, replayed step by step. */
export function Replay({ finding, docs, caseId, open, onOpenChange }: { finding: Finding; docs: Map<string, Document>; caseId: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const reduce = useReducedMotion();
  const doc = finding.doc_id ? docs.get(finding.doc_id) : undefined;
  const signals = useMemo(() => signalsOf(finding, docs), [finding, docs]);
  const fusion = finding.evidence.find(isFusion);
  const families = Object.entries((fusion?.data?.families ?? {}) as Record<string, number>).filter(([, v]) => typeof v === "number");
  const score = finding.fused_score ?? finding.confidence;
  const steps = ["Where Doc looked", "What Doc measured", "How the signals combine", "What Doc also considered", "Doc's call"];
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    if (!open) return;
    setStep(reduce ? steps.length - 1 : 0);
    setPlaying(!reduce);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reduce]);

  useEffect(() => {
    if (!open || !playing || step >= steps.length - 1) return;
    const t = window.setTimeout(() => setStep((s) => s + 1), STEP_MS + (step === 1 ? signals.length * 280 : 0));
    return () => window.clearTimeout(t);
  }, [open, playing, step, steps.length, signals.length]);

  const m = STATUS_META[finding.status];
  const show = (i: number) => step >= i;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="How Doc reached this" description="The finding's evidence, replayed step by step" className="w-[min(820px,96vw)]">
        <div className="flex flex-col gap-4 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={finding.status} />
            <span className="font-medium text-ink">{finding.title}</span>
          </div>

          <ol className="flex gap-1.5" aria-label="Steps">
            {steps.map((s, i) => (
              <li key={s} className="flex-1">
                <button type="button" onClick={() => { setStep(i); setPlaying(false); }} className="w-full cursor-pointer text-left" aria-current={step === i ? "step" : undefined}>
                  <span className={cn("block h-1 rounded-full transition-colors duration-300", step >= i ? RAIL[finding.status] : "bg-raised")} />
                  <span className={cn("mt-1 hidden text-[11px] sm:block", step === i ? "text-ink" : "text-ink-3")}>{s}</span>
                </button>
              </li>
            ))}
          </ol>

          <div className="flex min-h-[300px] flex-col gap-4">
            <AnimatePresence>
              {show(0) && (
                <motion.section key="look" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="grid gap-3 sm:grid-cols-[200px_minmax(0,1fr)]">
                  {doc && finding.page !== null && finding.bbox ? (
                    <PageCrop caseId={caseId} doc={doc} page={finding.page} bbox={finding.bbox} stroke={m.stroke} className="max-h-40 rounded-md" />
                  ) : (
                    <div className="rounded-md bg-raised p-4 text-[13px] text-ink-3">Case-level finding</div>
                  )}
                  <div>
                    <div className="mono-label">1. Where Doc looked</div>
                    <p className="mt-1 text-ink-2">
                      {doc ? (
                        <>
                          <span className="font-mono text-[13px] text-ink">{doc.filename}</span>
                          {finding.page !== null && `, page ${finding.page + 1}`}
                          {finding.related_doc_ids.length > 0 && `, compared with ${finding.related_doc_ids.length} other document${finding.related_doc_ids.length === 1 ? "" : "s"}`}.
                        </>
                      ) : (
                        "Across the case's documents."
                      )}
                    </p>
                  </div>
                </motion.section>
              )}

              {show(1) && (
                <motion.section key="measure" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="mono-label">2. What Doc measured</div>
                  <ul className="mt-2 flex flex-col gap-1.5">
                    {signals.length === 0 && <li className="text-[13.5px] text-ink-3">The explanation holds the measurement.</li>}
                    {signals.map((s, i) => (
                      <motion.li
                        key={i}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: reduce ? 0 : 0.25 + i * 0.28 }}
                        className="flex flex-wrap items-baseline gap-x-2 rounded-md border border-line bg-ground/60 px-3 py-1.5 text-[13.5px]"
                      >
                        <span className={cn("size-1.5 shrink-0 self-center rounded-full", RAIL[finding.status])} />
                        <span className="font-medium text-ink">{s.label}</span>
                        <span className="min-w-0 break-words font-mono text-[12px] text-ink-2">{s.detail}</span>
                      </motion.li>
                    ))}
                  </ul>
                </motion.section>
              )}

              {show(2) && (
                <motion.section key="combine" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="mono-label">3. How the signals combine</div>
                  <div className="mt-2 flex flex-col gap-1.5">
                    {families.map(([name, v], i) => (
                      <div key={name} className="flex items-center gap-3 text-[13px]">
                        <span className="w-28 shrink-0 text-ink-2">{humanize(name)}</span>
                        <Bar value={v} tone="bg-ink-3" delay={reduce ? 0 : i * 0.15} />
                        <span className="w-10 text-right font-mono text-[11.5px] text-ink-2">{Math.round(v * 100)}%</span>
                      </div>
                    ))}
                    <div className="mt-1 flex items-center gap-3 text-[13px]">
                      <span className="w-28 shrink-0 font-medium text-ink">{families.length ? "Combined" : "Confidence"}</span>
                      <Bar value={score} tone={RAIL[finding.status]} delay={reduce ? 0 : families.length * 0.15 + 0.2} />
                      <span className="w-10 text-right font-mono text-[11.5px] font-semibold text-ink">{Math.round(score * 100)}%</span>
                    </div>
                    <p className="text-[12.5px] text-ink-3">
                      {families.length > 1
                        ? `${families.length} independent kinds of signal point at the same spot, so together they count for more than any one alone.`
                        : families.length === 1
                          ? "One kind of signal on its own. Strong only means the check is sure about what it measured."
                          : "How sure this check is about what it measured, within this check only."}
                    </p>
                  </div>
                </motion.section>
              )}

              {show(3) && (
                <motion.section key="benign" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="mono-label">4. What Doc also considered</div>
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[13.5px] text-ink-2 marker:text-ink-3">
                    {(finding.benign_alternatives.length ? finding.benign_alternatives : ["No innocent explanation was recorded for this check."]).slice(0, 3).map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                </motion.section>
              )}

              {show(4) && (
                <motion.section
                  key="call"
                  initial={{ opacity: 0, scale: 0.97 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ type: "spring", stiffness: 260, damping: 22 }}
                  className={cn(
                    "rounded-lg border p-4",
                    finding.status === "POTENTIAL_MANIPULATION" ? "border-man/50 glow-red" : finding.status === "INCONSISTENCY" ? "border-inc/50 glow-amber" : "border-obs/50 glow-cyan",
                  )}
                >
                  <div className="mono-label">5. Doc's call</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <StatusBadge status={finding.status} />
                    <span className="font-mono text-[12px] tracking-[0.12em] text-ink">REQUIRES HUMAN REVIEW</span>
                  </div>
                  <p className="mt-2 text-[13.5px] text-ink-2">
                    A possibility for you to check, not a conclusion. Confirm, dismiss or escalate it on the finding.
                  </p>
                </motion.section>
              )}
            </AnimatePresence>
          </div>

          <div className="sticky bottom-0 -mx-5 -mb-5 flex flex-wrap items-center gap-2 border-t border-line bg-panel px-5 py-3">
            <Button size="sm" onClick={() => (step >= steps.length - 1 ? (setStep(0), setPlaying(true)) : setPlaying((p) => !p))}>
              {step >= steps.length - 1 ? <RotateCcw className="size-3.5" aria-hidden /> : playing ? <Pause className="size-3.5" aria-hidden /> : <Play className="size-3.5" aria-hidden />}
              {step >= steps.length - 1 ? "Replay" : playing ? "Pause" : "Play"}
            </Button>
            <Button size="sm" disabled={step >= steps.length - 1} onClick={() => { setPlaying(false); setStep((s) => Math.min(steps.length - 1, s + 1)); }}>
              Next step
            </Button>
            <Button size="sm" onClick={() => { setPlaying(false); setStep(steps.length - 1); }} className="ml-auto">
              Show all
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

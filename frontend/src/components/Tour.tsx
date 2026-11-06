import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation, useMatch } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCase } from "@/api/hooks";
import { endTour, startTour, tourForPath, tourSeen, useActiveTour, type TourId } from "@/lib/tour";
import { Button } from "./ui/button";
import { Mascot, type Mood } from "./Mascot";

interface Step {
  target?: string; // a data-tour value; none means Doc speaks from the middle of the screen
  title: string;
  text: string;
  mood?: Mood;
}

const TOURS: Record<TourId, Step[]> = {
  home: [
    { title: "Doc online", text: "I'm Doc, the investigation assistant. Here's a 30-second orientation." },
    { target: "start", title: "Open an investigation", text: "Give the case an identifier, then add every document from the same application as evidence." },
    { target: "examples", title: "Demo evidence sets", text: "Synthetic cases with made-up people. \"Altered salary slip\" is the best first look." },
    { target: "header-links", title: "Navigation", text: "Investigations, analytics across cases, and About, which lists exactly what I can and can't do." },
    { target: "doc", title: "Ask Doc anytime", text: "Open me from here to ask about any investigation. I explain the evidence. Decisions stay with you.", mood: "happy" },
  ],
  case: [
    { target: "status", title: "Case status", text: "Risk level, how much evidence was analyzed, and how far the review has got. The risk level only sets priority." },
    { target: "top-findings", title: "Priority findings", text: "The strongest signals first, each with its confidence and a path to the evidence." },
    { target: "doc-panel", title: "Doc's briefing", text: "My summary of where to look. Ask me follow-up questions from here." },
    { target: "tab-viewer", title: "Findings", text: "Every finding, highlighted on the document itself." },
    { target: "tab-conflicts", title: "Compare", text: "Values that disagree between documents, side by side, and the evidence graph." },
    { target: "tab-audit", title: "Timeline", text: "Every step and decision, chained together so you can prove nothing changed afterwards.", mood: "happy" },
  ],
  findings: [
    { target: "doc-tabs", title: "Evidence files", text: "Switch between documents. The count shows what needs review on each." },
    { target: "canvas", title: "Document inspection", text: "Findings are outlined on the page. Scroll to zoom, drag to pan." },
    { target: "show", title: "Forensic views", text: "Switch to error level analysis or noise to see what the checks measured. Treat them as hints." },
    { target: "findings", title: "Doc's findings", text: "Strongest first. Open one for the reasoning, innocent explanations and how to verify." },
    { title: "Your call", text: "Confirm, dismiss or escalate each finding. Every decision is written to the timeline.", mood: "happy" },
  ],
};

const CARD_W = 320;
const PAD = 8;

function placement(rect: DOMRect | null, vw: number, vh: number, w: number, h: number) {
  if (!rect) return { left: (vw - w) / 2, top: (vh - h) / 2 };
  const clampX = (x: number) => Math.min(Math.max(x, 12), vw - w - 12);
  const clampY = (y: number) => Math.min(Math.max(y, 12), vh - h - 12);
  if (rect.bottom + 16 + h < vh) return { left: clampX(rect.left), top: rect.bottom + 16 };
  if (rect.top - 16 - h > 0) return { left: clampX(rect.left), top: rect.top - 16 - h };
  if (rect.right + 16 + w < vw) return { left: rect.right + 16, top: clampY(rect.top) };
  if (rect.left - 16 - w > 0) return { left: rect.left - 16 - w, top: clampY(rect.top) };
  return { left: clampX(vw - w - 12), top: clampY(vh - h - 12) };
}

function TourOverlay({ id }: { id: TourId }) {
  const still = useReducedMotion();
  const steps = TOURS[id];
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });
  const card = useRef<HTMLDivElement>(null);
  const next = useRef<HTMLButtonElement>(null);
  const [cardH, setCardH] = useState(200);
  const step = steps[index];
  const last = index === steps.length - 1;

  const measure = useCallback(() => {
    setSize({ w: window.innerWidth, h: window.innerHeight });
    const el = step.target ? document.querySelector(`[data-tour="${step.target}"]`) : null;
    setRect(el ? el.getBoundingClientRect() : null);
  }, [step.target]);

  // Bring the target into view, then measure it. A step whose target isn't on screen is skipped.
  useEffect(() => {
    if (!step.target) {
      setRect(null);
      return;
    }
    const el = document.querySelector(`[data-tour="${step.target}"]`);
    if (!el) {
      setIndex((i) => (i < steps.length - 1 ? i + 1 : i));
      return;
    }
    el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: still ? "auto" : "smooth" });
    const t = window.setTimeout(measure, still ? 0 : 320);
    return () => window.clearTimeout(t);
  }, [step.target, steps.length, measure, still]);

  useEffect(() => {
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [measure]);

  useLayoutEffect(() => {
    if (card.current) setCardH(card.current.offsetHeight);
    next.current?.focus({ preventScroll: true });
  }, [index]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") endTour();
      if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, steps.length - 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [steps.length]);

  const width = Math.min(CARD_W + 76, size.w - 24);
  const spot = step.target ? rect : null;
  const pos = placement(spot, size.w, size.h, width, cardH);
  const glide = still ? { duration: 0 } : { type: "spring" as const, stiffness: 170, damping: 22 };

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label="Tour of the page">
      {/* Clicks outside the tour do nothing, so nothing changes underneath while Doc is talking. */}
      <div className="absolute inset-0" />
      {spot ? (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute rounded-xl ring-2 ring-accent"
          initial={false}
          animate={{ left: spot.left - PAD, top: spot.top - PAD, width: spot.width + PAD * 2, height: spot.height + PAD * 2 }}
          transition={glide}
          style={{ boxShadow: "0 0 0 9999px rgba(12, 14, 20, 0.58)" }}
        />
      ) : (
        <motion.div aria-hidden className="absolute inset-0 bg-[rgba(12,14,20,0.58)]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} />
      )}

      <motion.div
        className="absolute flex items-end gap-2"
        style={{ width }}
        initial={still ? false : { left: pos.left, top: pos.top + 30, opacity: 0 }}
        animate={{ left: pos.left, top: pos.top, opacity: 1 }}
        transition={glide}
      >
        <div className="hidden shrink-0 sm:block">
          <Mascot mood={step.mood ?? "idle"} size={66} />
        </div>
        <AnimatePresence mode="wait">
          <motion.div
            key={index}
            ref={card}
            initial={still ? false : { opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={still ? undefined : { opacity: 0, y: -4 }}
            transition={{ duration: 0.16 }}
            className="min-w-0 flex-1 rounded-xl rounded-bl-sm border border-line bg-panel p-4 shadow-2xl"
          >
            <div className="flex items-center gap-2 sm:hidden">
              <Mascot mood={step.mood ?? "idle"} size={36} />
            </div>
            <h2 className="text-[17px] font-semibold leading-snug">{step.title}</h2>
            <p className="mt-1 text-[14px] leading-relaxed text-ink-2">{step.text}</p>
            <div className="mt-3 flex items-center gap-2">
              <span className="text-[12px] text-ink-3" aria-label={`Step ${index + 1} of ${steps.length}`}>
                {steps.map((_, i) => (
                  <span key={i} aria-hidden className={`mr-1 inline-block size-1.5 rounded-full ${i === index ? "bg-accent" : "bg-line-strong"}`} />
                ))}
              </span>
              <button type="button" onClick={endTour} className="ml-auto cursor-pointer text-[13px] text-ink-3 hover:text-ink hover:underline">
                {last ? "Close" : "Skip"}
              </button>
              {index > 0 && (
                <Button size="sm" onClick={() => setIndex((i) => i - 1)}>
                  Back
                </Button>
              )}
              <Button ref={next} size="sm" variant="primary" onClick={() => (last ? endTour() : setIndex((i) => i + 1))}>
                {last ? "Got it" : index === 0 ? "Show me" : "Next"}
              </Button>
            </div>
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

/** Runs each tour once, the first time you reach its page, and on request after that. */
export function TourHost() {
  const active = useActiveTour();
  const location = useLocation();
  const match = useMatch("/cases/:caseId/*");
  const c = useCase(match?.params.caseId);
  const complete = c.data?.case.status === "complete";

  useEffect(() => {
    if (active) return;
    const id = tourForPath(location.pathname);
    const tab = match?.params["*"] ?? "";
    const ready = id === "home" ? location.pathname === "/" : complete && (id === "findings" || tab === "");
    if (!ready || tourSeen(id)) return;
    // Wait until the page has drawn what the tour points at.
    const wanted = TOURS[id].find((s) => s.target)?.target;
    let tries = 0;
    const timer = window.setInterval(() => {
      tries += 1;
      if (!wanted || document.querySelector(`[data-tour="${wanted}"]`) || tries > 25) {
        window.clearInterval(timer);
        if (tries <= 25) startTour(id);
      }
    }, 200);
    return () => window.clearInterval(timer);
  }, [location.pathname, complete, active, match?.params]);

  return <AnimatePresence>{active && <TourOverlay key={active} id={active} />}</AnimatePresence>;
}

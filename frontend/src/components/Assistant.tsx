import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useMatch } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api } from "@/api";
import { useFindings } from "@/api/hooks";
import { onDocSays } from "@/lib/assistant";
import { Mascot, type Mood } from "./Mascot";

const HIDDEN_KEY = "docuforensic.docHidden";

function readHidden(): boolean {
  try {
    return localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function saveHidden(v: boolean) {
  try {
    localStorage.setItem(HIDDEN_KEY, v ? "1" : "0");
  } catch {
    // Without storage, the choice lasts until the page reloads.
  }
}

/** What Doc says on each screen. All of it comes from results already on the page, with no new claims. */
function guidance(tab: string, status: string | undefined, risk: string | undefined, toLook: number, nothingRead: boolean): { text: string; mood: Mood } {
  if (nothingRead) return { text: "I couldn't read any of these files. The list here says why.", mood: "oops" };
  if (status === "running") return { text: "Still checking these documents.", mood: "thinking" };
  const done = status === "complete";
  switch (tab) {
    case "":
      if (!done) return { text: "Add every document from the application, then press the button to check them.", mood: "idle" };
      if (toLook > 0) {
        return {
          text: `${toLook} thing${toLook === 1 ? "" : "s"} here deserve${toLook === 1 ? "s" : ""} a closer look. You make the call.`,
          mood: risk === "low" ? "idle" : "concerned",
        };
      }
      return { text: "Nothing stood out. That doesn't prove the documents are genuine.", mood: "happy" };
    case "viewer":
      return { text: "Click a finding and I'll jump to the spot on the page.", mood: "idle" };
    case "conflicts":
      return { text: "These only show up when the documents are read together.", mood: "idle" };
    case "graph":
      return { text: "Each red line is a conflict. Click one to see both sides.", mood: "idle" };
    case "data":
      return { text: "A machine read these, so double-check anything important.", mood: "idle" };
    case "dossier":
      return { text: "Here's the full report. You can download it from the top.", mood: "happy" };
    case "audit":
      return { text: "Press Verify integrity to check nothing has been changed.", mood: "idle" };
    default:
      return { text: "Click me any time for a tip.", mood: "idle" };
  }
}

/** Doc, the floating guide. Drag it anywhere, click it for a tip, or hide it. */
export function Assistant() {
  const still = useReducedMotion();
  const match = useMatch("/cases/:caseId/*");
  const location = useLocation();
  const caseId = match?.params.caseId;
  const tab = match?.params["*"] ?? "";
  const [hidden, setHidden] = useState(readHidden);
  const [bubble, setBubble] = useState<string | null>(null);
  const [override, setOverride] = useState<Mood | null>(null);
  const [wander, setWander] = useState(0);
  const dragged = useRef(false);
  const hideTimer = useRef<number>(0);
  const moodTimer = useRef<number>(0);

  const c = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.getCase(caseId!),
    enabled: !!caseId,
    refetchInterval: (q) => (q.state.data?.case.status === "running" ? 2000 : false),
  });
  const findings = useFindings(caseId);
  const toLook = useMemo(() => (findings.data ?? []).filter((f) => f.status !== "OBSERVATION").length, [findings.data]);
  const docs = c.data?.documents ?? [];
  const nothingRead = c.data?.case.status === "complete" && docs.length > 0 && docs.every((d) => d.page_count === 0);
  const now = guidance(tab, c.data?.case.status, c.data?.case.risk_level, toLook, nothingRead);
  const mood = override ?? now.mood;

  const say = (text: string, ms = 6000) => {
    setBubble(text);
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setBubble(null), ms);
  };

  // A short tip when arriving somewhere new, and once results are in.
  const sayRef = useRef(say);
  sayRef.current = say;
  useEffect(() => {
    const t = window.setTimeout(() => sayRef.current(now.text), 600);
    return () => window.clearTimeout(t);
    // Only on arrival or when the result changes, never on every re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, c.data?.case.status, toLook]);

  useEffect(
    () =>
      onDocSays((text, m) => {
        sayRef.current(text, 4500);
        setOverride(m);
        window.clearTimeout(moodTimer.current);
        moodTimer.current = window.setTimeout(() => setOverride(null), 4500);
      }),
    [],
  );

  // Now and then, Doc strolls a little way along the bottom of the screen.
  useEffect(() => {
    if (still || hidden) return;
    let timer: number;
    const stroll = () => {
      timer = window.setTimeout(() => {
        setWander(Math.round(Math.random() * 70));
        stroll();
      }, 14000 + Math.random() * 16000);
    };
    stroll();
    return () => window.clearTimeout(timer);
  }, [still, hidden]);

  // The map's zoom buttons sit in the bottom-left corner.
  const left = tab === "graph" ? 64 : 12;

  if (hidden) {
    return (
      <button
        type="button"
        onClick={() => {
          setHidden(false);
          saveHidden(false);
        }}
        title="Show Doc"
        className="fixed bottom-2 left-2 z-40 cursor-pointer rounded-full border border-line bg-panel px-2.5 py-1 text-[13px] text-ink-2 shadow-sm hover:text-ink"
      >
        Show Doc
      </button>
    );
  }

  return (
    <motion.div
      className="pointer-events-none fixed bottom-1 z-40"
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0, x: wander }}
      transition={{ x: { duration: 2.2, ease: "easeInOut" }, default: { duration: 0.35 } }}
      style={{ left }}
    >
      <motion.div drag dragMomentum={false} dragElastic={0.05} onDragStart={() => (dragged.current = true)} className="pointer-events-auto relative w-fit cursor-grab active:cursor-grabbing">
        <AnimatePresence>
          {bubble && (
            <motion.div
              role="status"
              initial={{ opacity: 0, scale: 0.85, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 4 }}
              transition={{ type: "spring", stiffness: 320, damping: 24 }}
              style={{ transformOrigin: "0% 100%" }}
              className="absolute bottom-[calc(100%-6px)] left-8 w-56 rounded-xl rounded-bl-sm border border-line bg-panel px-3 py-2 pr-7 text-[14px] leading-snug text-ink shadow-lg sm:bottom-14 sm:left-[calc(100%+2px)]"
            >
              {bubble}
              <button
                type="button"
                aria-label="Hide Doc"
                title="Hide Doc"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => {
                  setHidden(true);
                  saveHidden(true);
                }}
                className="absolute right-1.5 top-1.5 cursor-pointer rounded p-0.5 text-ink-3 hover:bg-hover hover:text-ink"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
        <motion.button
          type="button"
          aria-label="Doc, your guide. Click for a tip."
          title="Doc is a guide. It only repeats what the checks found, and it doesn't decide anything."
          whileHover={still ? undefined : { scale: 1.06, rotate: -2 }}
          whileTap={still ? undefined : { scale: 0.94 }}
          onClick={() => {
            if (dragged.current) {
              dragged.current = false;
              return;
            }
            say(now.text);
            setOverride("hello");
            window.clearTimeout(moodTimer.current);
            moodTimer.current = window.setTimeout(() => setOverride(null), 2600);
          }}
          className="block cursor-[inherit] rounded-2xl p-1"
        >
          <Mascot mood={mood} size={68} />
        </motion.button>
      </motion.div>
    </motion.div>
  );
}

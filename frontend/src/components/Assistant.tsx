import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useMatch } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, ChevronRight, X } from "lucide-react";
import { api } from "@/api";
import { accountApi, type ChatReply } from "@/api/account";
import { onDocSays, onOpenDocChat } from "@/lib/assistant";
import { caseCode } from "@/lib/case";
import { TOUR_REQUEST, startTour, tourForPath, useActiveTour } from "@/lib/tour";
import { cn } from "@/lib/utils";
import { DocOrb } from "./DocOrb";

interface ChatLine {
  id: number;
  from: "you" | "doc";
  text: string;
  reply?: ChatReply;
}

function starters(tab: string, finding: boolean, caseOpen: boolean, done: boolean): string[] {
  if (finding && tab === "viewer") return ["Explain this finding", "Could this be innocent?", "How do I check this?"];
  if (!caseOpen) return ["Give me a tour", "How do I start?", "What can you do?"];
  if (!done) return ["How do I add documents?", "What do the labels mean?"];
  return ["What conflicts did you find?", "Which document looks suspicious?", "Show me the strongest evidence", "What should I investigate first?"];
}

function SourceNote({ reply }: { reply: ChatReply }) {
  if (reply.source === "live_llm") {
    return <p className="mt-1.5 font-mono text-[10.5px] tracking-[0.08em] text-ink-3">AI MODEL{reply.model ? ` · ${reply.model.toUpperCase()}` : ""} · VERIFY BEFORE RELYING ON IT</p>;
  }
  if (reply.source === "results") return <p className="mt-1.5 font-mono text-[10.5px] tracking-[0.08em] text-ink-3">SOURCE · CASE RESULTS</p>;
  return null;
}

function Drawer({ caseId, findingId, suggestions, onClose }: { caseId?: string; findingId: string | null; suggestions: string[]; onClose: () => void }) {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const list = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), []);
  useEffect(() => setLines([]), [caseId]);
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [lines, busy]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  const ask = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    // A tour is shown, not told, so it's handled here instead of going to the server.
    if (TOUR_REQUEST.test(question)) {
      onClose();
      startTour(tourForPath(window.location.pathname));
      return;
    }
    setDraft("");
    setLines((l) => [...l, { id: nextId.current++, from: "you", text: question }]);
    setBusy(true);
    try {
      const reply = await accountApi.chat(question, caseId, findingId);
      setLines((l) => [...l, { id: nextId.current++, from: "doc", text: reply.answer, reply }]);
    } catch {
      setLines((l) => [...l, { id: nextId.current++, from: "doc", text: "I can't reach the analysis service right now. Check it's running, then try again." }]);
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  };

  const latest = [...lines].reverse().find((l) => l.reply)?.reply;
  const chips = latest?.suggestions.length ? latest.suggestions : lines.length === 0 ? suggestions : [];

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.aside
        aria-label="Doc, investigation assistant"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 340, damping: 36 }}
        className="fixed inset-y-0 right-0 z-50 flex w-[440px] max-w-full flex-col border-l border-line bg-panel shadow-[-24px_0_60px_-20px_rgba(0,0,0,0.6)]"
      >
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[radial-gradient(ellipse_at_top,rgba(var(--color-glow),0.14),transparent_70%)]" />
        <header className="relative flex shrink-0 items-center gap-3 border-b border-line px-5 py-4">
          <DocOrb state={busy ? "thinking" : "idle"} size={38} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[13px] font-semibold tracking-[0.2em] text-ink">DOC</span>
              <span className="flex items-center gap-1.5 font-mono text-[10.5px] tracking-[0.12em] text-accent">
                <span className="status-dot" /> {busy ? "ANALYZING" : "ONLINE"}
              </span>
            </div>
            <div className="mono-label mt-0.5 !text-[10.5px]">Investigation assistant{caseId ? ` · ${caseCode(caseId)}` : ""}</div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="cursor-pointer rounded-md p-1.5 text-ink-3 hover:bg-hover hover:text-ink">
            <X className="size-4" aria-hidden />
          </button>
        </header>

        <div ref={list} role="log" aria-live="polite" className="relative flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-5">
          <div className="text-[14.5px] leading-relaxed text-ink-2">
            {caseId
              ? "Ask me about this investigation. I answer from the case's results and point you to the evidence. Decisions stay with you."
              : "Ask me how to use DocuForensic, or open an investigation and ask about its evidence."}
          </div>
          {lines.map((l) =>
            l.from === "you" ? (
              <motion.div key={l.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex gap-2 text-[14px] text-ink">
                <span className="mt-0.5 font-mono text-[12px] text-accent">›</span>
                <span className="font-medium">{l.text}</span>
              </motion.div>
            ) : (
              <motion.div key={l.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="relative rounded-xl border border-line bg-raised/60 p-3.5 pl-4">
                <span aria-hidden className="absolute inset-y-3 left-0 w-[2px] rounded-full bg-accent shadow-[0_0_10px_rgba(var(--color-glow),0.8)]" />
                <div className="whitespace-pre-line text-[14px] leading-relaxed text-ink">{l.text}</div>
                {l.reply && <SourceNote reply={l.reply} />}
                {!!l.reply?.links.length && (
                  <div className="mt-2.5 flex flex-wrap gap-2">
                    {l.reply.links.map((a) => (
                      <Link key={a.to} to={a.to} className="group inline-flex items-center gap-1 rounded-md border border-[rgba(var(--color-glow),0.3)] px-2 py-1 text-[12.5px] font-medium text-accent hover:bg-[rgba(var(--color-glow),0.08)]">
                        {a.label}
                        <ChevronRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
                      </Link>
                    ))}
                  </div>
                )}
              </motion.div>
            ),
          )}
          {busy && (
            <div role="status" aria-label="Doc is analyzing" className="flex items-center gap-2 font-mono text-[11px] tracking-[0.12em] text-accent">
              <span className="flex gap-1">
                {[0, 0.15, 0.3].map((d) => (
                  <motion.span key={d} className="size-1 rounded-full bg-accent" animate={{ opacity: [0.2, 1, 0.2] }} transition={{ duration: 0.9, repeat: Infinity, delay: d }} />
                ))}
              </span>
              ANALYZING CASE DATA
            </div>
          )}
          {!busy && chips.length > 0 && (
            <div className="fade-in">
              <div className="mono-label mb-2">Suggested queries</div>
              <div className="flex flex-col gap-1">
                {chips.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => ask(c)}
                    className="group flex cursor-pointer items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-left text-[13.5px] text-ink-2 transition-colors duration-150 hover:border-[rgba(var(--color-glow),0.45)] hover:bg-[rgba(var(--color-glow),0.05)] hover:text-ink"
                  >
                    {c}
                    <ChevronRight className="size-4 shrink-0 text-ink-3 transition-transform group-hover:translate-x-0.5 group-hover:text-accent" aria-hidden />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <form
          className="relative flex shrink-0 items-center gap-2 border-t border-line p-3"
          onSubmit={(e) => {
            e.preventDefault();
            ask(draft);
          }}
        >
          <span className="pl-1 font-mono text-[13px] text-accent" aria-hidden>
            ›
          </span>
          <input
            ref={input}
            value={draft}
            maxLength={500}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask Doc about this investigation"
            aria-label="Ask Doc a question"
            className="h-10 min-w-0 flex-1 bg-transparent text-[14px] text-ink placeholder:text-ink-3 focus:outline-none"
          />
          <button type="submit" disabled={busy || !draft.trim()} aria-label="Send" className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg bg-accent text-[#03141a] transition-[filter,opacity] hover:brightness-110 disabled:cursor-default disabled:opacity-30">
            <ArrowUp className="size-4" aria-hidden />
          </button>
        </form>
      </motion.aside>
    </>
  );
}

/** Doc's assistant drawer, plus short notices when something worth knowing happens. */
export function Assistant() {
  const match = useMatch("/cases/:caseId/*");
  const location = useLocation();
  const caseId = match?.params.caseId;
  const tab = match?.params["*"] ?? "";
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<{ text: string; tone: string } | null>(null);
  const timer = useRef<number>(0);
  const touring = useActiveTour();
  const c = useQuery({ queryKey: ["case", caseId], queryFn: () => api.getCase(caseId!), enabled: !!caseId });
  const findingId = new URLSearchParams(location.search).get("finding");

  useEffect(() => onOpenDocChat(() => setOpen(true)), []);
  useEffect(
    () =>
      onDocSays((text, mood) => {
        setNotice({ text, tone: mood === "oops" || mood === "concerned" ? "alert" : "ok" });
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setNotice(null), 4200);
      }),
    [],
  );

  if (touring) return null;
  return (
    <>
      <AnimatePresence>
        {notice && !open && (
          <motion.div
            role="status"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8 }}
            className={cn("panel fixed bottom-5 right-5 z-40 flex max-w-sm items-center gap-3 py-3 pl-3 pr-4", notice.tone === "alert" ? "glow-red" : "glow-cyan")}
          >
            <DocOrb state={notice.tone === "alert" ? "alert" : "done"} size={28} />
            <div>
              <div className="font-mono text-[10.5px] tracking-[0.14em] text-ink-3">DOC</div>
              <div className="text-[13.5px] text-ink">{notice.text}</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {open && (
          <Drawer
            caseId={caseId}
            findingId={findingId}
            suggestions={starters(tab, !!findingId, !!caseId, c.data?.case.status === "complete")}
            onClose={() => setOpen(false)}
          />
        )}
      </AnimatePresence>
    </>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useMatch } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { Send, X } from "lucide-react";
import { api } from "@/api";
import { accountApi, type ChatReply } from "@/api/account";
import { useFindings } from "@/api/hooks";
import { onDocSays, onOpenDocChat } from "@/lib/assistant";
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
      return { text: "Click a finding to see the spot on the page. Click me if you have a question.", mood: "idle" };
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
      return { text: "Click me if you have a question.", mood: "idle" };
  }
}

interface ChatLine {
  id: number;
  from: "you" | "doc";
  text: string;
  reply?: ChatReply;
}

function starters(tab: string, finding: boolean, caseOpen: boolean, done: boolean): string[] {
  if (finding && tab === "viewer") return ["Explain this finding", "Could this be innocent?", "How do I check this?"];
  if (!caseOpen) return ["How do I start?", "What can you do?", "What do the labels mean?"];
  if (!done) return ["How do I add documents?", "What do the labels mean?"];
  if (tab === "audit") return ["What does Verify integrity do?", "What did you find?"];
  if (tab === "dossier") return ["How do I download the report?", "What did you find?"];
  return ["What did you find?", "What should I look at first?", "Do the documents conflict?"];
}

function SourceNote({ reply }: { reply: ChatReply }) {
  if (reply.source === "live_llm") {
    return (
      <p className="mt-1 text-[12px] text-ink-3">
        Written by an AI model from these results{reply.model ? ` (${reply.model})` : ""}, so please check it.
      </p>
    );
  }
  if (reply.source === "results") return <p className="mt-1 text-[12px] text-ink-3">From this case's results.</p>;
  return null;
}

function ChatPanel({
  caseId,
  findingId,
  suggestions,
  onClose,
  onHide,
  onThinking,
}: {
  caseId?: string;
  findingId: string | null;
  suggestions: string[];
  onClose: () => void;
  onHide: () => void;
  onThinking: (busy: boolean) => void;
}) {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const list = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), []);
  // Each case gets its own conversation.
  useEffect(() => setLines([]), [caseId]);
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [lines, busy]);

  const ask = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    setDraft("");
    setLines((l) => [...l, { id: nextId.current++, from: "you", text: question }]);
    setBusy(true);
    onThinking(true);
    try {
      const reply = await accountApi.chat(question, caseId, findingId);
      setLines((l) => [...l, { id: nextId.current++, from: "doc", text: reply.answer, reply }]);
    } catch {
      setLines((l) => [...l, { id: nextId.current++, from: "doc", text: "I can't reach the service right now. Please check it's running, then try again." }]);
    } finally {
      setBusy(false);
      onThinking(false);
      input.current?.focus();
    }
  };

  const latest = [...lines].reverse().find((l) => l.reply)?.reply;
  const chips = latest?.suggestions.length ? latest.suggestions : lines.length === 0 ? suggestions : [];

  return (
    <motion.section
      aria-label="Chat with Doc"
      initial={{ opacity: 0, y: 14, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.98 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      style={{ transformOrigin: "0% 100%" }}
      className="pointer-events-auto fixed bottom-3 left-3 z-50 flex h-[min(520px,calc(100dvh-90px))] w-[360px] max-w-[calc(100vw-24px)] flex-col overflow-hidden rounded-2xl border-2 border-[var(--color-edge)] bg-panel shadow-[6px_6px_0_var(--color-edge)]"
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-line px-3 py-2">
        <Mascot mood={busy ? "thinking" : "idle"} size={30} />
        <div className="min-w-0 flex-1 pl-1">
          <div className="font-[family-name:var(--font-display)] text-[17px] font-extrabold leading-tight">Doc ✦</div>
          <div className="truncate text-[12px] text-ink-3">{caseId ? "Ask about this case or the app" : "Ask me about this app"}</div>
        </div>
        <button type="button" onClick={onHide} className="cursor-pointer rounded px-1.5 py-0.5 text-[13px] text-ink-3 hover:bg-hover hover:text-ink">
          Hide
        </button>
        <button type="button" onClick={onClose} aria-label="Close chat" className="cursor-pointer rounded p-1 text-ink-3 hover:bg-hover hover:text-ink">
          <X className="size-4" aria-hidden />
        </button>
      </header>

      <div ref={list} role="log" aria-live="polite" className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-3">
        <div className="max-w-[90%] self-start rounded-xl rounded-bl-sm bg-raised px-3 py-2 text-[14px] leading-snug">
          Hi! I can explain what the checks found, look up a value, or show you around. I can't decide anything for you, though.
        </div>
        {lines.map((l) =>
          l.from === "you" ? (
            <motion.div key={l.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="max-w-[85%] self-end whitespace-pre-line rounded-xl rounded-br-sm bg-accent px-3 py-2 text-[14px] font-medium leading-snug text-white">
              {l.text}
            </motion.div>
          ) : (
            <motion.div key={l.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="max-w-[92%] self-start">
              <div className="whitespace-pre-line rounded-xl rounded-bl-sm bg-raised px-3 py-2 text-[14px] leading-snug">{l.text}</div>
              {l.reply && <SourceNote reply={l.reply} />}
              {!!l.reply?.links.length && (
                <div className="mt-1 flex flex-wrap gap-x-3">
                  {l.reply.links.map((a) => (
                    <Link key={a.to} to={a.to} className="link text-[13px]">
                      {a.label}
                    </Link>
                  ))}
                </div>
              )}
            </motion.div>
          ),
        )}
        {busy && (
          <div role="status" aria-label="Doc is thinking" className="flex w-fit gap-1 self-start rounded-xl rounded-bl-sm bg-raised px-3 py-3">
            {[0, 0.15, 0.3].map((d) => (
              <motion.span key={d} className="size-1.5 rounded-full bg-ink-3" animate={{ y: [0, -4, 0] }} transition={{ duration: 0.7, repeat: Infinity, delay: d }} />
            ))}
          </div>
        )}
        {!busy && chips.length > 0 && (
          <div className="fade-in mt-0.5 flex flex-wrap gap-1.5">
            {chips.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => ask(c)}
                className="cursor-pointer rounded-full border-2 border-[var(--color-edge)] bg-panel px-3 py-1 font-medium text-[13px] text-ink-2 transition-colors duration-150 hover:border-accent hover:text-ink"
              >
                {c}
              </button>
            ))}
          </div>
        )}
      </div>

      <form
        className="flex shrink-0 gap-1.5 border-t border-line p-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
        }}
      >
        <input
          ref={input}
          value={draft}
          maxLength={500}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask Doc a question"
          aria-label="Ask Doc a question"
          className="h-9 min-w-0 flex-1 rounded-xl border-2 border-[var(--color-edge)] bg-panel px-2.5 text-[14px] text-ink placeholder:text-ink-3"
        />
        <button type="submit" disabled={busy || !draft.trim()} aria-label="Send" className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full border-2 border-[var(--color-edge)] bg-accent text-white transition-colors duration-150 hover:bg-accent-dark disabled:cursor-default disabled:opacity-40">
          <Send className="size-4" aria-hidden />
        </button>
      </form>
    </motion.section>
  );
}

/** Doc, the guide. Click it to chat, drag it anywhere, or hide it. */
export function Assistant({ floating = true }: { floating?: boolean }) {
  const still = useReducedMotion();
  const match = useMatch("/cases/:caseId/*");
  const location = useLocation();
  const caseId = match?.params.caseId;
  const tab = match?.params["*"] ?? "";
  const [hidden, setHidden] = useState(readHidden);
  const [bubble, setBubble] = useState<string | null>(null);
  const [override, setOverride] = useState<Mood | null>(null);
  const [wander, setWander] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
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
  const mood = chatBusy ? "thinking" : (override ?? now.mood);
  const findingId = new URLSearchParams(location.search).get("finding");
  const hide = () => {
    setChatOpen(false);
    setHidden(true);
    saveHidden(true);
  };

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
      onOpenDocChat(() => {
        setHidden(false);
        saveHidden(false);
        setChatOpen(true);
      }),
    [],
  );

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
    if (still || hidden || chatOpen || !floating) return;
    let timer: number;
    const stroll = () => {
      timer = window.setTimeout(() => {
        setWander(Math.round(Math.random() * 70));
        stroll();
      }, 14000 + Math.random() * 16000);
    };
    stroll();
    return () => window.clearTimeout(timer);
  }, [still, hidden, chatOpen, floating]);

  // The map's zoom buttons sit in the bottom-left corner.
  const left = tab === "graph" ? 64 : 12;

  const chat = (
    <AnimatePresence>
      {chatOpen && (
        <ChatPanel
          caseId={caseId}
          findingId={findingId}
          suggestions={starters(tab, !!findingId, !!caseId, c.data?.case.status === "complete")}
          onClose={() => setChatOpen(false)}
          onHide={hide}
          onThinking={setChatBusy}
        />
      )}
    </AnimatePresence>
  );

  if (hidden) {
    if (!floating) return chat;
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

  if (!floating) return chat;

  return (
    <>
      {chat}
      {!chatOpen && (
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
                  className="absolute bottom-[calc(100%-6px)] left-8 w-56 rounded-2xl rounded-bl-sm border-2 border-[var(--color-edge)] bg-panel px-3 py-2 pr-7 text-[14px] font-medium leading-snug text-ink shadow-[3px_3px_0_var(--color-edge)] sm:bottom-14 sm:left-[calc(100%+2px)]"
                >
                  {bubble}
                  <button
                    type="button"
                    aria-label="Hide Doc"
                    title="Hide Doc"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={hide}
                    className="absolute right-1.5 top-1.5 cursor-pointer rounded p-0.5 text-ink-3 hover:bg-hover hover:text-ink"
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
            <motion.button
              type="button"
              aria-label="Chat with Doc"
              title="Chat with Doc. It explains what the checks found, and it doesn't decide anything."
              whileHover={still ? undefined : { scale: 1.06, rotate: -2 }}
              whileTap={still ? undefined : { scale: 0.94 }}
              onClick={() => {
                if (dragged.current) {
                  dragged.current = false;
                  return;
                }
                setBubble(null);
                setChatOpen(true);
              }}
              className="block cursor-[inherit] rounded-2xl p-1"
            >
              <Mascot mood={mood} size={68} />
            </motion.button>
          </motion.div>
        </motion.div>
      )}
    </>
  );
}

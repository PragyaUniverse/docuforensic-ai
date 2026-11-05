import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ShieldCheck, ShieldX } from "lucide-react";
import { api } from "@/api";
import type { AuditEntry, AuditVerification } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { PageHeading } from "@/components/Shell";
import { cn, fmtTime, humanize } from "@/lib/utils";

function Row({ e, bad, afterBad }: { e: AuditEntry; bad: boolean; afterBad: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (bad) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [bad]);
  return (
    <li ref={ref} className={cn("relative border-b border-line", bad && "bg-man-dim", afterBad && "opacity-55")}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="grid w-full cursor-pointer grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2 text-left hover:bg-hover"
      >
        <span className={cn("font-mono text-[13px]", bad ? "font-medium text-man" : "text-ink-3")}>#{e.seq}</span>
        <span className="min-w-0">
          <span className="block truncate text-[14px] text-ink">
            {humanize(e.action.replace(/^stage\./, "step: ").replace("finding.review", "review decision"))}
            {e.actor.startsWith("reviewer:") && <span className="ml-2 text-[13px] text-ink-3">by {e.actor.slice(9)}</span>}
          </span>
        </span>
        <span className="flex items-center gap-2 font-mono text-[13px] text-ink-3">
          <span className="hidden lg:inline">{fmtTime(e.ts)}</span>
          <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} aria-hidden />
        </span>
      </button>
      {open && (
        <div className="border-t border-line bg-ground px-4 py-2">
          <div className="mb-1 code break-all text-ink-3">
            prev {e.prev_hash}
            <br />
            hash {e.entry_hash}
          </div>
          <pre className="max-h-64 overflow-auto code whitespace-pre-wrap break-words text-ink-2">{JSON.stringify(e.payload, null, 2)}</pre>
        </div>
      )}
    </li>
  );
}

function Verdict({ v }: { v: AuditVerification }) {
  const ok = v.ok;
  const Icon = ok ? ShieldCheck : ShieldX;
  return (
    <motion.div
      key={`${ok}-${v.first_bad_seq}-${v.head_hash}`}
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      role="status"
      className={cn("flex items-start gap-3 rounded-md border p-4", ok ? "border-ok bg-ok-dim" : "border-man bg-man-dim")}
    >
      <Icon className={cn("size-6 shrink-0", ok ? "text-ok" : "text-man")} aria-hidden />
      <div className="min-w-0">
        <div className={cn("text-[18px] font-semibold leading-tight", ok ? "text-ok" : "text-man")}>
          {ok ? "Nothing has been changed" : `Entry #${v.first_bad_seq} was changed after it was written`}
        </div>
        <p className="mt-1 text-ink-2">
          {ok
            ? `We rechecked all ${v.entries_checked} entries, and each still matches what was recorded.`
            : "What's saved no longer matches what was originally recorded."}
        </p>
        {ok ? (
          <p className="code mt-1 break-all text-ink-3">Fingerprint {v.head_hash ?? "n/a"}</p>
        ) : (
          <p className="mt-1 text-[14px] text-ink-3">Anything after this entry can't be trusted until it's looked into.</p>
        )}
      </div>
    </motion.div>
  );
}

export function AuditScreen() {
  const { caseId = "" } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["audit", caseId], queryFn: () => api.audit(caseId) });
  const [result, setResult] = useState<AuditVerification | null>(null);
  const [tampered, setTampered] = useState<number | null>(null);

  const verify = useMutation({ mutationFn: () => api.verifyAudit(caseId), onSuccess: setResult });
  const tamper = useMutation({
    mutationFn: () => api.tamperAudit(),
    onSuccess: (r) => {
      setTampered(r.tampered_seq);
      setResult(null);
      qc.invalidateQueries({ queryKey: ["audit", caseId] });
    },
  });
  const restore = useMutation({
    mutationFn: () => api.restoreAudit(),
    onSuccess: () => {
      setTampered(null);
      setResult(null);
      qc.invalidateQueries({ queryKey: ["audit", caseId] });
    },
  });

  const bad = result && !result.ok ? result.first_bad_seq : null;
  const err = verify.error ?? tamper.error ?? restore.error;

  return (
    <div className="flex h-full flex-col">
      <PageHeading
        title="History"
        actions={
          <>
            <Button variant="primary" onClick={() => verify.mutate()} disabled={verify.isPending}>
              Verify integrity
            </Button>
            {tampered === null ? (
              <Button onClick={() => tamper.mutate()} disabled={tamper.isPending}>
                Try editing an entry
              </Button>
            ) : (
              <Button onClick={() => restore.mutate()} disabled={restore.isPending}>
                Undo the edit to entry #{tampered}
              </Button>
            )}
          </>
        }
      >
        Everything that happened on this case, in order. Each entry is locked to the one before it, so any later edit gets noticed.
      </PageHeading>

      <div className="flex min-h-0 flex-1 flex-col gap-4 p-6">
        {err && <ErrorState title="That action failed" error={err} className="border border-line" />}
        {tampered !== null && !result && (
          <p role="status" className="flex items-center gap-2 rounded-md border border-inc bg-inc-dim px-3 py-2 text-[14px] text-inc">
            Entry #{tampered} was just edited directly in the database, as a test. Press Verify integrity to see if it gets noticed.
          </p>
        )}
        <AnimatePresence mode="wait">{result && <Verdict v={result} />}</AnimatePresence>
        {bad !== null && q.data && !q.data.some((e) => e.seq === bad) && (
          <p className="text-[13px] text-ink-2">
            Entry #{bad} belongs to another case in the same chain, so it is not listed below. Verification covers the whole chain.
          </p>
        )}
        <div className="min-h-[260px] flex-1 overflow-y-auto border-x border-t border-line bg-panel">
          {q.isLoading && <Loading label="Loading history" />}
          {q.isError && <ErrorState title="The history could not load" error={q.error} onRetry={() => q.refetch()} />}
          {q.data?.length === 0 && <Empty title="Nothing has happened on this case yet" />}
          <ol>
            {q.data?.map((e) => (
              <Row key={e.seq} e={e} bad={bad === e.seq} afterBad={bad !== null && e.seq > bad} />
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}

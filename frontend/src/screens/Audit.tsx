import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Hammer, Link as LinkIcon, RotateCcw, ShieldCheck, ShieldX, Undo2 } from "lucide-react";
import { api } from "@/api";
import type { AuditEntry, AuditVerification } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { PageHeading } from "@/components/Shell";
import { cn, fmtTime, shortHash } from "@/lib/utils";

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
        <span className={cn("font-mono text-xs", bad ? "font-medium text-man" : "text-ink-3")}>#{e.seq}</span>
        <span className="min-w-0">
          <span className="block truncate text-[13px] text-ink">
            {e.action}
            <span className="ml-2 font-mono text-[11px] text-ink-3">{e.actor}</span>
          </span>
          <span className="flex flex-wrap items-center gap-1 font-mono text-[11px] text-ink-3">
            <span title={e.prev_hash}>{shortHash(e.prev_hash, 10)}</span>
            <LinkIcon className="size-2.5" aria-hidden />
            <span className={bad ? "text-man" : "text-ink-2"} title={e.entry_hash}>
              {shortHash(e.entry_hash, 10)}
            </span>
          </span>
        </span>
        <span className="flex items-center gap-2 font-mono text-[11px] text-ink-3">
          <span className="hidden lg:inline">{fmtTime(e.ts)}</span>
          <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} aria-hidden />
        </span>
      </button>
      {open && (
        <div className="border-t border-line bg-ground px-4 py-2">
          <div className="mb-1 break-all font-mono text-[11px] text-ink-3">
            prev {e.prev_hash}
            <br />
            hash {e.entry_hash}
          </div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[11.5px] text-ink-2">{JSON.stringify(e.payload, null, 2)}</pre>
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
      className={cn("flex items-start gap-4 border-2 p-4", ok ? "border-ok bg-ok-dim" : "border-man bg-man-dim")}
    >
      <Icon className={cn("size-9 shrink-0", ok ? "text-ok" : "text-man")} aria-hidden />
      <div className="min-w-0">
        <div className={cn("display text-[22px] leading-tight", ok ? "text-ok" : "text-man")}>
          {ok ? "Chain intact" : `Chain broken at entry #${v.first_bad_seq}`}
        </div>
        <p className="mt-1 text-ink-2">
          {ok
            ? `All ${v.entries_checked} entries recomputed and matched their stored hashes.`
            : v.reason ?? "A stored entry no longer matches its hash."}
        </p>
        <p className="mt-1 break-all font-mono text-[11px] text-ink-3">
          {ok ? `head ${v.head_hash ?? "n/a"}` : `${v.entries_checked} entries checked before stopping. Entries after #${v.first_bad_seq} can no longer be trusted.`}
        </p>
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
        eyebrow="Audit trail · hash chain"
        title="Every action, linked to the one before it"
        actions={
          <>
            <Button variant="primary" onClick={() => verify.mutate()} disabled={verify.isPending}>
              <ShieldCheck aria-hidden /> Verify integrity
            </Button>
            {tampered === null ? (
              <Button variant="danger" onClick={() => tamper.mutate()} disabled={tamper.isPending}>
                <Hammer aria-hidden /> Tamper demo
              </Button>
            ) : (
              <Button onClick={() => restore.mutate()} disabled={restore.isPending}>
                <Undo2 aria-hidden /> Restore entry #{tampered}
              </Button>
            )}
          </>
        }
      >
        Each entry stores the hash of the previous one. Editing any stored record breaks every link after it, and verification finds the first break.
      </PageHeading>

      <div className="flex min-h-0 flex-1 flex-col gap-4 p-6">
        {err && <ErrorState title="That action failed" error={err} className="border border-line" />}
        {tampered !== null && !result && (
          <p role="status" className="flex items-center gap-2 border border-inc bg-inc-dim px-3 py-2 text-[13px] text-inc">
            <RotateCcw className="size-3.5" aria-hidden />
            Demonstration: the stored payload of entry #{tampered} was edited directly, without recomputing its hash. Run Verify integrity.
          </p>
        )}
        <AnimatePresence mode="wait">{result && <Verdict v={result} />}</AnimatePresence>
        {bad !== null && q.data && !q.data.some((e) => e.seq === bad) && (
          <p className="text-[13px] text-ink-2">
            Entry #{bad} belongs to another case in the same chain, so it is not listed below. Verification covers the whole chain.
          </p>
        )}
        <div className="min-h-[260px] flex-1 overflow-y-auto border-x border-t border-line bg-panel">
          {q.isLoading && <Loading label="Loading audit entries" />}
          {q.isError && <ErrorState title="Audit entries could not load" error={q.error} onRetry={() => q.refetch()} />}
          {q.data?.length === 0 && <Empty title="No audit entries for this case yet" />}
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

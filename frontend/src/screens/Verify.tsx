import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { FileCheck2, FileQuestion, FileWarning, FileX2, ShieldCheck, ShieldAlert, Upload } from "lucide-react";
import { featuresApi, type ReportCheck } from "@/api/features";
import { PageHeading } from "@/components/Shell";
import { Button } from "@/components/ui/button";
import { cn, fmtTime } from "@/lib/utils";

const LOOK: Record<ReportCheck["result"], { title: string; icon: typeof FileCheck2; tone: string; glow: string }> = {
  original: { title: "Original report", icon: FileCheck2, tone: "text-ok border-ok/50", glow: "glow-cyan" },
  modified: { title: "Changed since it was issued", icon: FileWarning, tone: "text-man border-man/50", glow: "glow-red" },
  unknown: { title: "Not a report from this system", icon: FileQuestion, tone: "text-inc border-inc/50", glow: "glow-amber" },
  not_pdf: { title: "Not a PDF", icon: FileX2, tone: "text-inc border-inc/50", glow: "glow-amber" },
};

function Result({ r }: { r: ReportCheck }) {
  const look = LOOK[r.result];
  const Icon = look.icon;
  return (
    <motion.section
      key={r.sha256}
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      className={cn("panel flex flex-col gap-4 p-6", look.glow)}
      aria-live="polite"
    >
      <div className="flex items-start gap-4">
        <span className={cn("flex size-12 shrink-0 items-center justify-center rounded-xl border", look.tone)}>
          <Icon className="size-6" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="text-[20px] font-semibold text-ink">{look.title}</h2>
          <p className="mt-1 text-ink-2">{r.message}</p>
        </div>
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[13.5px]">
        <dt className="mono-label self-center">File</dt>
        <dd className="font-mono text-ink">{r.filename}</dd>
        <dt className="mono-label self-center">SHA-256</dt>
        <dd className="break-all font-mono text-[12px] text-ink-2">{r.sha256}</dd>
        {r.case_name && (
          <>
            <dt className="mono-label self-center">Case</dt>
            <dd>
              <Link to={`/cases/${r.case_id}`} className="link">
                {r.case_name}
              </Link>
            </dd>
          </>
        )}
        {r.issued_at && (
          <>
            <dt className="mono-label self-center">Issued</dt>
            <dd className="text-ink">
              {fmtTime(r.issued_at)}, history entry #{r.entry_seq}
              {r.variant === "redacted" && " (redacted copy)"}
            </dd>
          </>
        )}
        {r.chain && r.result !== "not_pdf" && (
          <>
            <dt className="mono-label self-center">History</dt>
            <dd className={cn("flex items-center gap-1.5", r.chain.ok ? "text-ok" : "text-man")}>
              {r.chain.ok ? <ShieldCheck className="size-4" aria-hidden /> : <ShieldAlert className="size-4" aria-hidden />}
              {r.chain.ok
                ? `Intact: all ${r.chain.entries_checked} entries check out.`
                : `Changed at entry #${r.chain.first_bad_seq}: ${r.chain.reason}.`}
            </dd>
          </>
        )}
      </dl>
      <p className="text-[12.5px] text-ink-3">
        This proves whether the file is byte for byte the one the system issued. It doesn't make the report's findings right: they still
        need a person.
      </p>
    </motion.section>
  );
}

/** Verify this report: is a dossier PDF exactly as this system issued it? */
export function VerifyScreen() {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const check = useMutation({ mutationFn: (f: File) => featuresApi.verifyReport(f) });
  const pick = (files: FileList | null) => {
    const f = files?.[0];
    if (f) check.mutate(f);
  };

  return (
    <div className="mx-auto flex max-w-[860px] flex-col gap-6 pb-16">
      <PageHeading eyebrow="Report authenticity" title="Verify a report">
        Upload a dossier PDF to check it's exactly as this system issued it. Every report's fingerprint is written into the tamper-evident
        history when it's downloaded, so a change of even one byte shows.
      </PageHeading>
      <div className="flex flex-col gap-6 px-6">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            pick(e.dataTransfer.files);
          }}
          className={cn(
            "panel scanline relative flex cursor-pointer flex-col items-center gap-3 overflow-hidden border-dashed p-10 text-center transition-[box-shadow,border-color]",
            over ? "border-accent glow-cyan" : "hover:border-line-strong",
          )}
        >
          <span className="flex size-14 items-center justify-center rounded-2xl border border-[rgba(var(--color-glow),0.35)] bg-[rgba(var(--color-glow),0.06)] text-accent">
            <Upload className="size-6" aria-hidden />
          </span>
          <span className="text-[16px] font-medium text-ink">{check.isPending ? "Checking the report…" : "Drop a dossier PDF here"}</span>
          <span className="text-[13.5px] text-ink-3">or click to choose one. Reports come from the Report tab of any investigation.</span>
          <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(e) => pick(e.target.files)} />
          {check.isPending && (
            <motion.span
              aria-hidden
              className="absolute inset-x-0 top-0 h-0.5 bg-accent"
              initial={{ scaleX: 0 }}
              animate={{ scaleX: [0, 1, 0] }}
              transition={{ duration: 1.2, repeat: Infinity }}
              style={{ transformOrigin: "0% 50%" }}
            />
          )}
        </label>
        {check.isError && (
          <p role="alert" className="text-man">
            The report couldn't be checked: {(check.error as Error).message}
          </p>
        )}
        <AnimatePresence mode="wait">{check.data && <Result r={check.data} />}</AnimatePresence>
        {check.data && (
          <Button onClick={() => input.current?.click()} className="self-start">
            Check another report
          </Button>
        )}
      </div>
    </div>
  );
}

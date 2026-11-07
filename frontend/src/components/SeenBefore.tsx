import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, AtSign, CreditCard, Fingerprint, IdCard, ImageOff, Landmark, PenLine, Phone, Repeat2, UserRound } from "lucide-react";
import type { BBox } from "@/api/types";
import { featuresApi, type SeenElement, type SeenGroup, type SeenPlace } from "@/api/features";
import { cn } from "@/lib/utils";

const ICON: Record<SeenElement["kind"], typeof Phone> = {
  photo: UserRound, signature: PenLine, phone: Phone, email: AtSign, bank_account_number: Landmark, pan_number: CreditCard, id_number: IdCard,
};

const DOC_NAME: Record<string, string> = {
  application_form: "Application form", id_proof: "ID document", salary_slip: "Salary slip", bank_statement: "Bank statement",
  address_proof: "Address proof", declaration: "Declaration",
};

/** A region of a page image, cut out in the browser, so both sides show the real source pixels. */
function RegionThumb({ url, bbox, label }: { url: string; bbox: BBox; label: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const c = canvas.current;
      if (!c) return;
      const pad = 10;
      const x0 = Math.max(0, bbox.x0 - pad);
      const y0 = Math.max(0, bbox.y0 - pad);
      const w = Math.min(img.naturalWidth - x0, bbox.x1 - bbox.x0 + pad * 2);
      const h = Math.min(img.naturalHeight - y0, bbox.y1 - bbox.y0 + pad * 2);
      const scale = Math.min(1, 220 / Math.max(w, h));
      c.width = Math.max(1, Math.round(w * scale));
      c.height = Math.max(1, Math.round(h * scale));
      c.getContext("2d")?.drawImage(img, x0, y0, w, h, 0, 0, c.width, c.height);
    };
    img.onerror = () => setFailed(true);
    img.src = url;
  }, [url, bbox]);
  if (failed)
    return (
      <div className="flex h-24 items-center justify-center rounded-md bg-raised text-ink-3">
        <ImageOff className="size-4" aria-hidden />
      </div>
    );
  return <canvas ref={canvas} role="img" aria-label={label} className="mx-auto max-h-28 max-w-full rounded-md bg-white object-contain" />;
}

function viewer(caseId: string, p: SeenPlace) {
  const q = new URLSearchParams({ doc: p.doc_id, page: String(p.page) });
  if (p.field_id) q.set("field", p.field_id);
  return `/cases/${caseId}/viewer?${q}`;
}

function Element({ e, caseId, otherCaseId }: { e: SeenElement; caseId: string; otherCaseId: string }) {
  const Icon = ICON[e.kind];
  const image = e.kind === "photo" || e.kind === "signature";
  return (
    <li className="rounded-lg border border-line bg-ground/60 p-3">
      <div className="flex items-start gap-2.5">
        <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-md border", e.strong ? "border-man/50 text-man" : "border-inc/50 text-inc")}>
          <Icon className="size-3.5" aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-medium leading-tight text-ink">{e.label}</span>
          <span className="mt-0.5 block font-mono text-[11.5px] text-ink-3">
            {e.value && <span className="mr-2 text-ink-2">{e.value}</span>}
            {image ? `${Math.round(e.similarity * 100)}% image match` : "exact match"}
          </span>
        </span>
      </div>
      {image && (
        <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
          <RegionThumb url={featuresApi.pageImageUrl(caseId, e.here.doc_id, e.here.page)} bbox={e.here.bbox} label={`${e.label} on this application`} />
          <Repeat2 className="size-4 text-man" aria-hidden />
          <RegionThumb url={featuresApi.pageImageUrl(otherCaseId, e.there.doc_id, e.there.page)} bbox={e.there.bbox} label={`${e.label} on the other application`} />
        </div>
      )}
      <div className="mt-2 flex flex-col gap-0.5 text-[12.5px]">
        <Link to={viewer(caseId, e.here)} className="link w-fit">
          Here: {DOC_NAME[e.here.doc_type ?? ""] ?? e.here.filename}, page {e.here.page + 1}
        </Link>
        <Link to={viewer(otherCaseId, e.there)} className="link w-fit">
          There: {DOC_NAME[e.there.doc_type ?? ""] ?? e.there.filename}, page {e.there.page + 1}
        </Link>
      </div>
    </li>
  );
}

function Group({ g, caseId, index }: { g: SeenGroup; caseId: string; index: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.25 }}
      className={cn("panel flex flex-col gap-3 p-4", !g.same_applicant && "border-man/40")}
    >
      <header className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <Link to={`/cases/${g.case_id}`} className="group flex items-center gap-1 font-medium text-ink hover:text-accent">
            {g.case_name}
            <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
          </Link>
          <div className="text-[12.5px] text-ink-3">
            {g.applicant_there ? `Applicant: ${g.applicant_there}` : "Applicant name not read"}
          </div>
        </div>
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 font-mono text-[10.5px] tracking-[0.1em]",
            g.same_applicant ? "border-obs/50 text-obs" : "border-man/50 text-man",
          )}
        >
          {g.same_applicant ? "SAME NAME" : "DIFFERENT NAME"}
        </span>
      </header>
      <ul className="flex flex-col gap-2">
        {g.elements.map((e, i) => (
          <Element key={i} e={e} caseId={caseId} otherCaseId={g.case_id} />
        ))}
      </ul>
    </motion.article>
  );
}

/** Details from this application that also appear in another application on this system. */
export function SeenBefore({ caseId }: { caseId: string }) {
  const q = useQuery({ queryKey: ["seen-before", caseId], queryFn: () => featuresApi.seenBefore(caseId), refetchInterval: 15_000 });
  const data = q.data;
  const groups = data?.groups ?? [];
  return (
    <section data-tour="seen-before" aria-label="Seen before">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="mono-label flex items-center gap-2">
            <Fingerprint className="size-3.5 text-accent" aria-hidden /> Seen before
          </div>
          <p className="mt-1 max-w-[80ch] text-[13.5px] text-ink-3">
            Phone, email, bank account, PAN, ID number, photo and signature compared with every other application on this system.
          </p>
        </div>
        {data && <span className="font-mono text-[11px] text-ink-3">{data.checked_cases} other application{data.checked_cases === 1 ? "" : "s"} checked</span>}
      </div>
      {q.isLoading ? (
        <div className="mt-4 h-20 animate-pulse rounded-lg bg-raised" />
      ) : q.isError ? (
        <p className="mt-4 text-[13.5px] text-man">The comparison couldn't load: {(q.error as Error).message}</p>
      ) : groups.length === 0 ? (
        <p className="mt-4 rounded-lg border border-line bg-ground/60 p-4 text-[14px] text-ink-2">
          {data?.checked_cases
            ? `Nothing from this application appears in the ${data.checked_cases} other application${data.checked_cases === 1 ? "" : "s"} on this system.`
            : "There are no other applications on this system to compare with yet."}
        </p>
      ) : (
        <>
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {groups.map((g, i) => (
              <Group key={g.case_id} g={g} caseId={caseId} index={i} />
            ))}
          </div>
          <p className="mt-3 text-[13px] text-ink-3">
            Repeated details can be innocent, such as a family sharing a phone or a joint account. They're for you to check, not a conclusion.
          </p>
        </>
      )}
    </section>
  );
}

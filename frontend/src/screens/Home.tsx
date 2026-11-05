import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "@/api";
import type { Case } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/ui/states";
import { Mascot } from "@/components/Mascot";
import { RiskPlate } from "@/components/StatusBadge";
import { openDocChat } from "@/lib/assistant";
import { fmtTime } from "@/lib/utils";

const EXAMPLES: Record<string, { title: string; text: string; emoji: string; tint: string }> = {
  case_a_clean: { title: "A clean application", text: "Everything matches. This is what a normal result looks like.", emoji: "✅", tint: "bg-lime" },
  case_b_visual: { title: "An altered salary slip", text: "A changed figure, a pasted photo and a copied signature.", emoji: "💸", tint: "bg-pink" },
  case_c_crossdoc: { title: "Documents that disagree", text: "Each looks fine alone, but names, dates and amounts conflict.", emoji: "🧩", tint: "bg-sky" },
  case_d_pdf: { title: "An edited PDF", text: "The number you see isn't the number stored in the file.", emoji: "📄", tint: "bg-sun" },
  unsupported_files: { title: "Files it can't read", text: "Corrupt and unsupported files, to show how errors are handled.", emoji: "🚫", tint: "bg-raised" },
};

function CaseRow({ c }: { c: Case }) {
  return (
    <li>
      <Link to={`/cases/${c.id}`} className="flex items-center gap-3 border-b border-line px-4 py-3 transition-colors duration-150 last:border-b-0 hover:bg-hover">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{c.name}</div>
          <div className="truncate text-[13px] text-ink-3">{fmtTime(c.created_at)}</div>
        </div>
        <RiskPlate risk={c.risk_level} assessed={c.status === "complete"} />
      </Link>
    </li>
  );
}

export function HomeScreen() {
  const nav = useNavigate();
  const [name, setName] = useState("");
  const demos = useQuery({ queryKey: ["demo-cases"], queryFn: () => api.demoCases() });
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api.listCases() });
  const load = useMutation({
    mutationFn: (key: string) => api.loadDemoCase(key),
    onSuccess: (c) => nav(`/cases/${c.id}`),
  });
  const create = useMutation({
    mutationFn: () => api.createCase(name.trim() || "Untitled case"),
    onSuccess: (c) => nav(`/cases/${c.id}`),
  });

  return (
    <div className="mx-auto flex max-w-[860px] flex-col gap-10 px-6 py-10">
      <section className="rise overflow-hidden card p-6">
        <div className="flex items-start gap-5">
          <div className="min-w-0 flex-1">
            <h1 className="text-[34px] leading-[1.05] sm:text-[40px]">
              check the docs.
              <br />
              find the <span className="marker">receipts</span>. 🧾
            </h1>
            <p className="mt-3 text-[16px] text-ink-2">
              Drop in every document from one application. I'm Doc, and I'll read them, compare them, and flag anything
              that looks off, with the proof. You make the final call ✌️
            </p>
          </div>
          <button type="button" onClick={openDocChat} title="Ask Doc a question" aria-label="Ask Doc a question" className="hidden shrink-0 cursor-pointer sm:block">
            <Mascot mood={create.isPending || load.isPending ? "thinking" : "hello"} size={104} />
          </button>
        </div>
        <form
          className="mt-4 flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name this case, e.g. Loan application 1042"
            aria-label="Case name"
            className="h-10 min-w-[240px] flex-1 rounded-xl border-2 border-[var(--color-edge)] bg-panel px-3 text-ink transition-shadow duration-150 placeholder:text-ink-3 focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_22%,transparent)] focus:outline-none"
          />
          <Button variant="primary" type="submit" disabled={create.isPending}>
            Start a case →
          </Button>
        </form>
        {create.isError && <ErrorState title="Could not create the case" error={create.error} />}
        <p className="mt-2 text-[13px] text-ink-3">
          Only use documents you're allowed to process. Not sure where to begin?{" "}
          <button type="button" className="link cursor-pointer" onClick={openDocChat}>
            Ask Doc
          </button>
        </p>
      </section>

      <section aria-labelledby="demo-h">
        <h2 id="demo-h" className="text-[22px]">
          or try an example 👇
        </h2>
        <p className="mt-0.5 text-[14px] text-ink-3">All example documents are made up, with fictional people.</p>
        {demos.isLoading && <Loading label="Loading examples" />}
        {demos.isError && <ErrorState title="Examples are unavailable" error={demos.error} onRetry={() => demos.refetch()} />}
        <ul className="mt-4 grid gap-4 sm:grid-cols-2">
          {demos.data?.map((d, i) => {
            const copy = EXAMPLES[d.key] ?? { title: d.name, text: d.description, emoji: "📁", tint: "bg-raised" };
            const busy = load.isPending && load.variables === d.key;
            return (
              <li key={d.key} className="rise" style={{ "--i": i } as React.CSSProperties}>
                <button
                  type="button"
                  disabled={load.isPending}
                  onClick={() => load.mutate(d.key)}
                  className="card group flex h-full w-full cursor-pointer items-start gap-3 p-4 text-left transition-[transform,box-shadow] duration-150 hover:-translate-y-0.5 hover:rotate-[-0.6deg] hover:shadow-[6px_6px_0_var(--color-edge)] active:translate-x-1 active:translate-y-1 active:shadow-none disabled:cursor-default"
                >
                  <span aria-hidden className={`flex size-11 shrink-0 items-center justify-center rounded-xl border-2 border-[var(--color-edge)] text-[22px] ${copy.tint}`}>
                    {copy.emoji}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-[family-name:var(--font-display)] text-[17px] font-bold leading-tight">{copy.title}</span>
                    <span className="mt-0.5 block text-[14px] text-ink-2">{copy.text}</span>
                    <span className="mt-2 inline-flex items-center gap-1 text-[14px] font-semibold text-accent">
                      {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
                      {busy ? "opening" : "open"}
                      <span className="transition-transform duration-150 group-hover:translate-x-1">→</span>
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {load.isError && <ErrorState title="Could not open that example" error={load.error} />}
      </section>

      {!!cases.data?.length && (
        <section aria-labelledby="recent-h">
          <h2 id="recent-h" className="text-[17px] font-semibold">
            Recent cases
          </h2>
          <ul className="mt-3 overflow-hidden card">
            {cases.data.slice(0, 6).map((c) => (
              <CaseRow key={c.id} c={c} />
            ))}
          </ul>
        </section>
      )}
      {cases.isError && <ErrorState title="Cases are unavailable" error={cases.error} onRetry={() => cases.refetch()} />}
    </div>
  );
}

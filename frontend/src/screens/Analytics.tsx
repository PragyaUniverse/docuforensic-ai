import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { accountApi, type Analytics } from "@/api/account";
import { checkName } from "@/api/features";
import { PageHeading } from "@/components/Shell";
import { RiskPlate } from "@/components/StatusBadge";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { STATUS_META } from "@/lib/findings";
import type { FindingStatus, RiskLevel } from "@/api/types";
import { cn, humanize } from "@/lib/utils";
import { CountUp } from "@/components/Metrics";

const TONE: Record<FindingStatus, string> = { OBSERVATION: "bg-obs", INCONSISTENCY: "bg-inc", POTENTIAL_MANIPULATION: "bg-man" };

function Stat({ value, label, tone = "text-ink" }: { value: number; label: string; tone?: string }) {
  return (
    <div className="panel px-5 py-4 transition-shadow hover:glow-cyan">
      <div className="mono-label">{label}</div>
      <CountUp value={value} className={cn("mt-2 block font-mono text-[30px] font-semibold leading-none", tone)} />
    </div>
  );
}

function CountTable({ title, rows, note, bar = "bg-accent" }: { title: string; rows: [string, number, number?, string?][]; note?: string; bar?: string }) {
  const max = Math.max(1, ...rows.map((r) => r[1]));
  return (
    <section className="panel overflow-hidden">
      <h2 className="mono-label border-b border-line px-4 py-3 !text-ink-2">{title}</h2>
      {rows.length === 0 ? (
        <p className="px-4 py-3 text-[14px] text-ink-3">Nothing yet.</p>
      ) : (
        <ul className="py-1">
          {rows.map(([name, n, extra, tone]) => (
            <li key={name} className="px-4 py-2 text-[14px]">
              <div className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 text-ink-2">{name}</span>
                <span className="shrink-0 font-mono text-[13px] text-ink">
                  {n}
                  {!!extra && <span className="ml-2 text-ink-3">{extra} dismissed</span>}
                </span>
              </div>
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-line" aria-hidden>
                <div className={cn("grow-in h-full rounded-full", tone ?? bar)} style={{ width: `${(n / max) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
      {note && <p className="border-t border-line px-4 py-2.5 text-[13px] text-ink-3">{note}</p>}
    </section>
  );
}

/** Per check: what reviewers decided about its flags. Their own record on this system, not an accuracy figure. */
function FalseAlarms({ a }: { a: Analytics }) {
  const rows = (a.track_record ?? []).filter((r) => r.flagged > 0);
  const decided = rows.reduce((n, r) => n + r.decided, 0);
  return (
    <section className="panel overflow-hidden" aria-label="False-alarm tracker">
      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-line px-4 py-3">
        <div>
          <h2 className="mono-label !text-ink-2">False-alarm tracker</h2>
          <p className="mt-1 text-[13px] text-ink-3">
            How often reviewers confirmed or dismissed each check's flags. Each finding also shows its check's record here.
          </p>
        </div>
        <span className="font-mono text-[11px] text-ink-3">{decided} decision{decided === 1 ? "" : "s"} so far</span>
      </div>
      {rows.length === 0 ? (
        <p className="px-4 py-3 text-[14px] text-ink-3">No flags yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-[14px]">
            <thead>
              <tr className="text-left text-[12px] text-ink-3">
                <th className="px-4 py-2 font-normal">Check</th>
                <th className="px-2 py-2 text-right font-normal">Flags</th>
                <th className="px-2 py-2 text-right font-normal">Confirmed</th>
                <th className="px-2 py-2 text-right font-normal">Dismissed</th>
                <th className="w-[34%] px-4 py-2 font-normal">Dismissal rate</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 12).map((r) => (
                <tr key={r.check} className="border-t border-line">
                  <td className="px-4 py-2 text-ink-2">{checkName(r.check)}</td>
                  <td className="px-2 py-2 text-right font-mono text-[13px] text-ink">{r.flagged}</td>
                  <td className="px-2 py-2 text-right font-mono text-[13px] text-ok">{r.confirmed}</td>
                  <td className="px-2 py-2 text-right font-mono text-[13px] text-ink-3">{r.dismissed}</td>
                  <td className="px-4 py-2">
                    {r.dismissal_rate === null ? (
                      <span className="text-[12.5px] text-ink-3">
                        {r.decided === 0 ? "No decisions yet" : `Needs ${a.min_decisions} decisions (${r.decided} so far)`}
                      </span>
                    ) : (
                      <span className="flex items-center gap-2">
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line" aria-hidden>
                          <span
                            className={cn("grow-in block h-full rounded-full", r.dismissal_rate >= 0.5 ? "bg-inc" : "bg-ok")}
                            style={{ width: `${Math.round(r.dismissal_rate * 100)}%` }}
                          />
                        </span>
                        <span className={cn("w-10 text-right font-mono text-[12px]", r.dismissal_rate >= 0.5 ? "text-inc" : "text-ink-2")}>
                          {Math.round(r.dismissal_rate * 100)}%
                        </span>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="border-t border-line px-4 py-2.5 text-[13px] text-ink-3">
        A rate appears from {a.min_decisions} decisions up. A check reviewers often dismiss may need tuning, or more care when it fires.
      </p>
    </section>
  );
}

export function AnalyticsScreen() {
  const q = useQuery({ queryKey: ["analytics"], queryFn: () => accountApi.analytics() });
  if (q.isLoading) return <Loading label="Loading" className="h-full" />;
  if (q.isError) return <ErrorState title="Analytics could not load" error={q.error} onRetry={() => q.refetch()} />;
  const a = q.data!;
  if (a.cases === 0) return <Empty title="No cases yet" className="h-full">Totals appear here once you've checked some documents.</Empty>;
  const decided = (a.by_review.confirmed ?? 0) + (a.by_review.dismissed ?? 0) + (a.by_review.escalated ?? 0);
  return (
    <div className="mx-auto flex max-w-[1000px] flex-col gap-5 pb-10">
      <PageHeading eyebrow="Across all investigations" title="Analytics">Totals across every case on this system. These are counts, not accuracy figures.</PageHeading>
      <div className="flex flex-col gap-5 px-6">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat value={a.cases} label="Investigations" />
          <Stat value={a.documents} label="Evidence files" />
          <Stat value={(a.by_status.POTENTIAL_MANIPULATION ?? 0) + (a.by_status.INCONSISTENCY ?? 0)} label="Findings to review" tone="text-inc" />
          <Stat value={decided} label="Decisions made" tone="text-ok" />
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          <CountTable
            title="Findings by type"
            rows={(Object.keys(STATUS_META) as FindingStatus[]).map((s) => [STATUS_META[s].label, a.by_status[s] ?? 0, undefined, TONE[s]])}
          />
          <CountTable
            title="Reviewer decisions"
            rows={[
              ["Confirmed", a.by_review.confirmed ?? 0, undefined, "bg-ok"],
              ["Dismissed", a.by_review.dismissed ?? 0, undefined, "bg-ink-3"],
              ["Escalated", a.by_review.escalated ?? 0, undefined, "bg-inc"],
              ["Not reviewed yet", a.by_review.pending ?? 0, undefined, "bg-line-strong"],
            ]}
          />
          <CountTable title="Conflicts between documents" rows={a.by_discrepancy.map(([t, n]) => [humanize(t), n])} bar="bg-man" />
          <CountTable
            title="Which checks raise the most"
            rows={a.by_check.slice(0, 10).map((c) => [checkName(c.check), c.count, c.dismissed])}
            note="A check that reviewers often dismiss may be raising too many false alarms."
          />
        </div>
        <FalseAlarms a={a} />
        <section className="panel">
          <h2 className="mono-label border-b border-line px-4 py-3 !text-ink-2">Recent investigations</h2>
          <ul>
            {a.recent.map((c) => (
              <li key={c.id} className="border-b border-line last:border-b-0">
                <Link to={`/cases/${c.id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 hover:bg-hover">
                  <span className="min-w-0 font-medium">{c.name}</span>
                  <span className="flex items-center gap-4 text-[14px] text-ink-3">
                    {c.to_review > 0 && <span>{c.to_review} to review</span>}
                    <RiskPlate risk={c.risk_level as RiskLevel} assessed={c.status === "complete"} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

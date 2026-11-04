import { Check, CircleDashed, Minus, Clock, X } from "lucide-react";
import { useCapabilities } from "@/api/hooks";
import type { CapabilityMode } from "@/api/types";
import { ErrorState, Loading } from "@/components/ui/states";
import { PageHeading } from "@/components/Shell";
import { cn } from "@/lib/utils";

const MODES: Record<CapabilityMode, { label: string; text: string }> = {
  offline: { label: "Offline", text: "No external calls are made. Local forensics run in full. Explanations come from local rules or a local model." },
  demo_cache: { label: "Demo cache", text: "LLM text is replayed from recorded real runs, and each explanation is labelled as such. Forensic detectors still run live on the input." },
  live: { label: "Live LLM", text: "An LLM provider is answering. PII is redacted before any external call, and each finding shows which provider wrote its explanation." },
  deterministic: { label: "Deterministic", text: "No LLM is available. Forensics run in full, and explanations come from rules, labelled on every finding." },
};

const MATRIX: Record<string, { cls: string; icon: typeof Check }> = {
  implemented: { cls: "text-ok border-ok/60", icon: Check },
  partial: { cls: "text-inc border-inc/70", icon: CircleDashed },
  planned: { cls: "text-ink-2 border-line-strong", icon: Clock },
  unsupported: { cls: "text-ink-3 border-line-strong", icon: Minus },
};

export function CapabilitiesScreen() {
  const q = useCapabilities();
  if (q.isLoading) return <Loading label="Reading capabilities" className="h-full" />;
  if (q.isError) {
    return (
      <div>
        <PageHeading eyebrow="Capabilities & limitations" title="What this system can and cannot do" />
        <ErrorState title="The analysis service did not answer" error={q.error} onRetry={() => q.refetch()} />
      </div>
    );
  }
  const c = q.data!;
  const mode = MODES[c.mode] ?? { label: c.mode, text: "" };

  return (
    <div className="flex flex-col">
      <PageHeading eyebrow="Capabilities & limitations" title="What this system can and cannot do">
        Read live from the running service, not written by hand.
      </PageHeading>
      <div className="grid gap-6 p-6 xl:grid-cols-2">
        <section className="border border-line bg-panel p-4 xl:col-span-2">
          <div className="eyebrow">Current mode</div>
          <div className="display mt-1 text-[24px]">{mode.label}</div>
          <p className="mt-1 max-w-[80ch] text-ink-2">{mode.text}</p>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-ink-3">
            <span>LLM calls {c.llm_usage?.calls ?? 0}</span>
            <span>tokens {c.llm_usage?.tokens ?? 0}</span>
            {Object.entries(c.llm_usage?.by_provider ?? {}).map(([k, v]) => (
              <span key={k}>
                {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </span>
            ))}
          </div>
        </section>

        <section className="border border-line bg-panel">
          <h2 className="eyebrow border-b border-line px-4 py-2">LLM providers</h2>
          {c.providers.length === 0 ? (
            <p className="px-4 py-3 text-ink-3">No providers configured.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[13px]">
                <thead>
                  <tr className="eyebrow border-b border-line">
                    <th scope="col" className="px-4 py-1.5 font-medium">Provider</th>
                    <th scope="col" className="px-2 py-1.5 font-medium">Key</th>
                    <th scope="col" className="px-2 py-1.5 font-medium">Status</th>
                    <th scope="col" className="px-4 py-1.5 font-medium">Model</th>
                  </tr>
                </thead>
                <tbody>
                  {c.providers.map((p) => (
                    <tr key={p.provider} className="border-b border-line last:border-b-0">
                      <td className="px-4 py-1.5 font-medium">{p.provider}</td>
                      <td className="px-2 py-1.5 font-mono text-xs text-ink-2">{p.key_present ? "present" : "none"}</td>
                      <td className="px-2 py-1.5 font-mono text-xs text-ink-2">{p.status}</td>
                      <td className="px-4 py-1.5 font-mono text-xs text-ink-3">{p.model ?? "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="border border-line bg-panel">
          <h2 className="eyebrow border-b border-line px-4 py-2">Local tools</h2>
          {c.tools.length === 0 ? (
            <p className="px-4 py-3 text-ink-3">No tool status reported.</p>
          ) : (
            <ul>
              {c.tools.map((t) => (
                <li key={t.name} className="flex items-start gap-2 border-b border-line px-4 py-1.5 last:border-b-0">
                  {t.available ? <Check className="mt-0.5 size-3.5 shrink-0 text-ok" aria-hidden /> : <X className="mt-0.5 size-3.5 shrink-0 text-man" aria-hidden />}
                  <div className="min-w-0">
                    <div className="text-[13px]">
                      {t.name} <span className="sr-only">{t.available ? "available" : "not available"}</span>
                    </div>
                    {t.detail && <div className="font-mono text-[11px] text-ink-3">{t.detail}</div>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="border border-line bg-panel xl:col-span-2">
          <h2 className="eyebrow border-b border-line px-4 py-2">Capability matrix</h2>
          {c.matrix.length === 0 ? (
            <p className="px-4 py-3 text-ink-3">The service reported no capability matrix.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-[13px]">
                <tbody>
                  {c.matrix.map((m) => {
                    const s = MATRIX[m.status.toLowerCase()] ?? MATRIX.planned;
                    const Icon = s.icon;
                    return (
                      <tr key={m.capability} className="border-b border-line align-baseline last:border-b-0">
                        <td className="w-[34%] px-4 py-1.5 font-medium">{m.capability}</td>
                        <td className="w-32 px-2 py-1.5">
                          <span className={cn("inline-flex items-center gap-1 border px-1.5 py-0.5 font-mono text-[10.5px] uppercase", s.cls)}>
                            <Icon className="size-3" aria-hidden /> {m.status}
                          </span>
                        </td>
                        <td className="px-4 py-1.5 text-ink-2">{m.notes}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="border border-line bg-panel p-4 xl:col-span-2">
          <h2 className="eyebrow mb-2">Known limitations and expected false positives</h2>
          {c.limitations.length === 0 ? (
            <p className="text-ink-3">The service reported no limitations.</p>
          ) : (
            <ul className="list-disc space-y-1 pl-5 text-ink-2 marker:text-ink-3">
              {c.limitations.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

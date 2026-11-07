import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Download, Mail } from "lucide-react";
import { featuresApi } from "@/api/features";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/states";

/** A draft letter asking the issuer to confirm the doubtful values. The reviewer edits and sends it; the app never does. */
export function VerificationLetter({ findingId, open, onOpenChange }: { findingId: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [body, setBody] = useState("");
  const [copied, setCopied] = useState(false);
  const q = useQuery({
    queryKey: ["letter", findingId, lang],
    queryFn: () => featuresApi.letter(findingId, lang),
    enabled: open,
    staleTime: Infinity,
  });
  const letter = q.data;
  useEffect(() => setBody(letter?.body ?? ""), [letter]);
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1800);
    return () => window.clearTimeout(t);
  }, [copied]);

  const full = letter?.available ? `${lang === "hi" ? "प्रति" : "To"}: ${letter.to}\n${lang === "hi" ? "विषय" : "Subject"}: ${letter.subject}\n\n${body}` : "";
  const download = () => {
    const url = URL.createObjectURL(new Blob([full], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `verification_request_${lang}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Draft verification request" description="A letter asking the issuer to confirm the doubtful values" className="w-[min(760px,96vw)]">
        <div className="flex flex-col gap-4 p-5">
          <div className="flex flex-wrap items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-lg border border-line-strong text-accent">
              <Mail className="size-4" aria-hidden />
            </span>
            <p className="min-w-0 flex-1 text-[13.5px] text-ink-2">
              Written from this finding's evidence, asking only about the values the checks doubt. Edit it as you like. Nothing is sent
              from here.
            </p>
            <div role="group" aria-label="Letter language" className="flex overflow-hidden rounded-md border border-line-strong text-[13px]">
              {(["en", "hi"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={lang === v}
                  onClick={() => setLang(v)}
                  className={`cursor-pointer px-2.5 py-1 transition-colors ${lang === v ? "bg-accent text-white" : "text-ink-3 hover:bg-hover hover:text-ink"}`}
                >
                  {v === "hi" ? "हिंदी" : "English"}
                </button>
              ))}
            </div>
          </div>

          {q.isLoading ? (
            <Loading label="Drafting the letter" />
          ) : q.isError ? (
            <p role="alert" className="text-man">The letter couldn't be drafted: {(q.error as Error).message}</p>
          ) : letter && !letter.available ? (
            <p className="text-ink-2">{letter.message}</p>
          ) : letter ? (
            <>
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[14px]">
                <dt className="mono-label self-center">{lang === "hi" ? "प्रति" : "To"}</dt>
                <dd className="font-medium text-ink">{letter.to}</dd>
                <dt className="mono-label self-center">{lang === "hi" ? "विषय" : "Subject"}</dt>
                <dd className="text-ink">{letter.subject}</dd>
                <dt className="mono-label self-center">{lang === "hi" ? "दस्तावेज़" : "About"}</dt>
                <dd className="font-mono text-[13px] text-ink-2">{letter.about_document}</dd>
              </dl>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                aria-label="Letter text"
                rows={16}
                className="w-full resize-y rounded-md border border-line-strong bg-ground p-3 font-[inherit] text-[14px] leading-relaxed text-ink focus-glow"
              />
              <p className="text-[12.5px] text-ink-3">{letter.note}</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(full);
                      setCopied(true);
                    } catch {
                      setCopied(false);
                    }
                  }}
                >
                  {copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
                  {copied ? "Copied" : "Copy letter"}
                </Button>
                <Button onClick={download}>
                  <Download className="size-4" aria-hidden /> Download .txt
                </Button>
                {body !== letter.body && (
                  <Button onClick={() => setBody(letter.body ?? "")} className="ml-auto">
                    Undo my edits
                  </Button>
                )}
              </div>
            </>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

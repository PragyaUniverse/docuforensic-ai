import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useCaseDocuments, useFindings } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { ComparisonPanel } from "@/components/ComparisonPanel";
import { PageHeading } from "@/components/Shell";
import { findingLabels, sortFindings, spansDocuments } from "@/lib/findings";
import { humanize } from "@/lib/utils";

export function ConflictsScreen() {
  const { caseId = "" } = useParams();
  const f = useFindings(caseId);
  const { byId, fieldsById, isLoading } = useCaseDocuments(caseId);
  const crossList = useMemo(
    () => sortFindings((f.data ?? []).filter((x) => x.category === "cross_document" || spansDocuments(x, fieldsById))),
    [f.data, fieldsById],
  );
  const withinList = useMemo(
    () =>
      sortFindings(
        (f.data ?? []).filter((x) => x.category === "contextual" && x.related_field_ids.length >= 2 && !spansDocuments(x, fieldsById)),
      ),
    [f.data, fieldsById],
  );
  const labels = useMemo(() => findingLabels(f.data ?? []), [f.data]);
  const types = [...new Set(crossList.map((x) => x.discrepancy_type).filter(Boolean))] as string[];

  if (f.isLoading || isLoading) return <Loading label="Loading conflicts" className="h-full" />;
  if (f.isError) return <ErrorState title="Conflicts could not load" error={f.error} onRetry={() => f.refetch()} />;

  return (
    <div className="flex flex-col">
      <PageHeading eyebrow="Step 7 · Cross-document correlation" title="What only appears when documents are read together">
        Each conflict shows the original source regions side by side. {crossList.length} cross-document finding{crossList.length === 1 ? "" : "s"}
        {types.length > 0 && ` across ${types.length} discrepancy type${types.length === 1 ? "" : "s"}`}.
      </PageHeading>
      {types.length > 0 && (
        <div className="flex flex-wrap gap-1 border-b border-line px-6 py-2">
          {types.map((t) => (
            <span key={t} className="border border-line-strong px-1.5 py-0.5 font-mono text-[11px] text-ink-2">
              {humanize(t)}
            </span>
          ))}
        </div>
      )}
      {crossList.length + withinList.length === 0 ? (
        <Empty
          title="No conflicts recorded"
          action={
            <Button asChild size="sm">
              <Link to={`/cases/${caseId}/pipeline`}>Go to pipeline</Link>
            </Button>
          }
        >
          Either the investigation has not run, or the extracted values in these documents agree. Agreement between documents does not prove they are authentic.
        </Empty>
      ) : (
        <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-4 p-6">
          {crossList.map((x) => (
            <section key={x.id} className="border border-line bg-panel p-4">
              <ComparisonPanel caseId={caseId} finding={x} docs={byId} fieldsById={fieldsById} label={labels.get(x.id)} />
            </section>
          ))}
          {withinList.length > 0 && (
            <>
              <h2 className="eyebrow mt-4">Within a single document</h2>
              {withinList.map((x) => (
                <section key={x.id} className="border border-line bg-panel p-4">
                  <ComparisonPanel caseId={caseId} finding={x} docs={byId} fieldsById={fieldsById} label={labels.get(x.id)} />
                </section>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

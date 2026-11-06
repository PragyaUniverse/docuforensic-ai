import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useCaseDocuments, useFindings } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/ui/states";
import { ComparisonPanel } from "@/components/ComparisonPanel";
import { PageHeading } from "@/components/Shell";
import { findingLabels, sortFindings, spansDocuments } from "@/lib/findings";

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

  if (f.isLoading || isLoading) return <Loading label="Loading" className="h-full" />;
  if (f.isError) return <ErrorState title="This page could not load" error={f.error} onRetry={() => f.refetch()} />;

  return (
    <div className="flex flex-col">
      <PageHeading
        title="Compare documents"
        actions={
          crossList.length > 0 ? (
            <Button asChild>
              <Link to={`/cases/${caseId}/graph`}>See as a map</Link>
            </Button>
          ) : undefined
        }
      >
        Things that only show up when the documents are read together. Each one shows the original spots side by side.
      </PageHeading>
      {crossList.length + withinList.length === 0 ? (
        <Empty
          title="No conflicts found"
          action={
            <Button asChild size="sm">
              <Link to={`/cases/${caseId}`}>Go to overview</Link>
            </Button>
          }
        >
          Either the check hasn't run yet, or the documents agree with each other. Agreement doesn't prove they're genuine.
        </Empty>
      ) : (
        <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-4 p-6">
          {crossList.map((x, i) => (
            <section key={x.id} className="rise panel p-4" style={{ "--i": i } as React.CSSProperties}>
              <ComparisonPanel caseId={caseId} finding={x} docs={byId} fieldsById={fieldsById} label={labels.get(x.id)} />
            </section>
          ))}
          {withinList.length > 0 && (
            <>
              <h2 className="mt-4 text-[17px] font-semibold">Within a single document</h2>
              {withinList.map((x) => (
                <section key={x.id} className="panel p-4">
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

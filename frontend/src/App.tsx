import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { Empty, Loading } from "./components/ui/states";
import { HomeScreen } from "./screens/Home";
import { CaseScreen } from "./screens/Case";
import { PipelineScreen } from "./screens/Pipeline";
import { ViewerScreen } from "./screens/Viewer";
import { DataScreen } from "./screens/Data";
import { ConflictsScreen } from "./screens/Conflicts";
import { DossierScreen } from "./screens/Dossier";
import { AuditScreen } from "./screens/Audit";
import { CapabilitiesScreen } from "./screens/Capabilities";
import { AnalyticsScreen } from "./screens/Analytics";

const GraphScreen = lazy(() => import("./screens/Graph"));

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<HomeScreen />} />
        <Route path="capabilities" element={<CapabilitiesScreen />} />
        <Route path="analytics" element={<AnalyticsScreen />} />
        <Route path="cases/:caseId">
          <Route index element={<CaseScreen />} />
          <Route path="pipeline" element={<PipelineScreen />} />
          <Route path="viewer" element={<ViewerScreen />} />
          <Route path="data" element={<DataScreen />} />
          <Route path="conflicts" element={<ConflictsScreen />} />
          <Route
            path="graph"
            element={
              <Suspense fallback={<Loading label="Loading graph" />}>
                <GraphScreen />
              </Suspense>
            }
          />
          <Route path="dossier" element={<DossierScreen />} />
          <Route path="audit" element={<AuditScreen />} />
        </Route>
        <Route path="*" element={<Empty title="This page does not exist" className="h-full" />} />
      </Route>
    </Routes>
  );
}

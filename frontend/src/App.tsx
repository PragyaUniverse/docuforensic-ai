import { Suspense, lazy } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { Empty, Loading } from "./components/ui/states";
import { HomeScreen } from "./screens/Home";
import { CaseScreen } from "./screens/Case";

// Screens other than home and the case overview load when first opened, so the first page is quick.
const named = <K extends string>(load: () => Promise<Record<K, React.ComponentType>>, key: K) =>
  lazy(() => load().then((m) => ({ default: m[key] })));
const PipelineScreen = named(() => import("./screens/Pipeline"), "PipelineScreen");
const ViewerScreen = named(() => import("./screens/Viewer"), "ViewerScreen");
const DataScreen = named(() => import("./screens/Data"), "DataScreen");
const ConflictsScreen = named(() => import("./screens/Conflicts"), "ConflictsScreen");
const DossierScreen = named(() => import("./screens/Dossier"), "DossierScreen");
const AuditScreen = named(() => import("./screens/Audit"), "AuditScreen");
const CapabilitiesScreen = named(() => import("./screens/Capabilities"), "CapabilitiesScreen");
const AnalyticsScreen = named(() => import("./screens/Analytics"), "AnalyticsScreen");
const VerifyScreen = named(() => import("./screens/Verify"), "VerifyScreen");
const GraphScreen = lazy(() => import("./screens/Graph"));

const wait = (el: React.ReactNode) => <Suspense fallback={<Loading label="Loading" className="h-full" />}>{el}</Suspense>;

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<HomeScreen />} />
        <Route path="capabilities" element={wait(<CapabilitiesScreen />)} />
        <Route path="analytics" element={wait(<AnalyticsScreen />)} />
        <Route path="verify" element={wait(<VerifyScreen />)} />
        <Route path="cases/:caseId">
          <Route index element={<CaseScreen />} />
          <Route path="pipeline" element={wait(<PipelineScreen />)} />
          <Route path="viewer" element={wait(<ViewerScreen />)} />
          <Route path="data" element={wait(<DataScreen />)} />
          <Route path="conflicts" element={wait(<ConflictsScreen />)} />
          <Route
            path="graph"
            element={
              <Suspense fallback={<Loading label="Loading graph" />}>
                <GraphScreen />
              </Suspense>
            }
          />
          <Route path="dossier" element={wait(<DossierScreen />)} />
          <Route path="audit" element={wait(<AuditScreen />)} />
        </Route>
        <Route path="about" element={<Navigate to="/capabilities" replace />} />
        <Route
          path="*"
          element={
            <Empty
              title="This page does not exist"
              className="h-full"
              action={
                <Link to="/" className="link">
                  Back to investigations
                </Link>
              }
            >
              The link may be old, or the investigation was deleted.
            </Empty>
          }
        />
      </Route>
    </Routes>
  );
}

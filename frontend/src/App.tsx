import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Layout } from "@/components/Layout";
import { ServersPage } from "@/pages/ServersPage";
import { RunsPage } from "@/pages/RunsPage";
import { NewRunPage } from "@/pages/NewRunPage";
import { EmptyState, Loading } from "@/components/states";

// The run details page carries the charts (Recharts); load it only when needed.
const RunDetailsPage = lazy(() => import("@/pages/RunDetailsPage").then((m) => ({ default: m.RunDetailsPage })));

export default function App() {
  return (
    <TooltipProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/runs" replace />} />
            <Route path="servers" element={<ServersPage />} />
            <Route path="runs" element={<RunsPage />} />
            <Route path="runs/new" element={<NewRunPage />} />
            <Route path="runs/:id" element={<Suspense fallback={<Loading />}><RunDetailsPage /></Suspense>} />
            <Route path="*" element={<EmptyState message="Page not found." />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  );
}

import { Link, Route, Routes } from "react-router";

import { DashboardPage } from "../features/dashboard/DashboardPage";
import { CatalogPage } from "../features/catalog/CatalogPage";
import { DryDataWorkspaceDemo } from "../features/drydata-demo/DryDataWorkspaceDemo";
import { ImportsPage } from "../features/imports/ImportsPage";
import { MoleculeDetailPage } from "../features/molecules/MoleculeDetailPage";
import { MoleculesPage } from "../features/molecules/MoleculesPage";
import { SearchPage } from "../features/search/SearchPage";
import { ActivityPage } from "../features/jobs/ActivityPage";
import { AppLayout } from "../layouts/AppLayout";

function NotFoundPage() {
  return (
    <section className="not-found" aria-labelledby="not-found-title">
      <p className="section-kicker">404 · Not found</p>
      <h1 id="not-found-title">Page not found</h1>
      <p>这个地址不属于当前 MyLabData 工作空间。</p>
      <Link className="button" to="/">
        返回数据工作台
      </Link>
    </section>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="imports" element={<ImportsPage />} />
        <Route path="molecules" element={<MoleculesPage />} />
        <Route path="molecules/:moleculeId" element={<MoleculeDetailPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="drydata-demo" element={<DryDataWorkspaceDemo />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { queryKeys } from "../../api";
import { IncomingPackages } from "./IncomingPackages";
import { PackageBuilder } from "./PackageBuilder";
import { PreviewConfirmation } from "./PreviewConfirmation";
import { ImportHistory } from "./ImportHistory";

type Tab = "incoming" | "preview" | "history" | "build";

const TAB_LABELS: Record<Tab, string> = {
  incoming: "Incoming",
  preview: "Preview",
  history: "History",
  build: "Build",
};

export function ImportsPage() {
  const [parameters, setParameters] = useSearchParams();

  const tab = (parameters.get("tab") as Tab) ?? "incoming";
  const jobId = parameters.get("job");

  function switchTab(next: Tab) {
    const nextParams = new URLSearchParams(parameters);
    nextParams.set("tab", next);
    if (next !== "preview") {
      nextParams.delete("job");
    }
    setParameters(nextParams, { replace: true });
  }

  function handlePreviewStarted(_packageId: string, newJobId: string) {
    const nextParams = new URLSearchParams(parameters);
    nextParams.set("tab", "preview");
    nextParams.set("job", newJobId);
    setParameters(nextParams, { replace: true });
  }

  function handleReset() {
    const nextParams = new URLSearchParams();
    nextParams.set("tab", "incoming");
    setParameters(nextParams, { replace: true });
  }

  function handleCompleted() {
    const nextParams = new URLSearchParams(parameters);
    nextParams.set("tab", "history");
    nextParams.delete("job");
    setParameters(nextParams, { replace: true });
  }

  const queryClient = useQueryClient();
  const refreshKey =
    tab === "incoming"
      ? queryKeys.packages.all()
      : tab === "build"
        ? queryKeys.sourceFiles.all()
        : tab === "history"
          ? queryKeys.imports.all()
          : jobId
            ? queryKeys.jobs.detail(jobId)
            : null;
  const refreshing = useIsFetching({ queryKey: refreshKey ?? queryKeys.all }) > 0;

  function refresh() {
    if (refreshKey) {
      void queryClient.invalidateQueries({ queryKey: refreshKey });
    }
  }

  return (
    <div className="imports-page">
      <div className="section-heading">
        <div>
          <h2>Import</h2>
        </div>
      </div>
      <section className="panel import-shell">
        <div className="import-shell__header">
          <nav className="import-tabs" aria-label="Import workflow tabs">
            {(Object.keys(TAB_LABELS) as Tab[]).map((tabKey) => (
              <button
                aria-pressed={tab === tabKey}
                className={`import-tab${tab === tabKey ? " import-tab--active" : ""}`}
                key={tabKey}
                onClick={() => switchTab(tabKey)}
                type="button"
              >
                {TAB_LABELS[tabKey]}
              </button>
            ))}
          </nav>
          <button
            aria-label="Refresh"
            className={`import-refresh${refreshing ? " import-refresh--busy" : ""}`}
            disabled={!refreshKey}
            title="Refresh"
            type="button"
            onClick={refresh}
          >
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
            </svg>
          </button>
        </div>

        <div className="import-tab-content">
        {tab === "incoming" ? <IncomingPackages onPreviewStarted={handlePreviewStarted} /> : null}
        {tab === "preview" ? (
          jobId ? (
            <PreviewConfirmation
              jobId={jobId}
              onCompleted={handleCompleted}
              onReset={handleReset}
            />
          ) : (
            <div className="preview-workflow">
              <div className="preview-workflow__error">
                <p className="section-kicker">No job selected</p>
                <h3>No preview job in progress</h3>
                <p>Select a package from the Incoming tab to preview.</p>
                <button className="button" type="button" onClick={() => switchTab("incoming")}>
                  Go to Incoming
                </button>
              </div>
            </div>
          )
        ) : null}
        {tab === "history" ? <ImportHistory /> : null}
        {tab === "build" ? <PackageBuilder /> : null}
        </div>
      </section>
    </div>
  );
}

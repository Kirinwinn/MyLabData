import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiClient, ApiError, queryKeys } from "../../api";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatDateTime } from "../../lib/format";

const PAGE_SIZE = 50;

function errorMessage(error: Error | null) {
  return error instanceof ApiError ? error.message : "An unexpected error occurred while reading import records.";
}

interface ImportHistoryProps {
  refreshSignal?: number;
}

export function ImportHistory({ refreshSignal }: ImportHistoryProps) {
  const [offset, setOffset] = useState(0);

  const imports = useQuery({
    queryKey: queryKeys.imports.list(PAGE_SIZE, offset),
    queryFn: ({ signal }) => apiClient.imports({ limit: PAGE_SIZE, offset }, { signal }),
    refetchOnMount: refreshSignal !== undefined,
  });

  const page = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <section className="import-history" aria-labelledby="import-history-title">
      <div className="panel__heading">
        <div>
          <p className="section-kicker">Committed history</p>
          <h2 id="import-history-title">Import history</h2>
          <p>All successful and failed import records.</p>
        </div>
        <span className="section-heading__meta">Page {page}</span>
      </div>

      {imports.isPending ? <LoadingState title="Reading import records" /> : null}
      {imports.error ? (
        <ErrorState
          title="Failed to load imports"
          description={errorMessage(imports.error)}
          onRetry={() => imports.refetch()}
        />
      ) : null}
      {imports.data && !imports.data.length ? (
        <EmptyState title="No import records yet" description="Successful and failed imports will be kept here." />
      ) : null}
      {imports.data?.length ? (
        <>
          <div className="table-wrap">
            <table className="import-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>File</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Total Rows</th>
                  <th>Finished</th>
                </tr>
              </thead>
              <tbody>
                {imports.data.map((record) => (
                  <tr
                    className={record.status === "failed" ? "import-row--failed" : ""}
                    key={record.import_id}
                  >
                    <td>#{record.import_id}</td>
                    <td>
                      <strong>{record.file_hash?.slice(0, 16) ?? "No hash recorded"}</strong>
                      <small>{record.processor ?? "-"}</small>
                      {record.error_message ? (
                        <details className="import-row-error">
                          <summary>View error</summary>
                          <pre>{record.error_message}</pre>
                        </details>
                      ) : null}
                    </td>
                    <td>{record.data_type ?? "—"}</td>
                    <td>
                      <span className={`status-badge status-badge--${record.status}`}>
                        {record.status ?? "unknown"}
                      </span>
                    </td>
                    <td>{record.total_rows?.toLocaleString("en-US") ?? "—"}</td>
                    <td>{formatDateTime(record.finished_at ?? record.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="pagination" aria-label="Import history pagination">
            <button
              className="button button--ghost button--inline"
              disabled={offset === 0}
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </button>
            <span>Page {page}</span>
            <button
              className="button button--ghost button--inline"
              disabled={imports.data.length < PAGE_SIZE}
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </nav>
        </>
      ) : null}
    </section>
  );
}

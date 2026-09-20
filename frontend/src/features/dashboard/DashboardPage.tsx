import { useQuery } from "@tanstack/react-query";

import { apiClient, ApiError, queryKeys } from "../../api";
import type { ImportsResponse, StatsResponse } from "../../api";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatDateTime, formatNumber } from "../../lib/format";

const statCards: Array<{ key: keyof StatsResponse; label: string }> = [
  { key: "molecules", label: "Molecules" },
  { key: "attributes", label: "Attributes" },
  { key: "entries", label: "Entries" },
  { key: "annotations", label: "Annotations" },
  { key: "imports", label: "Imports" },
];

function errorMessage(error: Error | null) {
  return error instanceof ApiError
    ? error.message
    : "An unexpected error occurred while reading data.";
}

export function DashboardPage() {
  const stats = useQuery({
    queryKey: queryKeys.stats(),
    queryFn: ({ signal }) => apiClient.stats({ signal }),
  });
  const imports = useQuery({
    queryKey: queryKeys.imports.list(5, 0),
    queryFn: ({ signal }) => apiClient.imports({ limit: 5, offset: 0 }, { signal }),
  });
  return (
    <div className="dashboard">
      <section aria-labelledby="stats-title">
        <div className="section-heading">
          <div>
            <h2 id="stats-title">Database Summary</h2>
          </div>
        </div>
        <StatsGrid query={stats} />
      </section>

      <section className="panel" aria-labelledby="imports-title">
        <div className="panel__heading">
          <div>
            <p className="section-kicker">Latest activity</p>
            <h2 id="imports-title">Latest Imports</h2>
          </div>
        </div>
        <ImportsPanel query={imports} />
      </section>
    </div>
  );
}

type QueryView<T> = {
  data: T | undefined;
  error: Error | null;
  isPending: boolean;
  isFetching: boolean;
  refetch: () => unknown;
};

function StatsGrid({ query }: { query: QueryView<StatsResponse> }) {
  if (query.isPending) return <LoadingState title="Loading database summary" />;
  if (query.error) {
    return (
      <ErrorState
        title="Database summary failed"
        description={errorMessage(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  }
  if (!query.data) {
    return (
      <EmptyState title="No database summary" description="The backend returned no statistics." />
    );
  }

  return (
    <div className="stats-grid">
      {statCards.map((card) => (
        <article className="stat-card" key={card.key}>
          <p>{card.label}</p>
          <strong>{formatNumber(query.data?.[card.key])}</strong>
        </article>
      ))}
    </div>
  );
}

function ImportsPanel({ query }: { query: QueryView<ImportsResponse> }) {
  if (query.isPending) return <LoadingState compact title="Loading import records" />;
  if (query.error) {
    return (
      <ErrorState
        compact
        title="Failed to load import records"
        description={errorMessage(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  }
  if (!query.data?.length) {
    return (
      <EmptyState
        compact
        title="No import records yet"
        description="Your first completed import will appear here."
      />
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>File</th>
            <th>Type</th>
            <th>Status</th>
            <th>Total Rows</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {query.data.map((record) => (
            <tr key={record.import_id}>
              <td>
                <strong>{record.file_hash?.slice(0, 12) ?? "Hash unavailable"}</strong>
                <small>#{record.import_id}</small>
              </td>
              <td>{record.data_type ?? "—"}</td>
              <td>
                <StatusBadge status={record.status ?? "unknown"} />
              </td>
              <td>{formatNumber(record.total_rows)}</td>
              <td>{formatDateTime(record.created_at, { locale: "en-US" })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge status-badge--${status}`}>{status.replaceAll("_", " ")}</span>
  );
}

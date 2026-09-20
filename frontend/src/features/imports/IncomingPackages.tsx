import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiClient, ApiError, queryKeys } from "../../api";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatDateTime } from "../../lib/format";
import { formatBytes } from "./previewHelpers";

function errorMessage(error: Error | null) {
  return error instanceof ApiError ? error.message : "An unexpected error occurred while reading packages.";
}

interface IncomingPackagesProps {
  onPreviewStarted(packageId: string, jobId: string): void;
}

export function IncomingPackages({ onPreviewStarted }: IncomingPackagesProps) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const packages = useQuery({
    queryKey: queryKeys.packages.list(),
    queryFn: ({ signal }) => apiClient.packages({ signal }),
  });

  const expanded = useQuery({
    queryKey: queryKeys.packages.detail(expandedId ?? ""),
    queryFn: ({ signal }) => apiClient.package(expandedId ?? "", { signal }),
    enabled: Boolean(expandedId),
  });

  const preview = useMutation({
    mutationFn: (packageId: string) => apiClient.previewPackage(packageId),
    onSuccess: (response, packageId) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.packages.all() });
      onPreviewStarted(packageId, response.job_id);
    },
  });

  return (
    <div className="incoming-packages">
      {packages.isPending ? <LoadingState title="Scanning the Incoming directory" /> : null}
      {packages.error ? (
        <ErrorState
          title="Failed to load packages"
          description={errorMessage(packages.error)}
          onRetry={() => packages.refetch()}
        />
      ) : null}
      {packages.data && !packages.data.length ? (
        <EmptyState
          title="The Incoming directory is empty"
          description="Drop Molecules files or Annotation Packages into the Incoming directory and refresh to see them here."
        />
      ) : null}

      {packages.data?.length ? (
        <div className="package-list">
          {packages.data.map((item) => (
            <article
              className={`package-card package-card--${item.package_kind}`}
              key={item.package_id}
            >
              <button
                aria-expanded={expandedId === item.package_id}
                className="package-card__header"
                onClick={() =>
                  setExpandedId(expandedId === item.package_id ? null : item.package_id)
                }
                type="button"
              >
                <span className={`package-kind-badge package-kind-badge--${item.package_kind}`}>
                  {item.package_kind}
                </span>
                <div>
                  <strong>{item.package_name}</strong>
                  <small>
                    {formatBytes(item.size_bytes)} · {formatDateTime(item.modified_at)}
                  </small>
                </div>
                <span className="package-card__expand" aria-hidden="true">
                  {expandedId === item.package_id ? "▾" : "▸"}
                </span>
              </button>

              {expandedId === item.package_id ? (
                <div className="package-card__body">
                  {expanded.isPending ? <LoadingState compact title="Reading package details" /> : null}
                  {expanded.error ? (
                    <ErrorState
                      compact
                      title="Failed to load package details"
                      description={errorMessage(expanded.error)}
                      onRetry={() => expanded.refetch()}
                    />
                  ) : null}
                  {expanded.data ? (
                    <>
                      <div className="package-files">
                        <ul>
                          {expanded.data.files.map((file) => (
                            <li key={file}>{file}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="package-actions">
                        <button
                          className="button"
                          disabled={preview.isPending}
                          onClick={() => preview.mutate(item.package_id)}
                          type="button"
                        >
                          {preview.isPending ? "Starting preview…" : "Preview"}
                        </button>
                        {preview.error ? (
                          <p className="mutation-error">{errorMessage(preview.error)}</p>
                        ) : null}
                      </div>
                    </>
                  ) : null}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}

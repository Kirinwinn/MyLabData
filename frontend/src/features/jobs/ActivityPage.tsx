import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";

import { apiClient, ApiError, parseJobResult, queryKeys } from "../../api";
import type { ImportsResponse, JobResponse, JobsResponse } from "../../api";
import { EmptyState, ErrorState, LoadingState } from "../../components/PageState";
import { formatDateTime, formatNumber } from "../../lib/format";
import { updateJobCaches } from "./jobCache";
import { formatJobType, isTerminalJob, isUnfinishedJob, jobStatusLabels } from "./jobStatus";
import { transportLabel, useJob } from "./useJob";

const JOB_LIMIT = 200;
const IMPORT_LIMIT = 100;

function errorMessage(error: Error | null) {
  return error instanceof ApiError ? error.message : "An unexpected error occurred while reading activity records.";
}

export function ActivityPage() {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const jobs = useQuery({
    queryKey: queryKeys.jobs.list(JOB_LIMIT),
    queryFn: ({ signal }) => apiClient.jobs({ limit: JOB_LIMIT }, { signal }),
    refetchInterval: (state) => (state.state.data?.some(isUnfinishedJob) === true ? 5_000 : 30_000),
  });
  const imports = useQuery({
    queryKey: queryKeys.imports.list(IMPORT_LIMIT, 0),
    queryFn: ({ signal }) => apiClient.imports({ limit: IMPORT_LIMIT, offset: 0 }, { signal }),
  });
  const effectiveSelectedJobId =
    selectedJobId && jobs.data?.some((job) => job.job_id === selectedJobId)
      ? selectedJobId
      : (jobs.data?.[0]?.job_id ?? null);

  return (
    <div className="activity-page">
      <div className="section-heading">
        <div>
          <h2>Job</h2>
        </div>
      </div>
      <div className="activity-workspace">
        <section className="activity-job-list" aria-labelledby="activity-jobs-title">
          <div className="section-heading">
            <div>
              <h2 id="activity-jobs-title">History</h2>
            </div>
            {jobs.isFetching && !jobs.isPending ? <span>Syncing</span> : null}
          </div>
          <JobList
            jobs={jobs.data}
            error={jobs.error}
            isPending={jobs.isPending}
            onRetry={() => jobs.refetch()}
            onSelect={setSelectedJobId}
            selectedJobId={effectiveSelectedJobId}
          />
        </section>

        <section className="activity-job-detail" aria-labelledby="job-detail-title">
          <JobDetail jobId={effectiveSelectedJobId} />
        </section>
      </div>

      <section className="activity-imports panel" aria-labelledby="activity-imports-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Committed history</p>
            <h2 id="activity-imports-title">Imports</h2>
          </div>
          <span className="section-heading__meta">Latest {IMPORT_LIMIT} records</span>
        </div>
        <ImportsTable query={imports} />
      </section>
    </div>
  );
}

interface JobListProps {
  jobs: JobsResponse | undefined;
  error: Error | null;
  isPending: boolean;
  selectedJobId: string | null;
  onSelect(jobId: string): void;
  onRetry(): unknown;
}

function JobList({ jobs, error, isPending, selectedJobId, onSelect, onRetry }: JobListProps) {
  if (isPending) return <LoadingState compact title="Loading jobs" />;
  if (error) {
    return (
      <ErrorState
        compact
        title="Failed to load jobs"
        description={errorMessage(error)}
        onRetry={onRetry}
      />
    );
  }
  if (!jobs?.length) {
    return <EmptyState compact title="No jobs yet" description="Submitted jobs will appear here." />;
  }

  return (
    <div className="activity-job-items">
      {jobs.map((job) => (
        <button
          aria-pressed={selectedJobId === job.job_id}
          className={`activity-job-item${selectedJobId === job.job_id ? " activity-job-item--active" : ""}`}
          key={job.job_id}
          onClick={() => onSelect(job.job_id)}
          type="button"
        >
          <span className={`status-dot status-dot--${job.status}`} aria-hidden="true" />
          <span>
            <strong>{formatJobType(job.job_type)}</strong>
            <small>{job.message ?? `Job ${job.job_id.slice(0, 8)}`}</small>
          </span>
          <span>
            <JobStatusBadge status={job.status} />
            <small>{formatDateTime(job.updated_at, { locale: "en-US" })}</small>
          </span>
        </button>
      ))}
    </div>
  );
}

function JobDetail({ jobId }: { jobId: string | null }) {
  const queryClient = useQueryClient();
  const job = useJob(jobId);
  const cancel = useMutation({
    mutationFn: (id: string) => apiClient.cancelJob(id),
    onSuccess: (updated) => updateJobCaches(queryClient, updated),
  });

  if (!jobId) {
    return (
      <EmptyState
        compact
        title="Select a job"
        description="Live status and the full result of a job will appear here."
      />
    );
  }
  if (job.isPending) return <LoadingState compact title="Loading job details" />;
  if (job.error || !job.data) {
    return (
      <ErrorState
        compact
        title="Failed to load job details"
        description={errorMessage(job.error)}
        onRetry={() => job.refetch()}
      />
    );
  }

  const record = job.data;
  const parsedResult = parseJobResult(record);
  const canCancel = !isTerminalJob(record) && !record.cancel_requested;

  return (
    <div className="job-detail-card">
      <header>
        <div>
          <h2 id="job-detail-title">{formatJobType(record.job_type)}</h2>
          <code>{record.job_id}</code>
        </div>
      </header>

      <div className="job-progress-block">
        <div>
          <span>{record.message ?? "The backend did not provide a status message."}</span>
          <strong>{Math.round(record.progress * 100)}%</strong>
        </div>
        <div className="progress" aria-label={`Job progress ${Math.round(record.progress * 100)}%`}>
          <span style={{ width: `${record.progress * 100}%` }} />
        </div>
        <small>{transportLabel(job.transport, record)}</small>
      </div>

      <dl className="job-detail-meta">
        <div>
          <dt>Created</dt>
          <dd>{formatDateTime(record.created_at, { locale: "en-US" })}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{formatDateTime(record.started_at, { locale: "en-US" })}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>{formatDateTime(record.finished_at, { locale: "en-US" })}</dd>
        </div>
        <div>
          <dt>Cancel requested</dt>
          <dd>{record.cancel_requested ? "Sent" : "No"}</dd>
        </div>
      </dl>

      {record.error_message ? (
        <section className="job-error" aria-labelledby="job-error-title">
          <h3 id="job-error-title">Full error</h3>
          <pre>{record.error_message}</pre>
        </section>
      ) : null}

      {record.result ? (
        <section className="job-data" aria-labelledby="job-result-title">
          <h3 id="job-result-title">Result</h3>
          {!parsedResult.ok ? <p className="inline-warning">{parsedResult.error.message}</p> : null}
          <pre>{JSON.stringify(record.result, null, 2)}</pre>
        </section>
      ) : null}

      <details className="job-data">
        <summary>View job payload</summary>
        <pre>{JSON.stringify(record.payload, null, 2)}</pre>
      </details>

      {canCancel ? (
        <button
          className="button button--danger"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate(record.job_id)}
          type="button"
        >
          {cancel.isPending ? "Sending cancel request…" : "Cancel job"}
        </button>
      ) : null}
      {cancel.error ? <p className="mutation-error">{errorMessage(cancel.error)}</p> : null}
    </div>
  );
}

function ImportsTable({ query }: { query: UseQueryResult<ImportsResponse, Error> }) {
  if (query.isPending) return <LoadingState compact title="Loading imports" />;
  if (query.error) {
    return (
      <ErrorState
        compact
        title="Failed to load imports"
        description={errorMessage(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  }
  if (!query.data?.length) {
    return <EmptyState compact title="No imports yet" description="Successful and failed imports will be kept here." />;
  }

  return (
    <div className="table-wrap">
      <table>
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
          {query.data.map((record) => (
            <tr key={record.import_id}>
              <td>#{record.import_id}</td>
              <td>
                <strong>{record.file_hash?.slice(0, 16) ?? "No hash recorded"}</strong>
                <small>{record.processor ?? "—"}</small>
              </td>
              <td>{record.data_type ?? "—"}</td>
              <td>
                <span className={`status-badge status-badge--${record.status}`}>
                  {record.status ?? "unknown"}
                </span>
              </td>
              <td>{formatNumber(record.total_rows)}</td>
              <td>{formatDateTime(record.finished_at ?? record.created_at, { locale: "en-US" })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobStatusBadge({ status }: { status: JobResponse["status"] }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      {jobStatusLabels[status]}
      <span className="sr-only"> ({status})</span>
    </span>
  );
}

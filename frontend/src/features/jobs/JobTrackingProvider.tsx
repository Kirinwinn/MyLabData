import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext } from "react";
import { Link } from "react-router";

import { apiClient, queryKeys } from "../../api";
import type { JobsResponse } from "../../api";
import { formatJobType, isUnfinishedJob, jobStatusLabels } from "./jobStatus";
import { useJob } from "./useJob";

interface JobTrackingContextValue {
  jobs: JobsResponse;
  unavailable: boolean;
}

const JobTrackingContext = createContext<JobTrackingContextValue>({ jobs: [], unavailable: false });

export function JobTrackingProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: queryKeys.jobs.list(100),
    queryFn: ({ signal }) => apiClient.jobs({ limit: 100 }, { signal }),
    refetchInterval: (state) => (state.state.data?.some(isUnfinishedJob) === true ? 5_000 : 30_000),
  });
  const unfinished = query.data?.filter(isUnfinishedJob) ?? [];

  return (
    <JobTrackingContext.Provider value={{ jobs: query.data ?? [], unavailable: query.isError }}>
      {children}
      {unfinished.map((job) => (
        <JobObserver jobId={job.job_id} key={job.job_id} />
      ))}
    </JobTrackingContext.Provider>
  );
}

function JobObserver({ jobId }: { jobId: string }) {
  useJob(jobId);
  return null;
}

export function GlobalJobStatus() {
  const { jobs, unavailable } = useContext(JobTrackingContext);
  const unfinished = jobs.filter(isUnfinishedJob);
  const running = unfinished.filter((job) => job.status !== "waiting_confirmation");
  const waiting = unfinished.filter((job) => job.status === "waiting_confirmation");
  const latestFailure = jobs.find((job) => job.status === "failed");

  if (unavailable) {
    return (
      <Link className="global-job-state global-job-state--offline" to="/activity">
        Job status unavailable
      </Link>
    );
  }
  if (running.length) {
    const lead = running[0];
    return (
      <Link className="global-job-state global-job-state--active" to="/activity">
        <span aria-hidden="true" />
        {running.length} active job{running.length === 1 ? "" : "s"} ·{" "}
        {jobStatusLabels[lead.status]}
      </Link>
    );
  }
  if (waiting.length) {
    return (
      <Link className="global-job-state global-job-state--waiting" to="/activity">
        {waiting.length} job{waiting.length === 1 ? "" : "s"} awaiting confirmation
      </Link>
    );
  }
  if (latestFailure) {
    return (
      <Link className="global-job-state global-job-state--failed" to="/activity">
        Latest failure · {formatJobType(latestFailure.job_type)}
      </Link>
    );
  }
  return (
    <Link className="global-job-state" to="/activity">
      Jobs idle
    </Link>
  );
}

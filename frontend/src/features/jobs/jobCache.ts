import type { QueryClient } from "@tanstack/react-query";

import type { JobResponse, JobsResponse } from "../../api";
import { queryKeys } from "../../api";

export function updateJobCaches(queryClient: QueryClient, job: JobResponse) {
  queryClient.setQueryData(queryKeys.jobs.detail(job.job_id), job);
  queryClient.setQueriesData<JobsResponse>(
    {
      predicate: (query) =>
        query.queryKey[0] === "mylabdata" &&
        query.queryKey[1] === "jobs" &&
        query.queryKey[2] === "list",
    },
    (current) => {
      if (!current) return current;
      const index = current.findIndex((candidate) => candidate.job_id === job.job_id);
      if (index < 0) return [job, ...current];
      return current.map((candidate) => (candidate.job_id === job.job_id ? job : candidate));
    },
  );
}

export async function refreshQueriesForFinishedJob(queryClient: QueryClient, job: JobResponse) {
  const invalidations: Promise<unknown>[] = [
    queryClient.invalidateQueries({
      predicate: (query) =>
        query.queryKey[0] === "mylabdata" &&
        query.queryKey[1] === "jobs" &&
        query.queryKey[2] === "list",
    }),
  ];

  if (job.job_type === "package_import") {
    invalidations.push(
      queryClient.invalidateQueries({ queryKey: queryKeys.packages.all() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.molecules.all() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.attributes.all() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.imports.all() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.stats() }),
    );
  } else if (job.job_type === "property_update") {
    invalidations.push(
      queryClient.invalidateQueries({ queryKey: queryKeys.molecules.all() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.attributes.all() }),
      queryClient.invalidateQueries({ queryKey: [...queryKeys.all, "search"] }),
    );
  } else if (job.job_type === "package_preview") {
    invalidations.push(queryClient.invalidateQueries({ queryKey: queryKeys.packages.all() }));
  }

  await Promise.all(invalidations);
}

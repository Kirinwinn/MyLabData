import type { JobResponse } from "../../api";

export type JobStatus = JobResponse["status"];

export const terminalJobStatuses = new Set<JobStatus>(["completed", "failed", "cancelled"]);
export const unfinishedJobStatuses = new Set<JobStatus>([
  "queued",
  "validating",
  "waiting_confirmation",
  "running",
  "importing",
  "archiving",
  "archive_pending",
]);

export const jobStatusLabels: Record<JobStatus, string> = {
  queued: "Queued",
  validating: "Validating",
  waiting_confirmation: "Waiting for confirmation",
  running: "Running",
  importing: "Importing",
  archiving: "Archiving",
  archive_pending: "Awaiting archive",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function isTerminalJob(job: Pick<JobResponse, "status"> | undefined) {
  return job ? terminalJobStatuses.has(job.status) : false;
}

export function isUnfinishedJob(job: Pick<JobResponse, "status">) {
  return unfinishedJobStatuses.has(job.status);
}

export function formatJobType(jobType: string) {
  return jobType.replaceAll("_", " ");
}

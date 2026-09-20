import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { apiClient, queryKeys, subscribeToJobEvents } from "../../api";
import type { JobResponse } from "../../api";
import { refreshQueriesForFinishedJob, updateJobCaches } from "./jobCache";
import { isTerminalJob } from "./jobStatus";

export type JobTransport = "connecting" | "sse" | "polling" | "idle";

export function useJob(jobId: string | null) {
  const queryClient = useQueryClient();
  const [transportState, setTransportState] = useState<{
    jobId: string | null;
    value: JobTransport;
  }>({ jobId: null, value: "idle" });
  const subscription = useRef<{ close(): void } | null>(null);
  const refreshedVersion = useRef<string | null>(null);
  const baseTransport: JobTransport = !jobId
    ? "idle"
    : typeof EventSource === "undefined"
      ? "polling"
      : transportState.jobId === jobId
        ? transportState.value
        : "connecting";

  const query = useQuery({
    queryKey: queryKeys.jobs.detail(jobId ?? ""),
    queryFn: ({ signal }) => apiClient.job(jobId ?? "", { signal }),
    enabled: Boolean(jobId),
    refetchInterval: (state) => {
      const job = state.state.data;
      if (isTerminalJob(job)) return false;
      if (job?.status === "waiting_confirmation") return 5_000;
      return baseTransport === "polling" ? 2_000 : false;
    },
  });

  useEffect(() => {
    subscription.current?.close();
    subscription.current = null;
    refreshedVersion.current = null;

    if (!jobId) {
      return;
    }
    if (typeof EventSource === "undefined") {
      return;
    }

    subscription.current = subscribeToJobEvents(jobId, {
      onOpen: () => setTransportState({ jobId, value: "sse" }),
      onJob: (job) => {
        updateJobCaches(queryClient, job);
        if (job.status === "waiting_confirmation") {
          subscription.current?.close();
          subscription.current = null;
        } else if (isTerminalJob(job)) {
          subscription.current?.close();
          subscription.current = null;
        }
      },
      onDisconnect: () => {
        subscription.current = null;
        setTransportState({ jobId, value: "polling" });
      },
    });

    return () => {
      subscription.current?.close();
      subscription.current = null;
    };
  }, [jobId, queryClient]);

  useEffect(() => {
    const job = query.data;
    if (!job) return;
    if (job.status === "waiting_confirmation") {
      subscription.current?.close();
      subscription.current = null;
    }
    if (!isTerminalJob(job)) return;

    subscription.current?.close();
    subscription.current = null;
    const version = `${job.job_id}:${job.updated_at}`;
    if (refreshedVersion.current === version) return;
    refreshedVersion.current = version;
    void refreshQueriesForFinishedJob(queryClient, job);
  }, [query.data, queryClient]);

  const transport: JobTransport = isTerminalJob(query.data)
    ? "idle"
    : query.data?.status === "waiting_confirmation"
      ? "polling"
      : baseTransport;

  return { ...query, transport };
}

export function transportLabel(transport: JobTransport, job?: JobResponse) {
  if (isTerminalJob(job)) return "Monitoring ended";
  if (job?.status === "waiting_confirmation") return "Awaiting confirmation · Polling";
  if (transport === "sse") return "SSE live updates";
  if (transport === "polling") return "Polling (SSE disconnected)";
  if (transport === "connecting") return "Establishing SSE";
  return "Not monitoring";
}

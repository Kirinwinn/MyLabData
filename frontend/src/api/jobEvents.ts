import { z } from "zod";

import type { JobResponse } from "./client";

const jobEventSchema: z.ZodType<JobResponse> = z.object({
  job_id: z.string(),
  job_type: z.string(),
  job_kind: z.enum(["query", "command"]),
  status: z.enum([
    "queued",
    "validating",
    "waiting_confirmation",
    "running",
    "importing",
    "archiving",
    "archive_pending",
    "completed",
    "failed",
    "cancelled",
  ]),
  progress: z.number().min(0).max(1),
  message: z.string().nullable(),
  payload: z.record(z.string(), z.unknown()),
  result: z.record(z.string(), z.unknown()).nullable(),
  error_message: z.string().nullable(),
  cancel_requested: z.boolean(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  updated_at: z.string(),
});

export type JobEventTransportErrorKind = "connection" | "payload";

export class JobEventTransportError extends Error {
  constructor(
    message: string,
    readonly kind: JobEventTransportErrorKind,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "JobEventTransportError";
  }
}

interface JobEventSource {
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
  addEventListener(type: "job", listener: (event: MessageEvent<string>) => void): void;
  close(): void;
}

export type JobEventSourceFactory = (url: string) => JobEventSource;

export interface JobEventCallbacks {
  onJob(job: JobResponse): void;
  onOpen?(): void;
  onDisconnect(error: JobEventTransportError): void;
}

export interface JobEventSubscription {
  close(): void;
}

export function subscribeToJobEvents(
  jobId: string,
  callbacks: JobEventCallbacks,
  factory: JobEventSourceFactory = defaultEventSourceFactory,
): JobEventSubscription {
  const source = factory(`/api/v1/jobs/${encodeURIComponent(jobId)}/events`);
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    source.close();
  };

  source.onopen = () => callbacks.onOpen?.();
  source.addEventListener("job", (event) => {
    try {
      const parsed = jobEventSchema.safeParse(JSON.parse(event.data) as unknown);
      if (!parsed.success) {
        throw new JobEventTransportError("SSE 返回的 Job 数据不符合 API 契约。", "payload", {
          cause: parsed.error,
        });
      }
      callbacks.onJob(parsed.data);
    } catch (error) {
      close();
      callbacks.onDisconnect(
        error instanceof JobEventTransportError
          ? error
          : new JobEventTransportError("无法解析 SSE Job 事件。", "payload", { cause: error }),
      );
    }
  });
  source.onerror = () => {
    if (closed) return;
    close();
    callbacks.onDisconnect(new JobEventTransportError("SSE 连接已断开。", "connection"));
  };

  return { close };
}

function defaultEventSourceFactory(url: string): JobEventSource {
  return new EventSource(url) as unknown as JobEventSource;
}

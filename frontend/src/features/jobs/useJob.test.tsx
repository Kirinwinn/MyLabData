import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { JobResponse } from "../../api";
import { useJob } from "./useJob";

const queuedJob: JobResponse = {
  job_id: "job-1",
  job_type: "package_import",
  job_kind: "command",
  status: "queued",
  progress: 0,
  message: "Queued",
  payload: { package_id: "package-1" },
  result: null,
  error_message: null,
  cancel_requested: false,
  created_at: "2026-08-27T00:00:00Z",
  started_at: null,
  finished_at: null,
  updated_at: "2026-08-27T00:00:00Z",
};

class FakeEventSource {
  static latest: FakeEventSource;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  jobListener: ((event: MessageEvent<string>) => void) | null = null;
  close = vi.fn();

  constructor(readonly url: string) {
    FakeEventSource.latest = this;
  }

  addEventListener(type: string, listener: EventListener) {
    if (type === "job") {
      this.jobListener = listener as (event: MessageEvent<string>) => void;
    }
  }
}

function JobView() {
  const job = useJob("job-1");
  return (
    <div>
      <span>{job.transport}</span>
      <span>{job.data?.status}</span>
    </div>
  );
}

function renderJob() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <JobView />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useJob", () => {
  it("closes SSE at a terminal state and keeps failed distinct from completed", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(queuedJob)));
    renderJob();

    expect(await screen.findByText("queued")).toBeInTheDocument();
    FakeEventSource.latest.onopen?.(new Event("open"));
    expect(await screen.findByText("sse")).toBeInTheDocument();

    const failed: JobResponse = {
      ...queuedJob,
      status: "failed",
      message: "Background operation failed",
      error_message: "database unavailable",
      finished_at: "2026-08-27T00:00:03Z",
      updated_at: "2026-08-27T00:00:03Z",
    };
    FakeEventSource.latest.jobListener?.(new MessageEvent("job", { data: JSON.stringify(failed) }));

    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(screen.getByText("idle")).toBeInTheDocument();
    expect(FakeEventSource.latest.close).toHaveBeenCalled();
  });

  it("switches to polling when SSE disconnects", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(queuedJob)));
    renderJob();

    expect(await screen.findByText("queued")).toBeInTheDocument();
    FakeEventSource.latest.onerror?.(new Event("error"));

    expect(await screen.findByText("polling")).toBeInTheDocument();
    expect(FakeEventSource.latest.close).toHaveBeenCalled();
  });
});

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

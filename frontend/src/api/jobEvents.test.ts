import { describe, expect, it, vi } from "vitest";

import type { JobResponse } from "./client";
import { JobEventTransportError, subscribeToJobEvents } from "./jobEvents";

const job: JobResponse = {
  job_id: "job-1",
  job_type: "package_import",
  job_kind: "command",
  status: "importing",
  progress: 0.5,
  message: "Importing",
  payload: { package_id: "pkg-1" },
  result: null,
  error_message: null,
  cancel_requested: false,
  created_at: "2026-08-27T00:00:00Z",
  started_at: "2026-08-27T00:00:01Z",
  finished_at: null,
  updated_at: "2026-08-27T00:00:02Z",
};

class FakeEventSource {
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  jobListener: ((event: MessageEvent<string>) => void) | null = null;
  close = vi.fn();

  addEventListener(_type: "job", listener: (event: MessageEvent<string>) => void) {
    this.jobListener = listener;
  }
}

describe("Job SSE transport", () => {
  it("parses named Job events and closes on disconnect", () => {
    const source = new FakeEventSource();
    const onJob = vi.fn();
    const onDisconnect = vi.fn();
    const factory = vi.fn(() => source);

    subscribeToJobEvents("job/1", { onJob, onDisconnect }, factory);
    source.jobListener?.(new MessageEvent("job", { data: JSON.stringify(job) }));
    source.onerror?.(new Event("error"));

    expect(factory).toHaveBeenCalledWith("/api/v1/jobs/job%2F1/events");
    expect(onJob).toHaveBeenCalledWith(job);
    expect(source.close).toHaveBeenCalledOnce();
    expect(onDisconnect).toHaveBeenCalledWith(expect.any(JobEventTransportError));
  });

  it("rejects malformed events instead of accepting a false success", () => {
    const source = new FakeEventSource();
    const onJob = vi.fn();
    const onDisconnect = vi.fn();

    subscribeToJobEvents("job-1", { onJob, onDisconnect }, () => source);
    source.jobListener?.(
      new MessageEvent("job", { data: JSON.stringify({ ...job, status: "success" }) }),
    );

    expect(onJob).not.toHaveBeenCalled();
    expect(onDisconnect).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "payload", message: expect.stringContaining("API 契约") }),
    );
    expect(source.close).toHaveBeenCalledOnce();
  });
});

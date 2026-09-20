import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import type { JobResponse } from "../../api";
import { App } from "../../app/App";
import { createQueryJobHandler, json } from "../../tests/queryJobMock";

const failedJob: JobResponse = {
  job_id: "job-failed",
  job_type: "package_import",
  job_kind: "command",
  status: "failed",
  progress: 0,
  message: "Background operation failed",
  payload: { package_id: "package-1", preview_token: "secret-token" },
  result: null,
  error_message: "Constraint Error: duplicate key\nTransaction rolled back safely.",
  cancel_requested: false,
  created_at: "2026-08-27T00:00:00Z",
  started_at: "2026-08-27T00:00:01Z",
  finished_at: "2026-08-27T00:00:02Z",
  updated_at: "2026-08-27T00:00:02Z",
};

const queuedJob: JobResponse = {
  ...failedJob,
  job_id: "job-queued",
  job_type: "package_import",
  status: "queued",
  progress: 0,
  message: "Waiting for writer",
  error_message: null,
  started_at: null,
  finished_at: null,
};

function renderActivity() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/activity"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Activity page", () => {
  it("shows persistent Jobs, Imports and the complete failure message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        createQueryJobHandler(
          (url) => {
            if (url === "/api/v1/imports/query") {
              return {
                items: [
                  {
                    import_id: 9,
                    source_id: 1,
                    file_hash: "abc",
                    data_type: "annotations",
                    status: "failed",
                    processor: "mylabdata.v3.package_import",
                    total_rows: 10,
                    error_message: "rolled back",
                    created_at: "2026-08-27T00:00:00Z",
                    finished_at: "2026-08-27T00:00:02Z",
                  },
                ],
              };
            }
            return undefined;
          },
          (url) => {
            if (url === "/api/v1/jobs?limit=200") return json([failedJob]);
            if (url === "/api/v1/jobs/job-failed") return json(failedJob);
            throw new Error(`Unexpected URL ${url}`);
          },
        ),
      ),
    );

    renderActivity();

    expect(await screen.findByRole("heading", { name: "package import" })).toBeInTheDocument();
    expect(screen.getByText(/Constraint Error: duplicate key/)).toHaveTextContent(
      "Constraint Error: duplicate key Transaction rolled back safely.",
    );
    expect(screen.getByText("abc")).toBeInTheDocument();
    expect(screen.getByText("Monitoring ended")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel job" })).not.toBeInTheDocument();
  });

  it("sends cancellation and keeps the returned cancelled state", async () => {
    const cancelledJob: JobResponse = {
      ...queuedJob,
      status: "cancelled",
      message: "Cancelled before execution",
      finished_at: "2026-08-27T00:00:03Z",
      updated_at: "2026-08-27T00:00:03Z",
    };
    const fetchMock = vi.fn(
      createQueryJobHandler(
        (url) => (url === "/api/v1/imports/query" ? { items: [] } : undefined),
        (url, init) => {
          if (url === "/api/v1/jobs?limit=200") return json([queuedJob]);
          if (url === "/api/v1/jobs/job-queued/cancel" && init?.method === "POST") {
            return json(cancelledJob);
          }
          if (url === "/api/v1/jobs/job-queued") return json(queuedJob);
          throw new Error(`Unexpected URL ${url}`);
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderActivity();
    expect(await screen.findByText("Polling (SSE disconnected)")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Cancel job" }));

    expect(await screen.findByText("Cancelled before execution")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/jobs/job-queued/cancel",
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.queryByRole("button", { name: "Cancel job" })).not.toBeInTheDocument();
  });
});

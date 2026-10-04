import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api";
import type { JobResponse } from "../../api";
import { PreviewConfirmation } from "./PreviewConfirmation";

const state = vi.hoisted(() => ({ jobs: {} as Record<string, JobResponse> }));

vi.mock("../jobs/useJob", () => ({
  useJob: (id: string | null) => ({
    data: id ? state.jobs[id] : undefined,
    isPending: false,
    error: null,
    transport: "polling",
  }),
  transportLabel: () => "Monitoring ended",
}));

const preview: JobResponse = {
  job_id: "preview-1",
  job_type: "package_preview",
  job_kind: "query",
  status: "waiting_confirmation",
  progress: 0.5,
  message: "Molecules package is ready for confirmation",
  payload: { package_id: "mol-1" },
  result: {
    package_name: "molecules.parquet",
    package_hash: "a".repeat(64),
    total_rows: 2,
    valid_rows: 2,
    new_rows: 2,
    existing_rows: 0,
    duplicate_rows: 0,
    invalid_rows: 0,
  },
  error_message: null,
  cancel_requested: false,
  created_at: "2026-10-04T00:00:00Z",
  started_at: "2026-10-04T00:00:01Z",
  finished_at: null,
  updated_at: "2026-10-04T00:00:02Z",
};

function renderPreview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PreviewConfirmation jobId={preview.job_id} onCompleted={vi.fn()} onReset={vi.fn()} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  state.jobs = {};
});

describe("Molecules preview confirmation", () => {
  it.each([
    [1, 0, "Cannot import: 1 invalid records. Fix the file and preview again."],
    [0, 1, "Cannot import: 1 in-file duplicates. Fix the file and preview again."],
    [1, 1, "Cannot import: 1 invalid records and 1 in-file duplicates. Fix the file and preview again."],
  ])("blocks confirmation for %i invalid rows and %i duplicates", (invalid, duplicates, reason) => {
    state.jobs = {
      [preview.job_id]: {
        ...preview,
        result: {
          ...preview.result,
          total_rows: 2 + invalid + duplicates,
          valid_rows: 2 + duplicates,
          invalid_rows: invalid,
          duplicate_rows: duplicates,
        },
      },
    };
    const submit = vi.spyOn(apiClient, "importPackage");

    renderPreview();
    expect(screen.getByText("Invalid records")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(reason);
    expect(screen.queryByRole("button", { name: "Confirm import" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("allows existing molecules and explains that they will be skipped", () => {
    state.jobs = {
      [preview.job_id]: {
        ...preview,
        result: { ...preview.result, existing_rows: 1, new_rows: 1 },
      },
    };

    renderPreview();
    expect(screen.getByRole("button", { name: "Confirm import" })).toBeInTheDocument();
    expect(screen.getByText(
      "Existing molecules will be skipped. Only new molecules will be inserted.",
    )).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows preview details and sends the reviewed hash only after confirmation", async () => {
    state.jobs = {
      [preview.job_id]: preview,
      "import-1": {
        ...preview,
        job_id: "import-1",
        job_type: "package_import",
        job_kind: "command",
        status: "completed",
        progress: 1,
        result: {
          import_id: 1,
          package_name: "molecules.parquet",
          package_hash: "a".repeat(64),
          total_rows: 2,
          inserted_rows: 2,
          existing_rows: 0,
          duplicate_rows: 0,
          invalid_rows: 0,
          created_attributes: 0,
          created_entries: 0,
          created_sources: 0,
          archived: true,
        },
      },
    };
    const submit = vi.spyOn(apiClient, "importPackage").mockResolvedValue({
      package_id: "mol-1",
      job_id: "import-1",
      status: "queued",
    });

    renderPreview();
    expect(screen.getByText("Total rows")).toBeInTheDocument();
    expect(screen.getByText("New molecules")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm import" }));
    expect(submit).toHaveBeenCalledWith("mol-1", { preview_hash: "a".repeat(64) });
    expect(await screen.findByRole("heading", { name: "Import completed" })).toBeInTheDocument();
    expect(screen.getByText(/2 rows written/)).toBeInTheDocument();
  });

  it("shows a file-change rejection from the background import job", async () => {
    state.jobs = {
      [preview.job_id]: preview,
      "import-failed": {
        ...preview,
        job_id: "import-failed",
        job_type: "package_import",
        job_kind: "command",
        status: "failed",
        result: null,
        error_message: "Molecules preview hash is invalid or the package changed; please preview again",
      },
    };
    vi.spyOn(apiClient, "importPackage").mockResolvedValue({
      package_id: "mol-1",
      job_id: "import-failed",
      status: "queued",
    });

    renderPreview();
    await userEvent.click(screen.getByRole("button", { name: "Confirm import" }));
    expect(await screen.findByRole("heading", { name: "Import Failed" })).toBeInTheDocument();
    expect(screen.getByText(/package changed; please preview again/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Import completed" })).not.toBeInTheDocument();
  });
});

import { describe, expect, it } from "vitest";

import { parseJobResult } from "./jobResults";

describe("parseJobResult", () => {
  it("parses a result according to its job_type", () => {
    const parsed = parseJobResult({
      job_type: "package_preview",
      result: {
        package_name: "example.parquet",
        package_hash: "abc123",
        total_rows: 4,
        valid_rows: 3,
        new_rows: 2,
        existing_rows: 1,
        duplicate_rows: 0,
        invalid_rows: 1,
      },
    });

    expect(parsed).toMatchObject({
      ok: true,
      data: { jobType: "molecule_preview", result: { new_rows: 2 } },
    });
  });

  it("rejects a result whose shape does not match its job_type", () => {
    const parsed = parseJobResult({
      job_type: "package_preview",
      result: { total_rows: -1 },
    });

    expect(parsed).toMatchObject({
      ok: false,
      error: { jobType: "package_preview", message: "任务结果与任务类型不匹配" },
    });
  });

  it("reports an unsupported job type without trusting its result", () => {
    const parsed = parseJobResult({ job_type: "future_job", result: { status: "ok" } });
    expect(parsed).toMatchObject({ ok: false, error: { jobType: "future_job" } });
  });

  it("accepts an absent result while a job is unfinished", () => {
    expect(parseJobResult({ job_type: "package_import", result: null })).toEqual({
      ok: true,
      data: null,
    });
  });
});

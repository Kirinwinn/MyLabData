import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "./client";
import { ApiError } from "./errors";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApiClient", () => {
  it("calls the versioned health endpoint and returns its generated response type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(new ApiClient().health()).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/health",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("normalizes a FastAPI validation detail response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: [{ loc: ["body", "source"], msg: "Field required", type: "missing" }],
          }),
          { status: 422, statusText: "Unprocessable Entity" },
        ),
      ),
    );

    const error = await new ApiClient().health().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      kind: "http",
      status: 422,
      message: "body.source: Field required",
      validationIssues: [{ location: "body.source", message: "Field required", type: "missing" }],
    });
  });

  it("normalizes network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    const error = await new ApiClient().health().catch((caught: unknown) => caught);
    expect(error).toMatchObject({ kind: "network", status: undefined });
  });

  it("queries and cancels a Job through generated-contract endpoints", async () => {
    const response = { job_id: "job/one", status: "queued" };
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(response), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();

    await client.job("job/one");
    await client.cancelJob("job/one");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/jobs/job%2Fone",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/jobs/job%2Fone/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

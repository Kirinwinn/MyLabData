type QueryResolver = (url: string, init?: RequestInit) => unknown | undefined;
type Fallback = (url: string, init?: RequestInit) => Promise<Response> | Response;

export function createQueryJobHandler(resolve: QueryResolver, fallback: Fallback) {
  let nextId = 1;
  const results = new Map<string, unknown>();

  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const result = init?.method === "POST" ? resolve(url, init) : undefined;
    if (result !== undefined) {
      const jobId = `query-test-${nextId++}`;
      results.set(jobId, result);
      return json({ job_id: jobId, status: "queued" }, 202);
    }

    const jobId = url.match(/^\/api\/v1\/jobs\/(query-test-\d+)$/)?.[1];
    if (jobId && results.has(jobId)) {
      return json({
        job_id: jobId,
        job_type: "test_query",
        job_kind: "query",
        status: "completed",
        result: results.get(jobId),
        error_message: null,
      });
    }
    return fallback(url, init);
  };
}

export function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

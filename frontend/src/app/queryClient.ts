import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/errors";

function shouldRetry(failureCount: number, error: Error) {
  if (failureCount >= 1) return false;
  return !(error instanceof ApiError) || error.isRetryable;
}

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: shouldRetry,
        staleTime: 30_000,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

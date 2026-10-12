import { QueryClient } from '@tanstack/react-query';

import { ApiError } from '../api/client';

/**
 * Retry once when the backend may come back (unreachable, 5xx). Never retry a 4xx: the
 * answer will not change, and retrying only delays a "not found" the user should see now.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  const clientError =
    error instanceof ApiError &&
    error.kind === 'http' &&
    error.status !== null &&
    error.status < 500;
  return !clientError && failureCount < 1;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Data only changes when a sync runs, so refetching on window focus adds nothing.
        refetchOnWindowFocus: false,
        retry: shouldRetry,
        staleTime: 10_000,
      },
    },
  });
}

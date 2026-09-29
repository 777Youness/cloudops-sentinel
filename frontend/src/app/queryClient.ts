import { QueryClient } from '@tanstack/react-query';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Data only changes when a sync runs, so refetching on window focus adds nothing.
        refetchOnWindowFocus: false,
        retry: 1,
        staleTime: 10_000,
      },
    },
  });
}

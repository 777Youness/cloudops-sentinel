import {
  useIsMutating,
  useMutation,
  useMutationState,
  useQueryClient,
} from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api } from '../../api/client';

const syncKey = ['sync'] as const;

/** Runs a sync, then refreshes everything that depends on synced data. */
export function useSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: syncKey,
    mutationFn: api.sync,
    onSettled: () => queryClient.invalidateQueries(),
  });
}

/**
 * Sync activity across the whole app. Any component can start a sync (top bar, empty state);
 * this reads the shared mutation cache so every component sees the same pending/error state.
 */
export function useSyncActivity(): { pending: boolean; lastError: unknown } {
  const pending = useIsMutating({ mutationKey: syncKey }) > 0;
  const errors = useMutationState({
    filters: { mutationKey: syncKey },
    select: (mutation) => mutation.state.error,
  });
  return { pending, lastError: errors.at(-1) ?? null };
}

/** Seconds elapsed while `active` is true, for "Syncing… 4 s". */
export function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    const started = Date.now();
    const id = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 250);
    return () => {
      window.clearInterval(id);
      setSeconds(0);
    };
  }, [active]);
  return seconds;
}

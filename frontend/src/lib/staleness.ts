/** Staleness rule from docs/design-system.md ("Stale data"). */
export const STALE_AFTER_MS = 15 * 60 * 1000;

/** Data is stale when the last successful sync finished more than 15 minutes ago. */
export function isStale(dataAsOf: string | null | undefined, nowMs: number): boolean {
  if (!dataAsOf) return false; // never synced is its own state, not "stale"
  return nowMs - new Date(dataAsOf).getTime() > STALE_AFTER_MS;
}

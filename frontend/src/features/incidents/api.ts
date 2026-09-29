import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';
import type { IncidentStatusFilter } from '../../api/types';

export function useIncidents(status: IncidentStatusFilter) {
  return useQuery({ queryKey: ['incidents', status], queryFn: () => api.incidents(status) });
}

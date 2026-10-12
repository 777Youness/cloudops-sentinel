import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';

export function useIncident(id: string) {
  return useQuery({ queryKey: ['incident', id], queryFn: () => api.incident(id) });
}

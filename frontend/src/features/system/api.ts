import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';

export const systemKey = ['system'] as const;

export function useSystem() {
  return useQuery({ queryKey: systemKey, queryFn: api.system });
}

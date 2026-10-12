import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiError } from '../../api/client';

export function useIncident(id: string) {
  return useQuery({ queryKey: ['incident', id], queryFn: () => api.incident(id) });
}

const investigationKey = (id: string) => ['investigation', id] as const;

/** The latest saved investigation, or null if none was run (the API answers 404). */
export function useInvestigation(id: string) {
  return useQuery({
    queryKey: investigationKey(id),
    queryFn: async () => {
      try {
        return await api.investigation(id);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
}

/** Runs an investigation (the only request that calls the provider). */
export function useRunInvestigation(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ['run-investigation', id],
    mutationFn: () => api.runInvestigation(id),
    onSuccess: (result) => {
      queryClient.setQueryData(investigationKey(id), result);
      // Lists show the investigation status.
      void queryClient.invalidateQueries({ queryKey: ['incidents'] });
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
    },
  });
}

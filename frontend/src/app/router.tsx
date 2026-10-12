import { createBrowserRouter, Navigate } from 'react-router';

import { IncidentsPage } from '../features/incidents/IncidentsPage';
import { SystemPage } from '../features/system/SystemPage';
import { AppShell } from './AppShell';
import { NotFoundPage } from './NotFoundPage';

// Only built screens are routed. Overview arrives on Day 2; Cost and Drift are not routed in V1.
export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/incidents" replace /> },
      { path: 'incidents', element: <IncidentsPage /> },
      {
        // Loaded on first visit: the charting library is only needed in the workspace.
        path: 'incidents/:id',
        lazy: async () => ({
          Component: (await import('../features/workspace/WorkspacePage')).WorkspacePage,
        }),
      },
      { path: 'system', element: <SystemPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

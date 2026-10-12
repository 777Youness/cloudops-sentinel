import { createBrowserRouter } from 'react-router';

import { IncidentsPage } from '../features/incidents/IncidentsPage';
import { OverviewPage } from '../features/overview/OverviewPage';
import { SystemPage } from '../features/system/SystemPage';
import { AppShell } from './AppShell';
import { NotFoundPage } from './NotFoundPage';

// Only built screens are routed. Resources arrive on Day 5; Cost and Drift are not routed in V1.
export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
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

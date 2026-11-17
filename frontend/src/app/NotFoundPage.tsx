import { Link } from 'react-router';

import { Card } from '../components/Card';
import { EmptyState } from '../components/StateMessage';

export function NotFoundPage() {
  return (
    <Card>
      <EmptyState
        title="This page doesn't exist in this version of Sentinel."
        detail={<Link to="/incidents">Go to incidents</Link>}
      />
    </Card>
  );
}

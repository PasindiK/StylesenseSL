import { SaasHeader } from './SaasHeader';
import { SaasTabs } from './SaasTabs';
import { SaasMetrics } from './SaasMetrics';
import { LiveMetrics } from '../types';

interface SaasDashboardProps {
  metrics: LiveMetrics;
  notificationCount: number;
  onNotificationClick: () => void;
  currentPage: string;
  onPageChange: (page: string) => void;
  children: React.ReactNode;
}

export function SaasDashboard({
  metrics,
  notificationCount,
  onNotificationClick,
  currentPage,
  onPageChange,
  children,
}: SaasDashboardProps) {
  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'governance', label: 'Governance' },
    { id: 'approvals', label: 'Approvals' },
    { id: 'timeline', label: 'Timeline' },
    { id: 'storage', label: 'Storage' },
  ];

  const metricCards = [
    {
      label: 'Total Drifts',
      value: metrics.total_drifts,
      trend: 12,
    },
    {
      label: 'Resolved',
      value: metrics.auto_resolved,
      trend: 8,
    },
    {
      label: 'Pending',
      value: metrics.pending_approvals,
      trend: -3,
    },
    {
      label: 'Quarantined',
      value: metrics.quarantined,
      trend: 0,
    },
  ];

  return (
    <div className="saas-dashboard">
      <SaasHeader notificationCount={notificationCount} onNotificationClick={onNotificationClick} />
      <SaasTabs tabs={tabs} activeTab={currentPage} onTabChange={onPageChange} />
      <div className="saas-content">
        {currentPage === 'overview' && <SaasMetrics metrics={metricCards} />}
        {children}
      </div>
    </div>
  );
}

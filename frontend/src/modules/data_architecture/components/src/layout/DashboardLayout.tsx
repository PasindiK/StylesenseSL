import type { DashboardPageId } from '../types';

interface NavItem {
  id: DashboardPageId;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'live_validation', label: 'Live Validation' },
  { id: 'approvals', label: 'Approvals' },
  { id: 'medallion', label: 'Medallion' },
  { id: 'storage', label: 'Storage' },
  { id: 'explainability', label: 'Explainability' },
  { id: 'actions', label: 'Actions' },
  { id: 'timeline', label: 'Timeline' },
];

interface DashboardLayoutProps {
  currentPage: DashboardPageId;
  onPageChange: (page: DashboardPageId) => void;
  generatedAt?: string;
  refreshing?: boolean;
  children: React.ReactNode;
}

export function DashboardLayout({ currentPage, onPageChange, generatedAt, refreshing = false, children }: DashboardLayoutProps) {
  const generatedLabel = generatedAt ? new Date(generatedAt).toLocaleString() : 'Loading...';

  return (
    <div className="dashboard-shell">
      <header className="dashboard-header animate-rise">
        <div>
          <h1>Lakehouse Data Architecture Control Panel</h1>
          <p>Operational telemetry for the Sri Lankan Fashion Retail lakehouse.</p>
        </div>
        <div className="header-meta">
          <span className={`meta-label ${refreshing ? 'is-running' : ''}`}>
            {refreshing ? 'Refreshing' : 'Live Metrics'}
          </span>
          <span className="meta-value">Updated {generatedLabel}</span>
        </div>
      </header>

      <nav className="dashboard-nav animate-rise">
        {NAV_ITEMS.map((item) => (
          <button
            type="button"
            key={item.id}
            className={`nav-pill ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => onPageChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <main className="dashboard-main">{children}</main>
    </div>
  );
}

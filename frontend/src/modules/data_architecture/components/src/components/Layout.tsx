import { ReactNode, useState } from 'react';
import {
  Bell,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  LayoutDashboard,
  Zap,
  ClipboardCheck,
  CalendarClock,
  BrainCircuit,
  BarChart3,
  Search,
  Landmark,
  HardDrive,
  type LucideIcon,
} from 'lucide-react';

interface LayoutProps {
  children: ReactNode;
  currentPage: string;
  onNavigate: (page: string) => void;
  pipelineStatus: string;
  notificationCount: number;
  onNotificationClick: () => void;
}

export function Layout({
  children,
  currentPage,
  onNavigate,
  pipelineStatus,
  notificationCount,
  onNotificationClick,
}: LayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  type NavItem = {
    id: string;
    label: string;
    icon: LucideIcon;
  };

  const navItems: NavItem[] = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'latest-decision', label: 'Latest Decision', icon: Zap },
    { id: 'approval-queue', label: 'Approval Queue', icon: ClipboardCheck },
    { id: 'decision-timeline', label: 'Decision Timeline', icon: CalendarClock },
    { id: 'explainability', label: 'Explainability', icon: BrainCircuit },
    { id: 'action-distribution', label: 'Action Distribution', icon: BarChart3 },
    { id: 'drift-events', label: 'Recent Drift Events', icon: Search },
    { id: 'medallion', label: 'Medallion Architecture', icon: Landmark },
    { id: 'storage-tiers', label: 'Storage Tiers', icon: HardDrive },
  ];

  return (
    <div className="layout">
      <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <span className="logo-icon">
              <ShieldCheck size={18} strokeWidth={2.2} />
            </span>
            {!sidebarCollapsed && (
              <div className="logo-text-wrap">
                <span className="logo-text">Data Architecture</span>
                <span className="logo-subtext">Control Plane</span>
              </div>
            )}
          </div>
          <button
            className="collapse-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
                onClick={() => onNavigate(item.id)}
                title={sidebarCollapsed ? item.label : undefined}
              >
                <span className="nav-icon">
                  <Icon size={17} strokeWidth={2.1} />
                </span>
                {!sidebarCollapsed && <span className="nav-label">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        {!sidebarCollapsed && (
          <div className="sidebar-footer">
            <div className="sidebar-status">
              <div className="status-label">Pipeline Status</div>
              <div className={`status-value ${pipelineStatus === 'Paused' ? 'danger' : 'success'}`}>
                {pipelineStatus}
              </div>
            </div>
          </div>
        )}
      </aside>

      <div className="main-content">
        <header className="top-bar">
          <div className="page-title-section">
            <h1 className="page-title">
              {navItems.find(item => item.id === currentPage)?.label || 'Dashboard'}
            </h1>
          </div>
          <div className="top-bar-actions">
            <div className={`status-pill ${pipelineStatus === 'Paused' ? 'paused' : 'running'}`}>
              <span className="status-dot"></span>
              {pipelineStatus}
            </div>
            <button className="notification-btn" onClick={onNotificationClick}>
              <span className="bell-icon">
                <Bell size={18} strokeWidth={2.1} />
              </span>
              {notificationCount > 0 && (
                <span className="notification-badge">{notificationCount}</span>
              )}
            </button>
          </div>
        </header>

        <main className="page-content">
          {children}
        </main>

        <footer className="app-footer">
          Schema Drift Control Center · Powered by ML-based policies & human-in-the-loop
        </footer>
      </div>
    </div>
  );
}

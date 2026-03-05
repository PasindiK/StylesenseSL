import { useEffect, useState } from 'react';
import { SaasHeader } from './components/SaasHeader';
import { SaasTabs } from './components/SaasTabs';
import { SaasMetrics } from './components/SaasMetrics';
import { OverviewPage } from './components/OverviewPage';
import { ApprovalQueuePage } from './components/ApprovalQueuePage';
import { DecisionTimelinePage } from './components/DecisionTimelinePage';
import { GovernancePage } from './components/GovernancePage';
import { MedallionPage } from './components/MedallionPage';
import { StorageTiersPage } from './components/StorageTiersPage';
import { NotificationDropdown } from './components/NotificationDropdown';
import { MetricDetailModal } from './components/MetricDetailModal';
import { DashboardData, LiveMetrics, Notification, DriftEvent } from './types';

function Loading() {
  return (
    <div className="loading-screen">
      <div className="loading-spinner"></div>
      <div className="loading-text">Loading dashboard…</div>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState('overview');
  const [showNotifications, setShowNotifications] = useState(false);
  const [selectedMetricType, setSelectedMetricType] = useState<string | null>(null);
  const [latestDecision, setLatestDecision] = useState<NonNullable<DashboardData['latest_decision']> | null>(null);
  const [decisionsTimeline, setDecisionsTimeline] = useState<NonNullable<DashboardData['decisions_timeline']>>([]);
  const [pendingApprovals, setPendingApprovals] = useState<DriftEvent[]>([]);
  const [metrics, setMetrics] = useState<LiveMetrics>({ 
    total_drifts: 0, 
    auto_resolved: 0, 
    pending_approvals: 0, 
    quarantined: 0, 
    pipeline_status: 'Running' 
  });
  const [notifList, setNotifList] = useState<Notification[]>([]);
  const [toast, setToast] = useState<string | null>(null);

  // API Configuration
  const API_BASE_URL = 'http://localhost:8003/api';

  // Fetch dashboard data from API
  const fetchDashboardData = async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/dashboard-data`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = await resp.json();
      
      setData(payload);
      setLatestDecision(payload.latest_decision || null);
      setDecisionsTimeline(payload.decisions_timeline || []);
      setPendingApprovals(payload.pending_approvals || []);
      setMetrics(payload.live_metrics || { 
        total_drifts: 0, 
        auto_resolved: 0, 
        pending_approvals: 0, 
        quarantined: 0, 
        pipeline_status: 'Running' 
      });
      setNotifList(payload.notifications || []);
    } catch (err: any) {
      // Fallback to demo-data.json if API is not available
      console.warn('API not available, falling back to demo-data.json:', err.message);
      try {
        const resp = await fetch('/demo-data.json');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const payload = await resp.json();
        setData(payload);
        setLatestDecision(payload.latest_decision || null);
        setDecisionsTimeline(payload.decisions_timeline || []);
        setPendingApprovals(payload.pending_approvals || []);
        setMetrics(payload.live_metrics || { total_drifts: 0, auto_resolved: 0, pending_approvals: 0, quarantined: 0, pipeline_status: 'Running' });
        setNotifList(payload.notifications || []);
      } catch (fallbackErr: any) {
        setError(fallbackErr.message);
      }
    }
  };

  useEffect(() => {
    fetchDashboardData();
    
    // Auto-refresh every 10 seconds
    const interval = setInterval(fetchDashboardData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleApprove = async (table: string) => {
    try {
      // Find the event for this table
      const event = pendingApprovals.find(evt => evt.table === table);
      if (!event) return;

      // Call API to approve
      const resp = await fetch(`${API_BASE_URL}/approve-drift`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          table: table, 
          event_id: event.file || `drift_${table}_${Date.now()}.json` 
        })
      });

      if (resp.ok) {
        // Update local state
        setPendingApprovals((prev) => prev.filter((evt) => evt.table !== table));
        setDecisionsTimeline((prev) =>
          prev.map((item) => (item?.table === table ? { ...item, approval_status: 'Approved' } : item))
        );
        if (latestDecision?.table === table) {
          setLatestDecision({ ...latestDecision, approval_status: 'Approved', action: 'APPROVED' });
        }
        setMetrics((prev) => {
          const pending = Math.max(0, prev.pending_approvals - 1);
          return {
            ...prev,
            pending_approvals: pending,
            auto_resolved: prev.auto_resolved + 1,
            pipeline_status: pending === 0 ? 'Running' : prev.pipeline_status,
          };
        });
        setNotifList((prev) => [
          {
            timestamp: new Date().toISOString(),
            table,
            reason: 'Approval applied — pipeline can resume.',
            type: 'approval',
            risk_level: 'medium',
          },
          ...prev,
        ]);
        setToast('✓ Approval recorded. Resume pipeline to continue.');
        setTimeout(() => setToast(null), 2500);
        
        // Refresh data from backend
        fetchDashboardData();
      }
    } catch (error) {
      console.error('Error approving drift:', error);
      // Fallback to local update if API fails
      setPendingApprovals((prev) => prev.filter((evt) => evt.table !== table));
      setDecisionsTimeline((prev) =>
        prev.map((item) => (item?.table === table ? { ...item, approval_status: 'Approved' } : item))
      );
      if (latestDecision?.table === table) {
        setLatestDecision({ ...latestDecision, approval_status: 'Approved', action: 'APPROVED' });
      }
      setMetrics((prev) => {
        const pending = Math.max(0, prev.pending_approvals - 1);
        return {
          ...prev,
          pending_approvals: pending,
          auto_resolved: prev.auto_resolved + 1,
          pipeline_status: pending === 0 ? 'Running' : prev.pipeline_status,
        };
      });
      setNotifList((prev) => [
        {
          timestamp: new Date().toISOString(),
          table,
          reason: 'Approval applied — pipeline can resume.',
          type: 'approval',
          risk_level: 'medium',
        },
        ...prev,
      ]);
      setToast('✓ Approval recorded. Resume pipeline to continue.');
      setTimeout(() => setToast(null), 2500);
    }
  };

  const handleReject = async (table: string) => {
    try {
      // Find the event for this table
      const event = pendingApprovals.find(evt => evt.table === table);
      if (!event) return;

      // Call API to reject
      const resp = await fetch(`${API_BASE_URL}/reject-drift`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          table: table, 
          event_id: event.file || `drift_${table}_${Date.now()}.json` 
        })
      });

      if (resp.ok) {
        // Update local state
        setPendingApprovals((prev) => prev.filter((evt) => evt.table !== table));
        setDecisionsTimeline((prev) =>
          prev.map((item) => (item?.table === table ? { ...item, approval_status: 'Rejected' } : item))
        );
        if (latestDecision?.table === table) {
          setLatestDecision({ ...latestDecision, approval_status: 'Rejected', action: 'REJECTED' });
        }
        setMetrics((prev) => ({
          ...prev,
          pending_approvals: Math.max(0, prev.pending_approvals - 1),
          quarantined: prev.quarantined + 1,
        }));
        setNotifList((prev) => [
          {
            timestamp: new Date().toISOString(),
            table,
            reason: 'Rejection recorded — data quarantined, pipeline paused.',
            type: 'quarantine',
            risk_level: 'high',
          },
          ...prev,
        ]);
        setToast(`❌ Rejected: ${table}`);
        
        // Refresh data from backend
        fetchDashboardData();
      }
    } catch (error) {
      console.error('Error rejecting drift:', error);
      // Fallback to local update if API fails
      setPendingApprovals((prev) => prev.filter((evt) => evt.table !== table));
      setDecisionsTimeline((prev) =>
        prev.map((item) => (item?.table === table ? { ...item, approval_status: 'Rejected' } : item))
      );
      if (latestDecision?.table === table) {
        setLatestDecision({ ...latestDecision, approval_status: 'Rejected', action: 'REJECTED' });
      }
      setMetrics((prev) => ({
        ...prev,
        pending_approvals: Math.max(0, prev.pending_approvals - 1),
        quarantined: prev.quarantined + 1,
        pipeline_status: 'Paused',
      }));
      setNotifList((prev) => [
        {
          timestamp: new Date().toISOString(),
          table,
          reason: 'Rejection recorded — data quarantined, pipeline paused.',
          type: 'quarantine',
          risk_level: 'high',
        },
        ...prev,
      ]);
      setToast(`❌ Rejected: ${table}`);
    }
  };

  if (error) {
    return (
      <div className="error-screen">
        <div className="error-icon">❌</div>
        <div className="error-message">Error: {error}</div>
      </div>
    );
  }
  
  if (!data) return <Loading />;

  const unreadNotifications = notifList.filter(
    (n) => n.type === 'approval' || n.type === 'quarantine'
  );

  const renderPage = () => {
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

    switch (currentPage) {
      case 'overview':
        return (
          <>
            <SaasMetrics metrics={metricCards} />
            <OverviewPage
              metrics={metrics}
              onMetricClick={setSelectedMetricType}
            />
          </>
        );
      
      case 'governance':
        return (
          <GovernancePage />
        );
      
      case 'medallion':
        return (
          <MedallionPage
            architecture={data.architecture || { stages: [] }}
            datasetOverview={data.dataset_overview}
            csvPreviews={data.csv_previews}
          />
        );
      
      case 'approvals':
        return (
          <ApprovalQueuePage
            pendingApprovals={pendingApprovals}
            onApprove={handleApprove}
            onReject={handleReject}
          />
        );
      
      case 'timeline':
        return (
          <DecisionTimelinePage
            decisionsTimeline={decisionsTimeline}
          />
        );
      
      case 'storage':
        return (
          <StorageTiersPage
            architecture={data.architecture || { stages: [] }}
            csvPreviews={data.csv_previews}
          />
        );
      
      default:
        return (
          <>
            <SaasMetrics metrics={metricCards} />
            <OverviewPage metrics={metrics} onMetricClick={setSelectedMetricType} />
          </>
        );
    }
  };

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'governance', label: 'Governance' },
    { id: 'medallion', label: 'Medallion' },
    { id: 'approvals', label: 'Approvals' },
    { id: 'timeline', label: 'Timeline' },
    { id: 'storage', label: 'Storage' },
  ];

  return (
    <div className="saas-dashboard">
      <SaasHeader
        notificationCount={unreadNotifications.length}
        onNotificationClick={() => setShowNotifications(!showNotifications)}
      />
      <SaasTabs tabs={tabs} activeTab={currentPage} onTabChange={setCurrentPage} />
      <div className="saas-content">
        {renderPage()}
      </div>

      <NotificationDropdown
        notifications={notifList}
        isOpen={showNotifications}
        onClose={() => setShowNotifications(false)}
      />

      <MetricDetailModal
        metricType={selectedMetricType}
        data={data}
        onClose={() => setSelectedMetricType(null)}
      />

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}


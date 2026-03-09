import { useEffect, useState } from 'react';
import { ToastProvider } from './notifications/ToastProvider';
import { DashboardLayout } from './layout/DashboardLayout';
import { LoadingPanel } from './panels/Panel';
import { useDashboardSummary } from './hooks/useDashboardSummary';
import { OverviewPage } from './pages/OverviewPage';
import { GovernancePage } from './pages/GovernancePage';
import { ExplainabilityPage } from './pages/ExplainabilityPage';
import { ActionsPage } from './pages/ActionsPage';
import { MedallionPage } from './pages/MedallionPage';
import { ApprovalsPage } from './pages/ApprovalsPage';
import { TimelinePage } from './pages/TimelinePage';
import { StoragePage } from './pages/StoragePage';
import { LiveValidationPage } from './pages/LiveValidationPage';
import type { DashboardPageId, LayerId, MedallionFilesResponse } from './types';
import * as dashboardApi from './api/dashboardApi';


export default function App() {
  const [currentPage, setCurrentPage] = useState<DashboardPageId>('overview');
  const { summary, loading, refreshing, error, refresh } = useDashboardSummary({
    autoRefreshMs: 45000,
  });
  
  // Additional medallion files state (if used by MedallionPage)
  const [medallionFiles, setMedallionFiles] = useState<Partial<Record<LayerId, MedallionFilesResponse>>>({});

  // Load medallion files on demand when navigating to that page
  const loadMedallionFiles = async () => {
    try {
      const [bronze, silver, gold] = await Promise.all([
        dashboardApi.getMedallionFiles('bronze'),
        dashboardApi.getMedallionFiles('silver'),
        dashboardApi.getMedallionFiles('gold'),
      ]);
      setMedallionFiles({ bronze, silver, gold });
    } catch (err) {
      console.error('Failed to load medallion files:', err);
    }
  };

  useEffect(() => {
    if (currentPage === 'medallion' && Object.keys(medallionFiles).length === 0) {
      loadMedallionFiles();
    }
  }, [currentPage, medallionFiles]);

  if (error) {
    return (
      <ToastProvider>
        <div style={{ padding: '2rem', textAlign: 'center' }}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>❌</div>
          <div style={{ fontSize: '1.2rem', color: '#dc2626', marginBottom: '0.5rem' }}>
            Error loading dashboard
          </div>
          <div style={{ fontSize: '0.9rem', color: '#6b7280' }}>{error}</div>
          <button
            onClick={refresh}
            style={{
              marginTop: '1.5rem',
              padding: '0.6rem 1.2rem',
              backgroundColor: '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.95rem',
            }}
          >
            Retry
          </button>
        </div>
      </ToastProvider>
    );
  }

  if (loading || !summary) {
    return (
      <ToastProvider>
        <LoadingPanel title="Loading Dashboard" message="Loading dashboard data..." />
      </ToastProvider>
    );
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'overview':
        return <OverviewPage summary={summary} />;
      case 'live_validation':
        return <LiveValidationPage summary={summary} onOperationFinished={refresh} />;
      case 'governance':
        return <GovernancePage summary={summary} />;
      case 'explainability':
        return <ExplainabilityPage summary={summary} />;
      case 'actions':
        return (
          <ActionsPage
            pipelineStatus={summary.actions.pipeline_status}
            stakeholderViewCount={summary.governance.stakeholder_access.length}
            onOperationFinished={refresh}
          />
        );
      case 'medallion':
        return (
          <MedallionPage
            summary={summary}
            medallionFiles={medallionFiles}
            loading={Object.keys(medallionFiles).length === 0}
          />
        );
      case 'approvals':
        return <ApprovalsPage summary={summary} onOperationFinished={refresh} />;
      case 'timeline':
        return <TimelinePage summary={summary} />;
      case 'storage':
        return <StoragePage summary={summary} />;
      default:
        return <OverviewPage summary={summary} />;
    }
  };

  return (
    <ToastProvider>
      <DashboardLayout
        currentPage={currentPage}
        onPageChange={setCurrentPage}
        refreshing={refreshing}
        generatedAt={summary.generated_at}
      >
        {renderPage()}
      </DashboardLayout>
    </ToastProvider>
  );
}


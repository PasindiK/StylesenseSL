import React, { useState } from 'react';
import type { DashboardSummaryResponse } from '../types';
import { Panel } from '../panels/Panel';
import { MetricCard } from '../cards/MetricCard';
import { useToast } from '../notifications/ToastProvider';
import * as dashboardApi from '../api/dashboardApi';

interface ApprovalsPageProps {
  summary: DashboardSummaryResponse;
  onOperationFinished?: () => void | Promise<void>;
}

const ApprovalsPage: React.FC<ApprovalsPageProps> = ({ summary, onOperationFinished }) => {
  const { approvals } = summary;
  const { showToast } = useToast();
  const [processingId, setProcessingId] = useState<string | null>(null);

  const handleApprove = async (table: string, eventId: string, description: string) => {
    setProcessingId(eventId);
    showToast(`Approving drift: ${description}`, 'running', 1800);
    try {
      const response = await dashboardApi.approveDrift(table, eventId);
      showToast(`Drift ${response.status}: ${response.table}`, 'success');
      if (onOperationFinished) await onOperationFinished();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Approval failed';
      showToast(message, 'error');
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (table: string, eventId: string, description: string) => {
    setProcessingId(eventId);
    showToast(`Rejecting drift: ${description}`, 'running', 1800);
    try {
      const response = await dashboardApi.rejectDrift(table, eventId);
      showToast(`Drift ${response.status}: ${response.table}`, 'success');
      if (onOperationFinished) await onOperationFinished();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Rejection failed';
      showToast(message, 'error');
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="grid-12 animate-fade page-grid">
      {/* Approval Metrics Row */}
      <div className="span-4">
        <MetricCard
          label="Pending Approvals"
          value={approvals.pending_count}
          hint="Awaiting decision"
          tone={approvals.pending_count > 5 ? 'warning' : 'neutral'}
        />
      </div>
      <div className="span-4">
        <MetricCard
          label="Approved (Today)"
          value={approvals.approved_count}
          hint="Schema drifts accepted"
          tone="positive"
        />
      </div>
      <div className="span-4">
        <MetricCard
          label="Rejected (Today)"
          value={approvals.rejected_count}
          hint="Schema drifts denied"
          tone="neutral"
        />
      </div>

      {/* Approval Queue Table */}
      <div className="span-12">
        <Panel
          title="Approval Queue"
          subtitle={`${approvals.events.length} drift events awaiting decision`}
        >
          <div className="table-scroll table-scroll-tall">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Dataset</th>
                  <th>Drift Type</th>
                  <th>Description</th>
                  <th>Records Affected</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {approvals.events.length > 0 ? (
                  approvals.events.map((drift: any) => (
                    <tr key={drift.file || drift.table}>
                      <td>{new Date(drift.timestamp).toLocaleString()}</td>
                      <td>{drift.table}</td>
                      <td>
                        <span
                          style={{
                            padding: '0.25rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.8rem',
                            backgroundColor: '#dbeafe',
                            color: '#1e40af',
                          }}
                        >
                          schema
                        </span>
                      </td>
                      <td>{drift.decision || 'Pending review'}</td>
                      <td>{(drift.counts?.new || 0) + (drift.counts?.missing || 0)}</td>
                      <td>
                        <span
                          className="log-status-pending"
                          style={{
                            padding: '0.25rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.8rem',
                            backgroundColor: drift.approved ? '#d1fae5' : drift.rejected ? '#fee2e2' : '#fef3c7',
                            color: drift.approved ? '#065f46' : drift.rejected ? '#991b1b' : '#92400e',
                          }}
                        >
                          {drift.approved ? 'approved' : drift.rejected ? 'rejected' : 'pending'}
                        </span>
                      </td>
                      <td>
                        {!drift.approved && !drift.rejected && (
                          <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button
                              onClick={() => handleApprove(drift.table, drift.file || drift.table, drift.decision || '')}
                              disabled={processingId === (drift.file || drift.table)}
                              style={{
                                padding: '0.4rem 0.8rem',
                                fontSize: '0.85rem',
                                backgroundColor: '#10b981',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: processingId === (drift.file || drift.table) ? 'not-allowed' : 'pointer',
                                opacity: processingId === (drift.file || drift.table) ? 0.6 : 1,
                              }}
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => handleReject(drift.table, drift.file || drift.table, drift.decision || '')}
                              disabled={processingId === (drift.file || drift.table)}
                              style={{
                                padding: '0.4rem 0.8rem',
                                fontSize: '0.85rem',
                                backgroundColor: '#ef4444',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: processingId === (drift.file || drift.table) ? 'not-allowed' : 'pointer',
                                opacity: processingId === (drift.file || drift.table) ? 0.6 : 1,
                              }}
                            >
                              Reject
                            </button>
                          </div>
                        )}
                        {(drift.approved || drift.rejected) && <span style={{ color: '#9ca3af' }}>—</span>}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr className="loading-row">
                    <td colSpan={7}>No pending approvals</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
};

export { ApprovalsPage };

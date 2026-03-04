import { Badge } from './Badge';
import { DashboardData } from '../types';

interface DecisionTimelinePageProps {
  decisionsTimeline: NonNullable<DashboardData['decisions_timeline']>;
}

export function DecisionTimelinePage({ decisionsTimeline }: DecisionTimelinePageProps) {
  if (!decisionsTimeline || decisionsTimeline.length === 0) {
    return (
      <div className="page-section">
        <div className="empty-state">
          <div className="empty-icon">📅</div>
          <h3>No Decision History</h3>
          <p>Decision history will appear here as schema drift events are processed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Decision Timeline</h2>
        <Badge label={`${decisionsTimeline.length} decisions`} tone="info" />
      </div>

      <div className="card">
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Table</th>
                <th>Action</th>
                <th>Status</th>
                <th>Confidence</th>
                <th>Risk</th>
                <th>Changes</th>
              </tr>
            </thead>
            <tbody>
              {decisionsTimeline.map((row, idx) => (
                <tr key={idx}>
                  <td className="table-cell-timestamp">{row.timestamp}</td>
                  <td className="table-cell-main">{row.table}</td>
                  <td>
                    <Badge label={row.action || 'N/A'} tone="info" />
                  </td>
                  <td>
                    <Badge
                      label={row.approval_status || 'Unknown'}
                      tone={
                        row.approval_status === 'Approved' ? 'success' :
                        row.approval_status === 'Rejected' ? 'danger' :
                        row.approval_status === 'Auto' ? 'success' :
                        'warning'
                      }
                    />
                  </td>
                  <td>{((row.policy_confidence || 0) * 100).toFixed(0)}%</td>
                  <td>
                    <Badge
                      tone={
                        row.risk_level === 'high' ? 'danger' :
                        row.risk_level === 'medium' ? 'warning' :
                        'success'
                      }
                      label={row.risk_level || 'low'}
                    />
                  </td>
                  <td className="table-cell-changes">
                    <div className="change-summary compact">
                      {row.counts?.new ? <span>+{row.counts.new}</span> : null}
                      {row.counts?.missing ? <span>-{row.counts.missing}</span> : null}
                      {row.counts?.dtype ? <span>Δ{row.counts.dtype}</span> : null}
                      {row.counts?.renames ? <span>↻{row.counts.renames}</span> : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

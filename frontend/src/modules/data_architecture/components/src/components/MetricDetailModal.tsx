import { Badge } from './Badge';
import { DashboardData, QuarantineItem } from '../types';

interface MetricDetailModalProps {
  metricType: string | null;
  data: DashboardData | null;
  onClose: () => void;
}

export function MetricDetailModal({ metricType, data, onClose }: MetricDetailModalProps) {
  if (!metricType || !data) return null;

  const renderQuarantineDetails = () => {
    const quarantined = data.detailed_metrics?.quarantined_list || [];
    
    if (quarantined.length === 0) {
      return (
        <div className="empty-state">
          <div className="empty-icon">✅</div>
          <p>No datasets quarantined</p>
        </div>
      );
    }

    return (
      <div className="quarantine-list">
        {quarantined.map((item: QuarantineItem, idx: number) => (
          <div key={idx} className="quarantine-detail-card">
            <div className="quarantine-header">
              <div>
                <div className="quarantine-dataset">{item.dataset}</div>
                <div className="quarantine-meta">
                  File: {item.filename} · Quarantined: {item.quarantine_date}
                </div>
              </div>
              <Badge label={item.status} tone="danger" />
            </div>

            <div className="quarantine-section">
              <h4>⚠️ Quarantine Reasons</h4>
              <ul className="failure-list">
                {item.reason.map((reason, rIdx) => (
                  <li key={rIdx}>{reason}</li>
                ))}
              </ul>
            </div>

            {item.preview && item.preview.length > 0 && (
              <div className="quarantine-section">
                <h4>📊 Data Preview</h4>
                <p className="preview-info">
                  {item.rows_preview} rows × {item.columns.length} columns
                </p>
                <div className="table-wrapper">
                  <table className="data-table compact">
                    <thead>
                      <tr>
                        {item.columns.slice(0, 6).map((col, cIdx) => (
                          <th key={cIdx}>{col}</th>
                        ))}
                        {item.columns.length > 6 && <th>...</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {item.preview.slice(0, 10).map((row, rowIdx) => (
                        <tr key={rowIdx}>
                          {item.columns.slice(0, 6).map((col, colIdx) => (
                            <td key={colIdx}>
                              {row[col] !== null && row[col] !== undefined
                                ? String(row[col]).substring(0, 30)
                                : 'NULL'}
                            </td>
                          ))}
                          {item.columns.length > 6 && <td>...</td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="quarantine-actions">
              <button className="btn btn-danger">
                ✗ Keep Quarantined
              </button>
              <button className="btn btn-success">
                ✓ Approve & Continue Pipeline
              </button>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderMetricTable = () => {
    const metricData =
      metricType === 'total_drifts' ? data.detailed_metrics?.total_drifts_list :
      metricType === 'auto_resolved' ? data.detailed_metrics?.auto_resolved_list :
      metricType === 'pending_approvals' ? data.detailed_metrics?.pending_approvals_list :
      [];

    if (!metricData || metricData.length === 0) {
      return (
        <div className="empty-state">
          <div className="empty-icon">📭</div>
          <p>No data available</p>
        </div>
      );
    }

    return (
      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Table</th>
              <th>Action</th>
              <th>Status</th>
              <th>Risk</th>
              <th>Changes</th>
            </tr>
          </thead>
          <tbody>
            {metricData.map((event, idx) => (
              <tr key={idx}>
                <td className="table-cell-timestamp">{event.timestamp}</td>
                <td className="table-cell-main">{event.table}</td>
                <td>
                  <Badge label={event.action || 'N/A'} tone="info" />
                </td>
                <td>
                  <Badge
                    label={event.approval_status || 'Unknown'}
                    tone={
                      event.approval_status === 'Auto' ? 'success' :
                      event.approval_status === 'Pending' ? 'warning' :
                      'info'
                    }
                  />
                </td>
                <td>
                  <Badge
                    label={event.risk_level || 'low'}
                    tone={
                      event.risk_level === 'high' ? 'danger' :
                      event.risk_level === 'medium' ? 'warning' :
                      'success'
                    }
                  />
                </td>
                <td className="table-cell-changes">
                  <div className="change-summary compact">
                    {event.counts?.new ? <span>+{event.counts.new}</span> : null}
                    {event.counts?.missing ? <span>-{event.counts.missing}</span> : null}
                    {event.counts?.dtype ? <span>Δ{event.counts.dtype}</span> : null}
                    {event.counts?.renames ? <span>↻{event.counts.renames}</span> : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const getTitle = () => {
    switch (metricType) {
      case 'total_drifts': return 'All Drift Events';
      case 'auto_resolved': return 'Auto-Resolved Drifts';
      case 'pending_approvals': return 'Pending Approvals';
      case 'quarantined': return 'Quarantined Datasets';
      default: return 'Metric Details';
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 className="modal-title">{getTitle()}</h3>
          <button className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="modal-body">
          {metricType === 'quarantined' ? renderQuarantineDetails() : renderMetricTable()}
        </div>
      </div>
    </div>
  );
}

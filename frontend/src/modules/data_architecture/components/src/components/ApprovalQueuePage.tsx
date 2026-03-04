import { Badge } from './Badge';
import { DriftEvent } from '../types';

interface ApprovalQueuePageProps {
  pendingApprovals: DriftEvent[];
  onApprove: (table: string) => void;
  onReject: (table: string) => void;
}

export function ApprovalQueuePage({
  pendingApprovals,
  onApprove,
  onReject,
}: ApprovalQueuePageProps) {
  if (pendingApprovals.length === 0) {
    return (
      <div className="page-section">
        <div className="empty-state">
          <div className="empty-icon">✅</div>
          <h3>No Pending Approvals</h3>
          <p>All schema drift events have been reviewed. The pipeline is running smoothly.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Approval Queue</h2>
        <Badge label={`${pendingApprovals.length} awaiting action`} tone="warning" />
      </div>

      <div className="info-banner warning">
        <span className="banner-icon">⚠️</span>
        <div>
          <strong>Action Required:</strong> {pendingApprovals.length} schema drift event{pendingApprovals.length > 1 ? 's' : ''} awaiting your approval. 
          Review changes carefully before approving to resume pipeline.
        </div>
      </div>

      <div className="card">
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Table</th>
                <th>Timestamp</th>
                <th>Risk Level</th>
                <th>Changes</th>
                <th>Confidence</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pendingApprovals.map((evt) => (
                <tr key={evt.file}>
                  <td>
                    <div className="table-cell-main">{evt.table}</div>
                    <div className="table-cell-sub">{evt.file}</div>
                  </td>
                  <td className="table-cell-timestamp">{evt.timestamp}</td>
                  <td>
                    <Badge
                      tone={
                        evt.risk_level === 'high' ? 'danger' : 
                        evt.risk_level === 'medium' ? 'warning' : 
                        'success'
                      }
                      label={evt.risk_level || 'low'}
                    />
                  </td>
                  <td className="table-cell-changes">
                    <div className="change-summary">
                      {evt.counts?.new ? <span className="change-item">+{evt.counts.new} new</span> : null}
                      {evt.counts?.missing ? <span className="change-item danger">-{evt.counts.missing} missing</span> : null}
                      {evt.counts?.dtype ? <span className="change-item warning">{evt.counts.dtype} types</span> : null}
                      {evt.counts?.renames ? <span className="change-item info">↻{evt.counts.renames} renamed</span> : null}
                    </div>
                  </td>
                  <td>
                    <Badge label="High" tone="success" />
                  </td>
                  <td>
                    <div className="table-actions">
                      <button 
                        className="btn-small btn-success" 
                        onClick={() => onApprove(evt.table)}
                      >
                        Approve
                      </button>
                      <button 
                        className="btn-small btn-danger" 
                        onClick={() => onReject(evt.table)}
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="help-text">
        <strong>Tip:</strong> Approve to resume pipeline; Reject to keep data quarantined for manual review.
      </div>
    </div>
  );
}

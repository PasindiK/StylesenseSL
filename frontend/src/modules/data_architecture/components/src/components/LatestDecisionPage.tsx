import { Badge } from './Badge';
import { DashboardData, LiveMetrics } from '../types';

interface LatestDecisionPageProps {
  latestDecision: NonNullable<DashboardData['latest_decision']> | null;
  metrics: LiveMetrics;
  onApprove: (table: string) => void;
  onReject: (table: string) => void;
}

export function LatestDecisionPage({
  latestDecision,
  metrics,
  onApprove,
  onReject,
}: LatestDecisionPageProps) {
  if (!latestDecision) {
    return (
      <div className="page-section">
        <div className="empty-state">
          <div className="empty-icon">📭</div>
          <h3>No Recent Decisions</h3>
          <p>No schema drift decisions have been made yet. Start processing data to see drift events.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Latest Decision</h2>
        <Badge 
          label={latestDecision.approval_status || 'Unknown'} 
          tone={
            latestDecision.approval_status === 'Approved' ? 'success' : 
            latestDecision.approval_status === 'Rejected' ? 'danger' : 
            'warning'
          } 
        />
      </div>

      <div className="decision-card">
        <div className="decision-main">
          <div className="decision-header">
            <div>
              <h3 className="decision-table">{latestDecision.table}</h3>
              <div className="decision-timestamp">{latestDecision.timestamp}</div>
            </div>
            <div className="decision-badges">
              <Badge label={latestDecision.action || 'N/A'} tone="info" />
              <Badge 
                label={`Confidence: ${((latestDecision.policy_confidence || 0) * 100).toFixed(0)}%`} 
              />
              <Badge
                label={`Risk: ${latestDecision.risk_level}`}
                tone={
                  latestDecision.risk_level === 'high' ? 'danger' : 
                  latestDecision.risk_level === 'medium' ? 'warning' : 
                  'success'
                }
              />
              <Badge
                label={`Pipeline: ${metrics.pipeline_status}`}
                tone={metrics.pipeline_status === 'Paused' ? 'danger' : 'success'}
              />
            </div>
          </div>

          <div className="decision-details">
            <div className="detail-row">
              <span className="detail-label">New Columns:</span>
              <span className="detail-value">{latestDecision.counts?.new ?? 0}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Missing Columns:</span>
              <span className="detail-value">{latestDecision.counts?.missing ?? 0}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Type Changes:</span>
              <span className="detail-value">{latestDecision.counts?.dtype ?? 0}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Renamed Columns:</span>
              <span className="detail-value">{latestDecision.counts?.renames ?? 0}</span>
            </div>
          </div>

          {latestDecision.approval_status === 'Pending' && (
            <div className="decision-actions">
              <button 
                className="btn btn-success" 
                onClick={() => onApprove(latestDecision.table || '')}
              >
                <span>✓</span> Approve
              </button>
              <button 
                className="btn btn-danger" 
                onClick={() => onReject(latestDecision.table || '')}
              >
                <span>✗</span> Reject
              </button>
            </div>
          )}
        </div>

        <div className="decision-sidebar">
          <h4>Decision Impact</h4>
          {latestDecision.approval_status === 'Pending' ? (
            <div className="impact-info warning">
              <p><strong>Approval:</strong> Resume pipeline and apply schema changes</p>
              <p><strong>Rejection:</strong> Quarantine data and pause pipeline</p>
            </div>
          ) : latestDecision.approval_status === 'Approved' ? (
            <div className="impact-info success">
              <p>✓ Pipeline resumed with approved schema changes</p>
            </div>
          ) : (
            <div className="impact-info danger">
              <p>✗ Data quarantined, manual review required</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

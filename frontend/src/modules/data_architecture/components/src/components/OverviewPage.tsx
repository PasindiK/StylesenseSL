import { LiveMetrics } from '../types';

interface OverviewPageProps {
  metrics: LiveMetrics;
  onMetricClick: (type: string) => void;
}

export function OverviewPage({ metrics, onMetricClick }: OverviewPageProps) {
  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Live Metrics Overview</h2>
        <p className="section-description">Real-time monitoring of schema drift detection and resolution</p>
      </div>

      <div className="metrics-grid">
        <div 
          className="metric-card clickable" 
          onClick={() => onMetricClick('total_drifts')}
        >
          <div className="metric-icon">📊</div>
          <div className="metric-content">
            <div className="metric-value">{metrics.total_drifts}</div>
            <div className="metric-label">Total Drifts</div>
            <div className="metric-description">All detected schema changes</div>
          </div>
        </div>

        <div 
          className="metric-card success clickable" 
          onClick={() => onMetricClick('auto_resolved')}
        >
          <div className="metric-icon">✅</div>
          <div className="metric-content">
            <div className="metric-value">{metrics.auto_resolved}</div>
            <div className="metric-label">Auto-Resolved</div>
            <div className="metric-description">Automatically handled by ML policies</div>
          </div>
        </div>

        <div 
          className="metric-card warning clickable" 
          onClick={() => onMetricClick('pending_approvals')}
        >
          <div className="metric-icon">⏳</div>
          <div className="metric-content">
            <div className="metric-value">{metrics.pending_approvals}</div>
            <div className="metric-label">Pending Approvals</div>
            <div className="metric-description">Awaiting human review</div>
          </div>
        </div>

        <div 
          className="metric-card danger clickable" 
          onClick={() => onMetricClick('quarantined')}
        >
          <div className="metric-icon">🚫</div>
          <div className="metric-content">
            <div className="metric-value">{metrics.quarantined}</div>
            <div className="metric-label">Quarantined</div>
            <div className="metric-description">Data quality failures</div>
          </div>
        </div>
      </div>

      <div className="info-card">
        <div className="info-icon">ℹ️</div>
        <div className="info-content">
          <h4>How It Works</h4>
          <p>
            Our ML-based schema drift detection system automatically identifies and resolves safe schema changes.
            High-risk changes require human approval to maintain data integrity. Click any metric above to see detailed breakdown.
          </p>
        </div>
      </div>
    </div>
  );
}

import { TrendingUp, CheckCircle2, Clock, AlertTriangle, Activity, Database, Zap, Shield } from 'lucide-react';
import { LiveMetrics } from '../types';
import { Badge } from './Badge';

interface OverviewPageProps {
  metrics: LiveMetrics;
  onMetricClick: (type: string) => void;
}

export function OverviewPage({ metrics, onMetricClick }: OverviewPageProps) {
  // Calculate additional insights
  const totalProcessed = metrics.total_drifts || 0;
  const autoResolved = metrics.auto_resolved || 0;
  const pending = metrics.pending_approvals || 0;
  const quarantined = metrics.quarantined || 0;
  
  const automationRate = totalProcessed > 0 ? Math.round((autoResolved / totalProcessed) * 100) : 0;
  const successRate = totalProcessed > 0 ? Math.round(((autoResolved + pending) / totalProcessed) * 100) : 100;
  const avgResolutionTime = '2.3h'; // Mock data - replace with real calculation

  return (
    <div className="page-section">
      {/* Key Insights Section */}
      <div className="insights-grid">
        <div className="insight-card primary">
          <div className="insight-header">
            <div className="insight-icon">
              {/* @ts-ignore */}
              <Activity size={24} strokeWidth={2} />
            </div>
            <Badge label={metrics.pipeline_status || 'Running'} tone="success" />
          </div>
          <div className="insight-content">
            <h3>Pipeline Health</h3>
            <div className="insight-value">{successRate}%</div>
            <p className="insight-description">Successfully processed without failures</p>
          </div>
        </div>

        <div className="insight-card success">
          <div className="insight-header">
            <div className="insight-icon">
              {/* @ts-ignore */}
              <Zap size={24} strokeWidth={2} />
            </div>
            <span className="insight-badge positive">+{automationRate}%</span>
          </div>
          <div className="insight-content">
            <h3>Automation Rate</h3>
            <div className="insight-value">{automationRate}%</div>
            <p className="insight-description">Drifts resolved automatically by ML</p>
          </div>
        </div>

        <div className="insight-card info">
          <div className="insight-header">
            <div className="insight-icon">
              {/* @ts-ignore */}
              <Clock size={24} strokeWidth={2} />
            </div>
            <span className="insight-badge neutral">Avg</span>
          </div>
          <div className="insight-content">
            <h3>Resolution Time</h3>
            <div className="insight-value">{avgResolutionTime}</div>
            <p className="insight-description">Average time to resolve drifts</p>
          </div>
        </div>

        <div className="insight-card warning">
          <div className="insight-header">
            <div className="insight-icon">
              {/* @ts-ignore */}
              <Shield size={24} strokeWidth={2} />
            </div>
            <Badge label="Active" tone="info" />
          </div>
          <div className="insight-content">
            <h3>Governance Rules</h3>
            <div className="insight-value">24</div>
            <p className="insight-description">Quality rules enforced across pipeline</p>
          </div>
        </div>
      </div>

      {/* Detailed Metrics Grid */}
      <div className="section-header" style={{ marginTop: '40px' }}>
        <h2>Drift Detection Metrics</h2>
        <p className="section-description">Real-time monitoring of schema changes and resolutions</p>
      </div>

      <div className="metrics-detail-grid">
        <div 
          className="metric-detail-card clickable" 
          onClick={() => onMetricClick('total_drifts')}
        >
          <div className="metric-detail-header">
            <div className="metric-detail-icon primary">
              {/* @ts-ignore */}
              <Database size={20} strokeWidth={2} />
            </div>
            <span className="metric-trend positive">↑ 12%</span>
          </div>
          <div className="metric-detail-value">{metrics.total_drifts}</div>
          <div className="metric-detail-label">Total Drifts Detected</div>
          <div className="metric-detail-footer">
            <span className="metric-detail-sub">All schema changes identified</span>
          </div>
        </div>

        <div 
          className="metric-detail-card clickable" 
          onClick={() => onMetricClick('auto_resolved')}
        >
          <div className="metric-detail-header">
            <div className="metric-detail-icon success">
              {/* @ts-ignore */}
              <CheckCircle2 size={20} strokeWidth={2} />
            </div>
            <span className="metric-trend positive">↑ 8%</span>
          </div>
          <div className="metric-detail-value">{metrics.auto_resolved}</div>
          <div className="metric-detail-label">Auto-Resolved</div>
          <div className="metric-detail-footer">
            <span className="metric-detail-sub">Handled by ML policies</span>
          </div>
        </div>

        <div 
          className="metric-detail-card clickable" 
          onClick={() => onMetricClick('pending_approvals')}
        >
          <div className="metric-detail-header">
            <div className="metric-detail-icon warning">
              {/* @ts-ignore */}
              <Clock size={20} strokeWidth={2} />
            </div>
            <span className="metric-trend neutral">→ 0%</span>
          </div>
          <div className="metric-detail-value">{metrics.pending_approvals}</div>
          <div className="metric-detail-label">Pending Approvals</div>
          <div className="metric-detail-footer">
            <span className="metric-detail-sub">Awaiting human review</span>
          </div>
        </div>

        <div 
          className="metric-detail-card clickable" 
          onClick={() => onMetricClick('quarantined')}
        >
          <div className="metric-detail-header">
            <div className="metric-detail-icon danger">
              {/* @ts-ignore */}
              <AlertTriangle size={20} strokeWidth={2} />
            </div>
            <span className="metric-trend negative">↓ 3%</span>
          </div>
          <div className="metric-detail-value">{metrics.quarantined}</div>
          <div className="metric-detail-label">Quarantined</div>
          <div className="metric-detail-footer">
            <span className="metric-detail-sub">Quality rules violated</span>
          </div>
        </div>
      </div>

      {/* System Performance Card */}
      <div className="performance-card">
        <div className="performance-header">
          <div>
            <h3>System Performance</h3>
            <p>Real-time pipeline execution metrics</p>
          </div>
          <Badge label={metrics.pipeline_status || 'Running'} tone="success" />
        </div>
        <div className="performance-stats">
          <div className="perf-stat">
            <div className="perf-stat-icon success">
              {/* @ts-ignore */}
              <TrendingUp size={18} />
            </div>
            <div className="perf-stat-content">
              <div className="perf-stat-label">Throughput</div>
              <div className="perf-stat-value">1,247 records/s</div>
            </div>
          </div>
          <div className="perf-stat">
            <div className="perf-stat-icon info">
              {/* @ts-ignore */}
              <Activity size={18} />
            </div>
            <div className="perf-stat-content">
              <div className="perf-stat-label">Active Pipelines</div>
              <div className="perf-stat-value">8 running</div>
            </div>
          </div>
          <div className="perf-stat">
            <div className="perf-stat-icon warning">
              {/* @ts-ignore */}
              <Database size={18} />
            </div>
            <div className="perf-stat-content">
              <div className="perf-stat-label">Data Volume</div>
              <div className="perf-stat-value">156 TB</div>
            </div>
          </div>
          <div className="perf-stat">
            <div className="perf-stat-icon primary">
              {/* @ts-ignore */}
              <Shield size={18} />
            </div>
            <div className="perf-stat-content">
              <div className="perf-stat-label">Quality Score</div>
              <div className="perf-stat-value">98.7%</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import type { PipelineStageMetric } from '../types';

interface PipelineFlowDiagramProps {
  stages: PipelineStageMetric[];
}

export function PipelineFlowDiagram({ stages }: PipelineFlowDiagramProps) {
  const getStageColor = (stageName: string): string => {
    const name = stageName.toLowerCase();
    if (name === 'kafka') return '#6366f1'; // Indigo
    if (name === 'bronze') return '#f59e0b'; // Amber
    if (name === 'silver') return '#8b5cf6'; // Purple
    if (name === 'gold') return '#eab308'; // Yellow
    return '#64748b'; // Slate gray default
  };

  const getStatusColor = (successRate: number): string => {
    if (successRate >= 100) return '#15803d'; // Green
    if (successRate >= 95) return '#ca8a04'; // Amber
    return '#b91c1c'; // Red
  };

  const getThroughputChange = (currentIndex: number): { records: number; percentage: number } | null => {
    if (currentIndex === 0) return null;
    const current = stages[currentIndex];
    const previous = stages[currentIndex - 1];
    const records = current.records_processed - previous.records_processed;
    const percentage = previous.records_processed > 0 
      ? ((records / previous.records_processed) * 100) 
      : 0;
    return { records, percentage };
  };

  const overallSuccessRate = stages.length > 0
    ? stages.reduce((sum, s) => sum + s.success_rate, 0) / stages.length
    : 0;

  const totalIngested = stages[0]?.records_processed || 0;
  const finalOutput = stages[stages.length - 1]?.records_processed || 0;
  const recordGrowthPercent = totalIngested > 0 
    ? ((finalOutput / totalIngested - 1) * 100)
    : 0;

  return (
    <div className="pipeline-monitor" role="region" aria-label="Data Pipeline Flow Monitoring">
      {/* Pipeline Title */}
      <div className="pipeline-header">
        <h2 className="pipeline-title">Data Pipeline Flow</h2>
        <p className="pipeline-subtitle">Bronze → Silver → Gold Medallion Architecture</p>
      </div>

      {/* Professional Node-Based Pipeline Graph */}
      <div className="pipeline-graph-container">
        <div className="pipeline-flow-wrapper">
          {stages.map((stage, index) => {
            const statusColor = getStatusColor(stage.success_rate);
            const stageColor = getStageColor(stage.stage);
            const hasFailures = stage.failed_records > 0;
            const isPerfect = stage.success_rate === 100 && stage.failed_records === 0;
            const throughput = getThroughputChange(index);

            return (
              <div className="pipeline-node-group" key={`${stage.stage}-${index}`}>
                {/* Stage Node Card */}
                <div className="pipeline-node-card" style={{ borderLeftColor: stageColor }}>
                  {/* Stage Header with Status Indicator */}
                  <div className="pipeline-node-header">
                    <div className="pipeline-node-title-wrapper">
                      <div 
                        className={`pipeline-status-dot ${isPerfect ? 'status-perfect' : hasFailures ? 'status-poor' : 'status-good'}`}
                        title={isPerfect ? 'All records processed successfully' : hasFailures ? `${stage.failed_records} failed records` : 'In progress'}
                      />
                      <h3 className="pipeline-node-title">{stage.stage}</h3>
                    </div>
                    {hasFailures && (
                      <div className="pipeline-status-badge">
                        ⚠ {stage.failed_records} Failed
                      </div>
                    )}
                  </div>

                  {/* Primary Metrics */}
                  <div className="pipeline-node-metrics">
                    <div className="pipeline-node-metric-primary">
                      <div className="pipeline-node-value">
                        {stage.records_processed.toLocaleString()}
                      </div>
                      <div className="pipeline-node-label">Records Processed</div>
                    </div>

                    {/* Secondary Metrics Row */}
                    <div className="pipeline-node-metrics-grid">
                      <div className="pipeline-node-metric">
                        <div 
                          className="pipeline-node-metric-value"
                          style={{ color: statusColor }}
                        >
                          {stage.success_rate.toFixed(1)}%
                        </div>
                        <div className="pipeline-node-metric-label">Success Rate</div>
                      </div>
                      
                      <div className="pipeline-node-metric">
                        <div className="pipeline-node-metric-value">
                          {stage.failed_records.toLocaleString()}
                        </div>
                        <div className="pipeline-node-metric-label">Failures</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Flow Connector with Growth Badge */}
                {index < stages.length - 1 && (
                  <div className="pipeline-flow-section">
                    {/* Growth Badge */}
                    {throughput && (
                      <div className={`pipeline-growth-badge ${throughput.records > 0 ? 'positive' : 'neutral'}`}>
                        <div className="pipeline-growth-indicator">
                          {throughput.records > 0 && '▲'}
                          {throughput.records === 0 && '—'}
                          {throughput.records < 0 && '▼'}
                        </div>
                        <div className="pipeline-growth-value">
                          {throughput.records > 0 ? '+' : ''}{throughput.records.toLocaleString()}
                        </div>
                        {throughput.percentage !== 0 && (
                          <div className="pipeline-growth-percent">
                            {throughput.percentage > 0 && `+${throughput.percentage.toFixed(0)}%`}
                            {throughput.percentage < 0 && `${throughput.percentage.toFixed(0)}%`}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Flow Arrow */}
                    <div className="pipeline-flow-arrow-wrapper">
                      <svg className="pipeline-flow-arrow" viewBox="0 0 100 40" preserveAspectRatio="none">
                        <defs>
                          <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
                            <polygon points="0 0, 10 3, 0 6" fill="#94a3b8" />
                          </marker>
                        </defs>
                        <line x1="0" y1="20" x2="100" y2="20" stroke="#cbd5e1" strokeWidth="2" markerEnd="url(#arrowhead)" />
                      </svg>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* KPI Summary Panel */}
      <div className="pipeline-kpi-section">
        <h3 className="pipeline-kpi-title">Pipeline Summary</h3>
        <div className="pipeline-kpi-grid">
          <div className="pipeline-kpi-card">
            <div className="pipeline-kpi-label">Total Ingested</div>
            <div className="pipeline-kpi-value">
              {totalIngested.toLocaleString()}
            </div>
            <div className="pipeline-kpi-unit">records</div>
          </div>

          <div className="pipeline-kpi-card">
            <div className="pipeline-kpi-label">Final Output</div>
            <div className="pipeline-kpi-value">
              {finalOutput.toLocaleString()}
            </div>
            <div className="pipeline-kpi-unit">records</div>
          </div>

          <div className="pipeline-kpi-card">
            <div className="pipeline-kpi-label">Record Growth</div>
            <div className={`pipeline-kpi-value ${recordGrowthPercent > 0 ? 'highlight-positive' : ''}`}>
              {recordGrowthPercent > 0 ? '+' : ''}{recordGrowthPercent.toFixed(0)}%
            </div>
            <div className="pipeline-kpi-unit">transformation</div>
          </div>

          <div className="pipeline-kpi-card">
            <div className="pipeline-kpi-label">Overall Success</div>
            <div className="pipeline-kpi-value" style={{ color: getStatusColor(overallSuccessRate) }}>
              {overallSuccessRate.toFixed(1)}%
            </div>
            <div className="pipeline-kpi-unit">health</div>
          </div>
        </div>
      </div>

      {/* Optional: Pipeline Health Indicator Bar */}
      <div className="pipeline-health-bar">
        <div className="pipeline-health-label">Pipeline Health:</div>
        <div className="pipeline-health-indicator-wrapper">
          <div 
            className="pipeline-health-fill" 
            style={{ 
              width: `${Math.max(0, Math.min(100, overallSuccessRate))}%`,
              backgroundColor: getStatusColor(overallSuccessRate)
            }}
          />
        </div>
        <div className="pipeline-health-value">{overallSuccessRate.toFixed(1)}%</div>
      </div>
    </div>
  );
}

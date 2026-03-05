interface MetricCard {
  label: string;
  value: number;
  trend?: number; // percentage change
}

interface SaasMetricsProps {
  metrics: MetricCard[];
}

export function SaasMetrics({ metrics }: SaasMetricsProps) {
  return (
    <div className="saas-metrics">
      {metrics.map((metric, idx) => (
        <div key={idx} className="metric-card-saas">
          <div className="metric-label">{metric.label}</div>
          <div className="metric-value">{metric.value.toLocaleString()}</div>
          {metric.trend !== undefined && (
            <div className={`metric-trend ${metric.trend >= 0 ? 'positive' : 'negative'}`}>
              {metric.trend >= 0 ? '↑' : '↓'} {Math.abs(metric.trend)}%
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

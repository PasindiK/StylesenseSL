interface MetricCardProps {
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'neutral' | 'positive' | 'warning' | 'critical';
}

export function MetricCard({ label, value, hint, tone = 'neutral' }: MetricCardProps) {
  return (
    <article className={`metric-card metric-${tone}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </article>
  );
}

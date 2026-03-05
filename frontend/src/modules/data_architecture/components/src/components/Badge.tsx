interface BadgeProps {
  label: string;
  tone?: 'success' | 'warning' | 'danger' | 'info';
}

export function Badge({ label, tone }: BadgeProps) {
  const className = tone ? `badge ${tone}` : 'badge';
  return <span className={className}>{label}</span>;
}

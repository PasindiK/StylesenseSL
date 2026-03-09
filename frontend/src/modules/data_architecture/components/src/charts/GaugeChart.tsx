import { Pie, PieChart, ResponsiveContainer, Cell } from 'recharts';

interface GaugeChartProps {
  value: number;
  max?: number;
  label?: string;
}

export function GaugeChart({ value, max = 100, label = 'Success Rate' }: GaugeChartProps) {
  const safeValue = Math.min(max, Math.max(0, value));
  const remaining = Math.max(0, max - safeValue);
  const data = [
    { name: 'value', value: safeValue },
    { name: 'remaining', value: remaining },
  ];

  const tone = safeValue >= 90 ? '#008060' : safeValue >= 70 ? '#d97706' : '#b91c1c';

  return (
    <div className="gauge-wrap">
      <div className="gauge-chart">
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              startAngle={180}
              endAngle={0}
              innerRadius={55}
              outerRadius={80}
              stroke="none"
            >
              <Cell fill={tone} />
              <Cell fill="#e5e7eb" />
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="gauge-value">{safeValue.toFixed(1)}%</div>
      <div className="gauge-label">{label}</div>
    </div>
  );
}

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from 'recharts';
import { MetricCard } from '../cards/MetricCard';
import { PipelineFlowDiagram } from '../charts/PipelineFlowDiagram';
import { Panel } from '../panels/Panel';
import type { DashboardSummaryResponse } from '../types';
import { formatRechartsBytesTooltip, pct } from '../utils/formatters';

interface OverviewPageProps {
  summary: DashboardSummaryResponse;
}

const PIE_COLORS = ['#0f766e', '#0284c7', '#f59e0b', '#94a3b8'];

export function OverviewPage({ summary }: OverviewPageProps) {
  const metrics = summary.overview.metrics;
  const freshness = summary.overview.freshness;
  const ingestion = summary.overview.ingestion_metrics;
  const volumeDistribution = summary.overview.data_volume_distribution;
  const storageTiers = summary.overview.storage_tier_usage;

  const latestPipeline = summary.overview.pipeline_flow;

  const overallSuccess = latestPipeline.length
    ? latestPipeline.reduce((sum, item) => sum + item.success_rate, 0) / latestPipeline.length
    : 0;

  return (
    <div className="grid-12 animate-fade">
      <div className="span-12">
        <div className="metric-grid six">
          <MetricCard label="Total Records Ingested Today" value={metrics.total_records_ingested_today.toLocaleString()} />
          <MetricCard label="Bronze Files Count" value={metrics.bronze_files_count.toLocaleString()} />
          <MetricCard label="Silver Datasets Count" value={metrics.silver_datasets_count.toLocaleString()} />
          <MetricCard label="Gold Tables Count" value={metrics.gold_tables_count.toLocaleString()} />
          <MetricCard
            label="Active Drift Alerts"
            value={metrics.active_drift_alerts.toLocaleString()}
            tone={metrics.active_drift_alerts > 0 ? 'warning' : 'positive'}
          />
          <MetricCard
            label="Data Quality Score"
            value={pct(metrics.data_quality_score)}
            tone={metrics.data_quality_score >= 95 ? 'positive' : 'warning'}
          />
        </div>
      </div>

      <div className="span-12">
        <Panel title="Data Pipeline Flow" subtitle="Bronze -> Silver -> Gold Medallion Architecture">
          <PipelineFlowDiagram stages={latestPipeline} />
        </Panel>
      </div>

      <div className="span-8">
        <Panel title="Data Freshness" subtitle="Freshness in hours since the last layer update">
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={freshness}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="bronze_freshness_hours" stroke="#b45309" name="Bronze" strokeWidth={2} />
                <Line type="monotone" dataKey="silver_freshness_hours" stroke="#0284c7" name="Silver" strokeWidth={2} />
                <Line type="monotone" dataKey="gold_freshness_hours" stroke="#0f766e" name="Gold" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-4">
        <Panel title="Pipeline Runtime" subtitle="Current execution posture">
          <div className="stat-stack">
            <div className="stat-item">
              <span>Overall Success</span>
              <strong>{pct(overallSuccess)}</strong>
            </div>
            <div className="stat-item">
              <span>Bronze Files</span>
              <strong>{metrics.bronze_files_count.toLocaleString()}</strong>
            </div>
            <div className="stat-item">
              <span>Silver Datasets</span>
              <strong>{metrics.silver_datasets_count.toLocaleString()}</strong>
            </div>
            <div className="stat-item">
              <span>Pipeline Status</span>
              <strong>{summary.actions.pipeline_status}</strong>
            </div>
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel title="Storage Tier Usage" subtitle="Hot, Warm, Cold split">
          <div className="chart-box medium">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={storageTiers} dataKey="size_bytes" nameKey="tier" outerRadius={95} innerRadius={45}>
                  {storageTiers.map((item, index) => (
                    <Cell key={`tier-${item.tier}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => formatRechartsBytesTooltip(value)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-12">
        <Panel title="Data Volume Distribution" subtitle="Volume split by medallion layer">
          <div className="chart-box medium">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={volumeDistribution}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis dataKey="layer" />
                <YAxis />
                <Tooltip formatter={(value) => formatRechartsBytesTooltip(value)} />
                <Bar dataKey="size_bytes" fill="#0f766e" name="Layer Volume" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
    </div>
  );
}

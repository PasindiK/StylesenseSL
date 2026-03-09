import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { MetricCard } from '../cards/MetricCard';
import { Panel } from '../panels/Panel';
import type { DashboardSummaryResponse } from '../types';
import { pct } from '../utils/formatters';

interface ExplainabilityPageProps {
  summary: DashboardSummaryResponse;
}

export function ExplainabilityPage({ summary }: ExplainabilityPageProps) {
  const explainability = summary.explainability;

  const featureRows = explainability.feature_importance.flatMap((entry) =>
    entry.features.map((feature) => ({
      action: entry.action,
      feature: feature.name,
      weight: feature.weight,
    })),
  );

  return (
    <div className="grid-12 animate-fade">
      <div className="span-12">
        <div className="metric-grid four">
          <MetricCard
            label="Training Dataset Size"
            value={explainability.ml_dataset_metrics.training_dataset_size.toLocaleString()}
          />
          <MetricCard label="Feature Count" value={explainability.ml_dataset_metrics.feature_count.toLocaleString()} />
          <MetricCard
            label="Embedding Vectors Generated"
            value={explainability.ml_dataset_metrics.embedding_vectors_generated.toLocaleString()}
          />
          <MetricCard
            label="Model Accuracy"
            value={pct(explainability.ml_dataset_metrics.model_accuracy)}
            tone={explainability.ml_dataset_metrics.model_accuracy >= 80 ? 'positive' : 'warning'}
          />
        </div>
      </div>

      <div className="span-6">
        <Panel title="Feature Importance" subtitle="Primary drivers behind model decisions">
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={featureRows.slice(0, 20)} layout="vertical" margin={{ left: 120 }}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis dataKey="feature" type="category" width={130} />
                <Tooltip />
                <Bar dataKey="weight" fill="#0f766e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel title="Embedding Clusters" subtitle="Product similarity cluster scatter">
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis dataKey="x" type="number" name="Embedding X" />
                <YAxis dataKey="y" type="number" name="Embedding Y" />
                <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                <Scatter data={explainability.embedding_clusters} fill="#0284c7" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-12">
        <Panel title="Recommendation Explanation" subtitle="Why products were recommended">
          <div className="recommendation-grid">
            {explainability.recommendation_explanations.map((item) => (
              <article key={item.title} className="recommendation-card">
                <h4>{item.title}</h4>
                <p>{item.reason}</p>
                <div className="recommendation-confidence">Confidence: {pct(item.confidence)}</div>
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

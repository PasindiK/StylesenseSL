import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { DashboardData } from '../types';

interface ExplainabilityPageProps {
  featureImportance: NonNullable<DashboardData['feature_importance']>;
}

export function ExplainabilityPage({ featureImportance }: ExplainabilityPageProps) {
  if (!featureImportance || featureImportance.length === 0) {
    return (
      <div className="page-section">
        <div className="empty-state">
          <div className="empty-icon">🧠</div>
          <h3>No Explainability Data</h3>
          <p>Feature importance data will appear here after drift events are processed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Decision Explainability</h2>
        <p className="section-description">
          ML feature importance for each action type - understand what drives automated decisions
        </p>
      </div>

      <div className="info-banner info">
        <span className="banner-icon">💡</span>
        <div>
          <strong>How to Read:</strong> Higher weights indicate features that have more influence on the ML policy's decision. 
          This transparency helps you understand and trust automated drift resolution.
        </div>
      </div>

      <div className="explainability-grid">
        {featureImportance.map((fi) => (
          <div key={fi.action} className="explainability-card">
            <div className="card-header">
              <h3>{fi.action}</h3>
              <div className="feature-count">{fi.features.length} features</div>
            </div>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart 
                  data={fi.features} 
                  layout="vertical" 
                  margin={{ left: 120, right: 20, top: 10, bottom: 10 }}
                >
                  <XAxis 
                    type="number" 
                    domain={[0, 'auto']} 
                    stroke="var(--muted)" 
                    fontSize={11}
                  />
                  <YAxis 
                    type="category" 
                    dataKey="name" 
                    stroke="var(--muted)" 
                    width={110} 
                    fontSize={11}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      background: 'var(--card)', 
                      border: '1px solid var(--grid)',
                      borderRadius: '6px'
                    }}
                  />
                  <Bar 
                    dataKey="weight" 
                    fill="var(--accent-2)" 
                    radius={[0, 4, 4, 0]} 
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="feature-list">
              {fi.features.slice(0, 3).map((feature, idx) => (
                <div key={idx} className="feature-item">
                  <span className="feature-name">{feature.name}</span>
                  <span className="feature-weight">{(feature.weight * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

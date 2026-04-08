import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { DashboardData } from '../types';

interface ActionDistributionPageProps {
  actionDistribution: NonNullable<DashboardData['action_distribution']>;
}

export function ActionDistributionPage({ actionDistribution }: ActionDistributionPageProps) {
  if (!actionDistribution || actionDistribution.length === 0) {
    return (
      <div className="page-section">
        <div className="empty-state">
          <div className="empty-icon">📈</div>
          <h3>No Distribution Data</h3>
          <p>Action distribution data will appear here after drift events are processed.</p>
        </div>
      </div>
    );
  }

  const totalAutomated = actionDistribution.reduce((sum, item) => sum + item.automated, 0);
  const totalHumanReviewed = actionDistribution.reduce((sum, item) => sum + item.human_reviewed, 0);
  const totalActions = totalAutomated + totalHumanReviewed;
  const automationRate = totalActions > 0 ? ((totalAutomated / totalActions) * 100).toFixed(1) : '0';

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Action Distribution</h2>
        <p className="section-description">
          Breakdown of automated vs human-reviewed decisions
        </p>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Automation Rate</div>
          <div className="stat-value success">{automationRate}%</div>
          <div className="stat-description">{totalAutomated} of {totalActions} actions automated</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Actions</div>
          <div className="stat-value">{totalActions}</div>
          <div className="stat-description">Across all drift events</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Human Reviewed</div>
          <div className="stat-value warning">{totalHumanReviewed}</div>
          <div className="stat-description">Required manual intervention</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Actions by Type</h3>
        </div>
        <div className="chart-container-large">
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={actionDistribution} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
              <XAxis 
                dataKey="action" 
                stroke="var(--muted)" 
                fontSize={12}
                angle={-45}
                textAnchor="end"
                height={80}
              />
              <YAxis stroke="var(--muted)" fontSize={12} />
              <Tooltip 
                contentStyle={{ 
                  background: 'var(--card)', 
                  border: '1px solid var(--grid)',
                  borderRadius: '6px'
                }}
              />
              <Legend />
              <Bar 
                dataKey="automated" 
                stackId="a" 
                fill="var(--accent)" 
                name="Automated"
                radius={[0, 0, 0, 0]}
              />
              <Bar 
                dataKey="human_reviewed" 
                stackId="a" 
                fill="var(--warning)" 
                name="Human Reviewed"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="distribution-table">
        <table className="data-table">
          <thead>
            <tr>
              <th>Action</th>
              <th>Total</th>
              <th>Automated</th>
              <th>Human Reviewed</th>
              <th>Automation %</th>
            </tr>
          </thead>
          <tbody>
            {actionDistribution.map((item) => {
              const total = item.automated + item.human_reviewed;
              const autoPercent = total > 0 ? ((item.automated / total) * 100).toFixed(0) : '0';
              return (
                <tr key={item.action}>
                  <td className="table-cell-main">{item.action}</td>
                  <td>{total}</td>
                  <td className="success">{item.automated}</td>
                  <td className="warning">{item.human_reviewed}</td>
                  <td>
                    <div className="progress-cell">
                      <div className="progress-bar">
                        <div 
                          className="progress-fill" 
                          style={{ width: `${autoPercent}%` }}
                        />
                      </div>
                      <span className="progress-label">{autoPercent}%</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

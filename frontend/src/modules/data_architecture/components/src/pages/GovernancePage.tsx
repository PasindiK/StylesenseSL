import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { MetricCard } from '../cards/MetricCard';
import { Panel } from '../panels/Panel';
import type { DashboardSummaryResponse } from '../types';

interface GovernancePageProps {
  summary: DashboardSummaryResponse;
}

const COLORS = ['#0f766e', '#0284c7', '#f59e0b', '#b91c1c', '#64748b'];

export function GovernancePage({ summary }: GovernancePageProps) {
  const governance = summary.governance;

  return (
    <div className="grid-12 animate-fade">
      <div className="span-12">
        <div className="metric-grid four">
          <MetricCard label="Audit Events Today" value={governance.metric_cards.audit_events_today} />
          <MetricCard label="Access Requests" value={governance.metric_cards.access_requests} />
          <MetricCard label="Policy Violations" value={governance.metric_cards.policy_violations} tone="warning" />
          <MetricCard
            label="Unauthorized Access Attempts"
            value={governance.metric_cards.unauthorized_access_attempts}
            tone={governance.metric_cards.unauthorized_access_attempts > 0 ? 'critical' : 'positive'}
          />
        </div>
      </div>

      <div className="span-8">
        <Panel title="Audit Activity Per Hour" subtitle="Hourly governance events">
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={governance.audit_activity_per_hour}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#0f766e" strokeWidth={2} name="Events" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-4">
        <Panel title="Compliance Indicators" subtitle="Retention, access, and quality controls">
          <div className="compliance-list">
            {governance.compliance_indicators.map((item) => (
              <div key={item.name} className="compliance-item">
                <span>{item.name}</span>
                <strong className={`status-${item.status.toLowerCase()}`}>{item.status}</strong>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel title="Access by Stakeholder" subtitle="Fabric Components, Mesh Nodes, Agentic AI, Analytics Users">
          <div className="chart-box medium">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={governance.stakeholder_access} dataKey="count" nameKey="stakeholder" outerRadius={95}>
                  {governance.stakeholder_access.map((item, idx) => (
                    <Cell key={`stakeholder-${item.stakeholder}`} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel title="Regional Access" subtitle="Access events by Sri Lankan province">
          <div className="chart-box medium">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={governance.regional_access}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
                <XAxis dataKey="province" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#0284c7" name="Access Events" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-12">
        <Panel title="Audit Log Stream" subtitle="Recent governance events">
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Event Type</th>
                  <th>Status</th>
                  <th>User</th>
                </tr>
              </thead>
              <tbody>
                {governance.audit_events.slice(0, 30).map((entry, index) => (
                  <tr key={`${String(entry.timestamp)}-${index}`}>
                    <td>{String(entry.timestamp || 'N/A')}</td>
                    <td>{String(entry.event_type || 'N/A')}</td>
                    <td>{String(entry.status || 'N/A')}</td>
                    <td>{String(entry.user || 'system')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}

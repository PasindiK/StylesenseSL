import { Badge } from './Badge';
import type { DashboardData, LiveMetrics } from '../types';

interface GovernancePageProps {
  governance?: DashboardData['governance'];
  metrics: LiveMetrics;
}

function policyTone(status: string): 'success' | 'warning' | 'danger' | 'info' {
  const normalized = (status || '').toLowerCase();
  if (normalized === 'active' || normalized === 'compliant') {
    return 'success';
  }
  if (normalized === 'warning') {
    return 'danger';
  }
  if (normalized === 'review') {
    return 'warning';
  }
  return 'info';
}

function statusLabel(status: string): string {
  const normalized = (status || '').toLowerCase();
  if (normalized === 'active') {
    return 'Active';
  }
  if (normalized === 'compliant') {
    return 'Compliant';
  }
  if (normalized === 'review') {
    return 'Under Review';
  }
  if (normalized === 'warning') {
    return 'Attention Needed';
  }
  return status || 'Unknown';
}

export function GovernancePage({ governance, metrics }: GovernancePageProps) {
  const policies = governance?.policies || [];
  const qualityRules = governance?.quality_rules || [];
  const compliance = governance?.compliance || [];

  const totalPolicyCoverage = policies.reduce((sum, item) => sum + (item.affected_datasets || 0), 0);
  const totalRulePass = qualityRules.reduce((sum, rule) => sum + (rule.passed || 0), 0);
  const totalRuleChecks = qualityRules.reduce((sum, rule) => sum + (rule.datasets || 0), 0);
  const rulePassRate = totalRuleChecks > 0 ? `${((totalRulePass / totalRuleChecks) * 100).toFixed(1)}%` : '0.0%';
  const compliantStandards = compliance.filter(item => (item.status || '').toLowerCase() === 'compliant').length;

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Data Governance</h2>
        <p className="section-description">
          Live governance posture built from backend policy config and latest DQ report
        </p>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Governance Rules</div>
          <div className="stat-value">{metrics.governance_rules_count ?? 0}</div>
          <div className="stat-description">Counted from policy configuration</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Policy Coverage</div>
          <div className="stat-value">{totalPolicyCoverage}</div>
          <div className="stat-description">Total dataset-policy assignments</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Rule Pass Rate</div>
          <div className="stat-value success">{rulePassRate}</div>
          <div className="stat-description">From latest quality checks</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Compliant Standards</div>
          <div className="stat-value">{compliantStandards}/{compliance.length}</div>
          <div className="stat-description">Current compliance posture</div>
        </div>
      </div>

      {/* Governance Policies */}
      <div className="card">
        <div className="card-header">
          <h3>Governance Policies</h3>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span className="policy-count">{policies.length} Policies</span>
            {governance?.source && (
              <Badge label={`Source: ${governance.source}`} tone="info" />
            )}
          </div>
        </div>
        {policies.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📭</div>
            <p>No governance policy payload is available from backend yet.</p>
          </div>
        ) : (
          <div className="governance-grid">
            {policies.map((policy) => (
              <div key={policy.id} className="policy-card">
                <div className="policy-header">
                  <div className="policy-title">
                    <h4>{policy.name}</h4>
                    <span className="policy-id">{policy.id}</span>
                  </div>
                  <Badge
                    label={statusLabel(policy.status)}
                    tone={policyTone(policy.status)}
                  />
                </div>
                <p className="policy-description">{policy.description}</p>
                <div className="policy-footer">
                  <span className="dataset-count">{policy.affected_datasets} Datasets</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quality Rules */}
      <div className="card">
        <div className="card-header">
          <h3>Quality Rules</h3>
          <span className="rule-count">{qualityRules.length} Rules</span>
        </div>
        {qualityRules.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📉</div>
            <p>No quality rule summary is available.</p>
          </div>
        ) : (
          <div className="quality-rules-table">
            <table>
              <thead>
                <tr>
                  <th>Rule Name</th>
                  <th>Description</th>
                  <th>Datasets</th>
                  <th>Pass Rate</th>
                  <th>Coverage</th>
                </tr>
              </thead>
              <tbody>
                {qualityRules.map((rule) => (
                  <tr key={rule.id}>
                    <td>
                      <div className="rule-name">
                        <strong>{rule.name}</strong>
                        <span className="rule-id">{rule.id}</span>
                      </div>
                    </td>
                    <td className="rule-description">{rule.description}</td>
                    <td className="center">{rule.datasets}</td>
                    <td className="center">
                      <div className="pass-rate">
                        <span className="passed">{rule.passed}</span>
                        <span className="separator">/</span>
                        <span className="total">{rule.datasets}</span>
                      </div>
                    </td>
                    <td className="center">
                      <div className="coverage-badge">{rule.coverage}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Compliance Standards */}
      <div className="card">
        <div className="card-header">
          <h3>Compliance Standards</h3>
          <span className="compliance-count">{compliance.length} Standards</span>
        </div>
        {compliance.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🛡️</div>
            <p>No compliance summary is available.</p>
          </div>
        ) : (
          <div className="compliance-grid">
            {compliance.map((item) => (
              <div key={item.standard} className="compliance-card">
                <div className="compliance-header">
                  <h4>{item.standard}</h4>
                  <Badge
                    label={statusLabel(item.status)}
                    tone={policyTone(item.status)}
                  />
                </div>
                <div className="compliance-metrics">
                  <div className="metric">
                    <span className="label">Current Value</span>
                    <span className="value">{item.score}</span>
                  </div>
                  <div className="metric">
                    <span className="label">Checks</span>
                    <span className="value">{item.audits}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

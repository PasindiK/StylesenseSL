import { Badge } from './Badge';

export function GovernancePage() {
  const policies = [
    {
      id: 'POL001',
      name: 'Data Classification',
      status: 'active' as const,
      description: 'Enforce classification levels for all datasets',
      affectedDatasets: 142,
    },
    {
      id: 'POL002',
      name: 'PII Protection',
      status: 'active' as const,
      description: 'Identify and protect personally identifiable information',
      affectedDatasets: 89,
    },
    {
      id: 'POL003',
      name: 'Retention Policy',
      status: 'active' as const,
      description: 'Define data retention periods by dataset type',
      affectedDatasets: 156,
    },
    {
      id: 'POL004',
      name: 'Access Control',
      status: 'review' as const,
      description: 'Role-based access control for sensitive assets',
      affectedDatasets: 78,
    },
  ];

  const qualityRules = [
    {
      id: 'QR001',
      name: 'Schema Validation',
      description: 'Validates schema consistency across pipeline stages',
      datasets: 142,
      passed: 134,
      failed: 8,
      coverage: '95%',
    },
    {
      id: 'QR002',
      name: 'Null Value Check',
      description: 'Enforces minimum non-null value thresholds',
      datasets: 89,
      passed: 87,
      failed: 2,
      coverage: '98%',
    },
    {
      id: 'QR003',
      name: 'Duplicate Detection',
      description: 'Identifies and flags duplicate records',
      datasets: 156,
      passed: 150,
      failed: 6,
      coverage: '96%',
    },
  ];

  const compliance = [
    {
      standard: 'GDPR',
      status: 'compliant' as const,
      score: '98%',
      audits: 12,
    },
    {
      standard: 'CCPA',
      status: 'compliant' as const,
      score: '97%',
      audits: 10,
    },
    {
      standard: 'HIPAA',
      status: 'compliant' as const,
      score: '99%',
      audits: 8,
    },
    {
      standard: 'SOC2',
      status: 'review' as const,
      score: '94%',
      audits: 5,
    },
  ];

  return (
    <div className="page-section">
      <div className="section-header">
        <h2>Data Governance</h2>
        <p className="section-description">
          Manage policies, quality rules, and compliance standards across your data ecosystem
        </p>
      </div>

      {/* Governance Policies */}
      <div className="card">
        <div className="card-header">
          <h3>Governance Policies</h3>
          <span className="policy-count">{policies.length} Active</span>
        </div>
        <div className="governance-grid">
          {policies.map((policy) => (
            <div key={policy.id} className="policy-card">
              <div className="policy-header">
                <div className="policy-title">
                  <h4>{policy.name}</h4>
                  <span className="policy-id">{policy.id}</span>
                </div>
                <Badge
                  label={policy.status === 'active' ? 'Active' : 'Under Review'}
                  tone={policy.status === 'active' ? 'success' : 'warning'}
                />
              </div>
              <p className="policy-description">{policy.description}</p>
              <div className="policy-footer">
                <span className="dataset-count">{policy.affectedDatasets} Datasets</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Quality Rules */}
      <div className="card">
        <div className="card-header">
          <h3>Quality Rules</h3>
          <span className="rule-count">{qualityRules.length} Rules</span>
        </div>
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
      </div>

      {/* Compliance Standards */}
      <div className="card">
        <div className="card-header">
          <h3>Compliance Standards</h3>
          <span className="compliance-count">4 Standards</span>
        </div>
        <div className="compliance-grid">
          {compliance.map((item) => (
            <div key={item.standard} className="compliance-card">
              <div className="compliance-header">
                <h4>{item.standard}</h4>
                <Badge
                  label={item.status === 'compliant' ? 'Compliant' : 'Under Review'}
                  tone={item.status === 'compliant' ? 'success' : 'warning'}
                />
              </div>
              <div className="compliance-metrics">
                <div className="metric">
                  <span className="label">Compliance Score</span>
                  <span className="value">{item.score}</span>
                </div>
                <div className="metric">
                  <span className="label">Audits Completed</span>
                  <span className="value">{item.audits}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

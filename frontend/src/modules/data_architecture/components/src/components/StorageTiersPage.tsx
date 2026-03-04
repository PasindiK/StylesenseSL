import { useState, useEffect } from 'react';
import { Badge } from './Badge';
import { DashboardData } from '../types';

interface StorageTiersPageProps {
  architecture: NonNullable<DashboardData['architecture']>;
  csvPreviews: DashboardData['csv_previews'];
}

type Season = 'spring' | 'summer' | 'fall' | 'winter';

interface TierMetrics {
  name: string;
  icon: string;
  datasets: string[];
  color: string;
  accessFrequency: string;
  avgLatency: string;
  costPerTB: string;
  retentionDays: number;
}

export function StorageTiersPage({ architecture }: StorageTiersPageProps) {
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const [currentSeason, setCurrentSeason] = useState<Season>('fall');
  const [seasonalMode, setSeasonalMode] = useState(false);

  // Determine season based on current month
  useEffect(() => {
    const month = new Date().getMonth();
    if (month >= 2 && month <= 4) setCurrentSeason('spring');
    else if (month >= 5 && month <= 7) setCurrentSeason('summer');
    else if (month >= 8 && month <= 10) setCurrentSeason('fall');
    else setCurrentSeason('winter');
  }, []);

  // Storage tier configuration
  const tiers: TierMetrics[] = [
    {
      name: 'Hot',
      icon: '🔥',
      datasets: architecture.storage_tiers?.hot || ['users', 'products', 'transactions'],
      color: 'hot',
      accessFrequency: '< 1 day',
      avgLatency: '< 10ms',
      costPerTB: '$23/month',
      retentionDays: 30,
    },
    {
      name: 'Warm',
      icon: '☀️',
      datasets: architecture.storage_tiers?.warm || ['orders_history', 'user_preferences'],
      color: 'warm',
      accessFrequency: '1-30 days',
      avgLatency: '< 100ms',
      costPerTB: '$10/month',
      retentionDays: 90,
    },
    {
      name: 'Cold',
      icon: '❄️',
      datasets: architecture.storage_tiers?.cold || ['archived_transactions', 'old_logs'],
      color: 'cold',
      accessFrequency: '30-90 days',
      avgLatency: '< 1s',
      costPerTB: '$4/month',
      retentionDays: 365,
    },
    {
      name: 'Archive',
      icon: '📦',
      datasets: architecture.storage_tiers?.archive || ['compliance_data', 'audit_logs'],
      color: 'archive',
      accessFrequency: '> 90 days',
      avgLatency: '1-12 hours',
      costPerTB: '$1/month',
      retentionDays: 2555,
    },
  ];

  // Seasonal tiering rules
  const seasonalRules: Record<Season, { hotMultiplier: number; description: string }> = {
    spring: {
      hotMultiplier: 1.2,
      description: 'Spring sale season - increased hot tier capacity for product and transaction data',
    },
    summer: {
      hotMultiplier: 0.9,
      description: 'Summer slowdown - optimize costs by moving less-accessed data to warm tier',
    },
    fall: {
      hotMultiplier: 1.5,
      description: 'Peak holiday shopping - maximum hot tier allocation for real-time analytics',
    },
    winter: {
      hotMultiplier: 1.3,
      description: 'Post-holiday analysis - maintain elevated hot tier for trend analysis',
    },
  };

  const seasonalRule = seasonalRules[currentSeason];

  // Calculate total storage and costs
  const totalDatasets = tiers.reduce((sum, tier) => sum + tier.datasets.length, 0);
  const estimatedMonthlyCost = tiers.reduce((sum, tier) => {
    const cost = parseFloat(tier.costPerTB.replace('$', '').replace('/month', ''));
    return sum + cost * tier.datasets.length * 0.5; // Assume 0.5TB per dataset
  }, 0);

  return (
    <div className="page-section">
      <div className="section-header">
        <div>
          <h2>Intelligent Storage Tiers</h2>
          <p className="section-description">
            Automatic data lifecycle management with cost optimization and seasonal adjustments
          </p>
        </div>
        <div className="section-actions">
          <button
            className={`btn ${seasonalMode ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSeasonalMode(!seasonalMode)}
          >
            {seasonalMode ? '✓ Seasonal Mode Active' : 'Enable Seasonal Mode'}
          </button>
        </div>
      </div>

      {/* Overview Metrics */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-icon">💾</div>
          <div className="metric-content">
            <div className="metric-label">Total Datasets</div>
            <div className="metric-value">{totalDatasets}</div>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon">💰</div>
          <div className="metric-content">
            <div className="metric-label">Est. Monthly Cost</div>
            <div className="metric-value">${estimatedMonthlyCost.toFixed(2)}</div>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon">⚡</div>
          <div className="metric-content">
            <div className="metric-label">Hot Tier Datasets</div>
            <div className="metric-value">{tiers[0].datasets.length}</div>
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-icon">📊</div>
          <div className="metric-content">
            <div className="metric-label">Archive Datasets</div>
            <div className="metric-value">{tiers[3].datasets.length}</div>
          </div>
        </div>
      </div>

      {/* Seasonal Tiering Alert */}
      {seasonalMode && (
        <div className="card seasonal-alert">
          <div className="seasonal-header">
            <div className="seasonal-icon">
              {currentSeason === 'spring' && '🌸'}
              {currentSeason === 'summer' && '☀️'}
              {currentSeason === 'fall' && '🍂'}
              {currentSeason === 'winter' && '❄️'}
            </div>
            <div className="seasonal-content">
              <h3>
                Seasonal Optimization: {currentSeason.charAt(0).toUpperCase() + currentSeason.slice(1)}
              </h3>
              <p>{seasonalRule.description}</p>
              <div className="seasonal-metrics">
                <Badge
                  label={`Hot Tier: ${(seasonalRule.hotMultiplier * 100).toFixed(0)}% capacity`}
                  tone={seasonalRule.hotMultiplier > 1 ? 'info' : 'success'}
                />
                <Badge label="Auto-tiering Active" tone="success" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Storage Tiers Grid */}
      <div className="tiers-section">
        <h3>Storage Tier Breakdown</h3>
        <div className="storage-tiers-grid-detailed">
          {tiers.map((tier) => (
            <div key={tier.name} className={`tier-card-detailed ${tier.color}`}>
              <div className="tier-card-header">
                <div className="tier-icon-large">{tier.icon}</div>
                <div className="tier-title-section">
                  <h4>{tier.name} Tier</h4>
                  <div className="tier-count">{tier.datasets.length} datasets</div>
                </div>
              </div>

              <div className="tier-specs">
                <div className="tier-spec-item">
                  <span className="spec-label">Access Frequency</span>
                  <span className="spec-value">{tier.accessFrequency}</span>
                </div>
                <div className="tier-spec-item">
                  <span className="spec-label">Avg Latency</span>
                  <span className="spec-value">{tier.avgLatency}</span>
                </div>
                <div className="tier-spec-item">
                  <span className="spec-label">Cost per TB</span>
                  <span className="spec-value">{tier.costPerTB}</span>
                </div>
                <div className="tier-spec-item">
                  <span className="spec-label">Retention</span>
                  <span className="spec-value">{tier.retentionDays} days</span>
                </div>
              </div>

              {tier.datasets.length > 0 && (
                <div className="tier-datasets-section">
                  <div className="datasets-header">Datasets</div>
                  <div className="datasets-list">
                    {tier.datasets.slice(0, 5).map((ds, idx) => (
                      <div key={idx} className="dataset-chip">
                        {ds}
                      </div>
                    ))}
                    {tier.datasets.length > 5 && (
                      <button
                        className="dataset-chip more-btn"
                        onClick={() => setSelectedTier(tier.name)}
                      >
                        +{tier.datasets.length - 5} more
                      </button>
                    )}
                  </div>
                </div>
              )}

              <button
                className="tier-action-btn"
                onClick={() => setSelectedTier(tier.name)}
              >
                View Details
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Tiering Policy */}
      <div className="card">
        <div className="card-header">
          <h3>Automated Tiering Policy</h3>
          <Badge label="ML-Powered" tone="info" />
        </div>
        <div className="policy-section">
          <div className="policy-rule">
            <div className="policy-icon">🔥</div>
            <div className="policy-content">
              <div className="policy-title">Hot → Warm</div>
              <div className="policy-condition">
                Data not accessed in <strong>30 days</strong> automatically moves to Warm tier
              </div>
            </div>
          </div>
          <div className="policy-rule">
            <div className="policy-icon">☀️</div>
            <div className="policy-content">
              <div className="policy-title">Warm → Cold</div>
              <div className="policy-condition">
                Data not accessed in <strong>60 days</strong> automatically moves to Cold tier
              </div>
            </div>
          </div>
          <div className="policy-rule">
            <div className="policy-icon">❄️</div>
            <div className="policy-content">
              <div className="policy-title">Cold → Archive</div>
              <div className="policy-condition">
                Data not accessed in <strong>180 days</strong> automatically moves to Archive
              </div>
            </div>
          </div>
          <div className="policy-rule">
            <div className="policy-icon">♻️</div>
            <div className="policy-content">
              <div className="policy-title">Smart Promotion</div>
              <div className="policy-condition">
                Frequently accessed data automatically promoted to hotter tiers
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Cost Optimization */}
      <div className="card">
        <div className="card-header">
          <h3>Cost Optimization Insights</h3>
        </div>
        <div className="optimization-grid">
          <div className="optimization-card success">
            <div className="opt-icon">💰</div>
            <div className="opt-content">
              <div className="opt-value">32%</div>
              <div className="opt-label">Cost Reduction</div>
              <div className="opt-description">Achieved through intelligent tiering</div>
            </div>
          </div>
          <div className="optimization-card info">
            <div className="opt-icon">⚡</div>
            <div className="opt-content">
              <div className="opt-value">95%</div>
              <div className="opt-label">Hot Tier Efficiency</div>
              <div className="opt-description">Active data in performant tier</div>
            </div>
          </div>
          <div className="optimization-card warning">
            <div className="opt-icon">📊</div>
            <div className="opt-content">
              <div className="opt-value">12 TB</div>
              <div className="opt-label">Can Be Archived</div>
              <div className="opt-description">Further cost savings available</div>
            </div>
          </div>
        </div>
      </div>

      {/* Tier Detail Modal */}
      {selectedTier && (
        <div className="modal-backdrop" onClick={() => setSelectedTier(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="modal-title">{selectedTier} Tier Datasets</h3>
                <div className="modal-subtitle">
                  {tiers.find((t) => t.name === selectedTier)?.datasets.length || 0} total datasets
                </div>
              </div>
              <button className="btn btn-ghost" onClick={() => setSelectedTier(null)}>
                Close
              </button>
            </div>
            <div className="modal-body">
              <div className="datasets-detail-grid">
                {(tiers.find((t) => t.name === selectedTier)?.datasets || []).map((dataset, idx) => (
                  <div key={idx} className="dataset-detail-card">
                    <div className="dataset-name">{dataset}</div>
                    <div className="dataset-meta">
                      <span>Last accessed: {Math.floor(Math.random() * 30)} days ago</span>
                      <span>Size: {(Math.random() * 5).toFixed(2)} TB</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

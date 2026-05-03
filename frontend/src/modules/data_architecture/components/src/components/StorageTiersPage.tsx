import { useEffect, useState } from 'react';
import { Badge } from './Badge';
import type {
  DashboardData,
  StorageTierAssignments,
  CurrentSeason,
  StoragePolicyRules,
} from '../types';
import {
  Flame,
  Sun,
  Snowflake,
  Package,
  HardDrive,
  DollarSign,
  Zap,
  AlertCircle,
  RefreshCw,
  Calendar,
  Lock,
  type LucideIcon,
} from 'lucide-react';

interface StorageTiersPageProps {
  architecture: NonNullable<DashboardData['architecture']>;
  csvPreviews: DashboardData['csv_previews'];
}

type Season = 'festive' | 'monsoon' | 'dry' | 'historical';

interface TierMetrics {
  name: string;
  icon: LucideIcon;
  datasets: string[];
  color: string;
  accessFrequency: string;
  avgLatency: string;
  costPerTB: string;
  retentionDays: number;
  description: string;
}

const defaultPolicyRules: StoragePolicyRules = {
  layer_rules: {
    bronze: { hot: '< 3 days', cool: '3-14 days', archive: '> 14 days' },
    silver: { hot: '< 7 days', cool: '7-60 days', archive: '> 60 days' },
    gold: { hot: '< 30 days', cool: '30-90 days', archive: '> 90 days' },
  },
  access_overrides: {
    promote_to_hot: 'If accessed within 1 day (when access telemetry exists)',
    promote_archive_to_cool: 'If accessed within 7 days (when access telemetry exists)',
  },
  seasonal_override: 'Datasets matching current seasonal product keywords are promoted to HOT',
};

function tierBadgeTone(tier: string): 'success' | 'warning' | 'danger' | 'info' {
  const normalized = (tier || '').toUpperCase();
  if (normalized === 'HOT') {
    return 'danger';
  }
  if (normalized === 'COOL') {
    return 'info';
  }
  if (normalized === 'ARCHIVE') {
    return 'warning';
  }
  return 'success';
}

function normalizeTierLabel(tier: string): string {
  const normalized = (tier || '').toUpperCase();
  if (!normalized) {
    return 'UNKNOWN';
  }
  return normalized;
}

function isTierMismatch(current: string, target: string): boolean {
  const norm_current = (current || '').toUpperCase();
  const norm_target = (target || '').toUpperCase();
  return norm_current !== norm_target;
}

function monthlyCostPerTbByTier(tier: string): number {
  const normalized = (tier || '').toUpperCase();
  if (normalized === 'HOT') {
    return 23;
  }
  if (normalized === 'COOL' || normalized === 'WARM') {
    return 10;
  }
  if (normalized === 'COLD') {
    return 4;
  }
  if (normalized === 'ARCHIVE') {
    return 1;
  }
  return 10;
}

export function StorageTiersPage({ architecture }: StorageTiersPageProps) {
  const [currentSeasonInfo, setCurrentSeasonInfo] = useState<CurrentSeason | null>(null);
  const [tierAssignments, setTierAssignments] = useState<StorageTierAssignments | null>(null);
  const [seasonalMode, setSeasonalMode] = useState(true);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [selectedTier, setSelectedTier] = useState<string | null>(null);

  const API_BASE_URL =
    (typeof import.meta !== 'undefined' && (import.meta.env.VITE_DATA_ARCH_API_URL as string)) ||
    'http://localhost:8003/api';

  useEffect(() => {
    const fetchTierData = async () => {
      try {
        setLoading(true);

        const seasonResp = await fetch(`${API_BASE_URL}/storage-tiers/current-season`);
        if (seasonResp.ok) {
          const seasonData = await seasonResp.json();
          setCurrentSeasonInfo(seasonData);
        }

        const tiersResp = await fetch(`${API_BASE_URL}/storage-tiers/current`);
        if (tiersResp.ok) {
          const tiersData = await tiersResp.json();
          setTierAssignments(tiersData);
        }
      } catch (error) {
        console.error('Error fetching tier data:', error);
        setTierAssignments({
          hot: architecture.storage_tiers?.hot || ['transactions', 'products', 'users', 'inventory'],
          warm: architecture.storage_tiers?.warm || ['orders_history', 'user_preferences'],
          cold: architecture.storage_tiers?.cold || ['archived_transactions', 'old_logs'],
          archive: architecture.storage_tiers?.archive || ['compliance_data', 'audit_logs'],
          dataset_details: [],
          policy_rules: defaultPolicyRules,
          last_updated: new Date().toISOString(),
          season: 'festive',
          auto_tiering_enabled: true,
        });
      } finally {
        setLoading(false);
      }
    };

    fetchTierData();
  }, [architecture.storage_tiers]);

  const handleSyncTiers = async () => {
    try {
      setSyncing(true);
      const resp = await fetch(`${API_BASE_URL}/storage-tiers/sync`, {
        method: 'POST',
      });

      if (resp.ok) {
        const data = await resp.json();
        setTierAssignments(data.assignments);
        alert('✓ Tier assignments synced from Azure successfully');
      } else {
        alert('Failed to sync tier assignments');
      }
    } catch (error) {
      console.error('Error syncing tiers:', error);
      alert('Error syncing tier assignments');
    } finally {
      setSyncing(false);
    }
  };

  const tiers: TierMetrics[] = [
    {
      name: 'Hot',
      icon: Flame,
      datasets: tierAssignments?.hot || [],
      color: 'hot',
      accessFrequency: '< 1 day',
      avgLatency: '< 10ms',
      costPerTB: '$23/month',
      retentionDays: 30,
      description: 'High-performance active data',
    },
    {
      name: 'Warm',
      icon: Sun,
      datasets: tierAssignments?.warm || [],
      color: 'warm',
      accessFrequency: '1-30 days',
      avgLatency: '< 100ms',
      costPerTB: '$10/month',
      retentionDays: 90,
      description: 'Transitional / unclassified workloads',
    },
    {
      name: 'Cold',
      icon: Snowflake,
      datasets: tierAssignments?.cold || [],
      color: 'cold',
      accessFrequency: '30-90 days',
      avgLatency: '< 1s',
      costPerTB: '$4/month',
      retentionDays: 365,
      description: 'Cost-optimized cool storage',
    },
    {
      name: 'Archive',
      icon: Package,
      datasets: tierAssignments?.archive || [],
      color: 'archive',
      accessFrequency: '> 90 days',
      avgLatency: '1-12 hours',
      costPerTB: '$1/month',
      retentionDays: 2555,
      description: 'Long-term archival retention',
    },
  ];

  const seasonalRules: Record<Season, { hotMultiplier: number; description: string }> = {
    festive: {
      hotMultiplier: 1.2,
      description: 'Festive demand raises hot-tier sensitivity for active retail datasets.',
    },
    monsoon: {
      hotMultiplier: 1.0,
      description: 'Monsoon maintains balanced hot/cool transitions.',
    },
    dry: {
      hotMultiplier: 0.9,
      description: 'Dry season favors cooler tiers for cost optimization.',
    },
    historical: {
      hotMultiplier: 0.8,
      description: 'Historical mode aggressively prioritizes archive posture.',
    },
  };

  const currentSeason = (currentSeasonInfo?.season as Season) || 'festive';
  const seasonalRule = seasonalRules[currentSeason];
  const datasetDetails = tierAssignments?.dataset_details || [];
  const policyRules = tierAssignments?.policy_rules || defaultPolicyRules;

  const totalDatasets = datasetDetails.length > 0
    ? datasetDetails.length
    : tiers.reduce((sum, tier) => sum + tier.datasets.length, 0);

  const estimatedMonthlyCost = tiers.reduce((sum, tier) => {
    const cost = parseFloat(tier.costPerTB.replace('$', '').replace('/month', ''));
    return sum + cost * tier.datasets.length * 0.5;
  }, 0);

  const mismatchedDatasets = datasetDetails.filter((item) =>
    isTierMismatch(item.current_blob_tier, item.target_policy_tier)
  );

  const policyAlignmentPct = datasetDetails.length > 0
    ? ((datasetDetails.length - mismatchedDatasets.length) / datasetDetails.length) * 100
    : 100;

  const estimatedMonthlySavings = datasetDetails.reduce((sum, item) => {
    const currentCost = monthlyCostPerTbByTier(item.current_blob_tier) * 0.5;
    const targetCost = monthlyCostPerTbByTier(item.target_policy_tier) * 0.5;
    return sum + Math.max(0, currentCost - targetCost);
  }, 0);

  const archiveCandidates = datasetDetails.filter(
    (item) => normalizeTierLabel(item.target_policy_tier) === 'ARCHIVE'
  ).length;

  const seasonalOverrideCount = datasetDetails.filter(
    (item) => (item.tier_reason_type || '').toLowerCase() === 'seasonal'
  ).length;

  const accessOverrideCount = datasetDetails.filter(
    (item) => (item.tier_reason_type || '').toLowerCase() === 'access-based'
  ).length;

  if (loading) {
    return (
      <div className="page-section">
        <div className="loading-state">Loading storage tier data...</div>
      </div>
    );
  }

  return (
    <div className="page-section">
      <div className="section-header">
        <div>
          <h2>Intelligent Storage Tiers</h2>
          <p className="section-description">
            Policy-driven Azure Blob tiering using layer, age, access, and seasonal context
          </p>
        </div>
        <div className="section-actions">
          <button
            className="btn btn-ghost"
            onClick={handleSyncTiers}
            disabled={syncing}
          >
            {/* @ts-ignore */}
            <RefreshCw size={16} strokeWidth={2} className={syncing ? 'spinning' : ''} />
            {syncing ? 'Syncing...' : 'Sync from Azure'}
          </button>
          <button
            className={`btn ${seasonalMode ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSeasonalMode(!seasonalMode)}
          >
            {seasonalMode ? '✓ Seasonal Mode Active' : 'Enable Seasonal Mode'}
          </button>
        </div>
      </div>

      {tierAssignments?.source && (
        <div style={{ marginBottom: '1rem' }}>
          <Badge
            label={`Data Source: ${tierAssignments.source === 'azure' ? 'Azure Blob Storage' : tierAssignments.source}`}
            tone={tierAssignments.source === 'azure' ? 'success' : 'warning'}
          />
          {tierAssignments.last_updated && (
            <span style={{ marginLeft: '0.5rem', color: '#64748b', fontSize: '0.875rem' }}>
              Last updated: {new Date(tierAssignments.last_updated).toLocaleString()}
            </span>
          )}
        </div>
      )}

      <div className="metrics-grid">
        <div className="metric-card">
          {/* @ts-ignore */}
          <div className="metric-icon"><HardDrive size={20} strokeWidth={2} /></div>
          <div className="metric-content">
            <div className="metric-label">Total Datasets</div>
            <div className="metric-value">{totalDatasets}</div>
          </div>
        </div>
        <div className="metric-card">
          {/* @ts-ignore */}
          <div className="metric-icon"><DollarSign size={20} strokeWidth={2} /></div>
          <div className="metric-content">
            <div className="metric-label">Est. Monthly Cost</div>
            <div className="metric-value">${estimatedMonthlyCost.toFixed(2)}</div>
          </div>
        </div>
        <div className="metric-card">
          {/* @ts-ignore */}
          <div className="metric-icon"><Zap size={20} strokeWidth={2} /></div>
          <div className="metric-content">
            <div className="metric-label">Hot Tier Datasets</div>
            <div className="metric-value">{tiers[0].datasets.length}</div>
          </div>
        </div>
        <div className="metric-card">
          {/* @ts-ignore */}
          <div className="metric-icon"><Lock size={20} strokeWidth={2} /></div>
          <div className="metric-content">
            <div className="metric-label">Archive Datasets</div>
            <div className="metric-value">{tiers[3].datasets.length}</div>
          </div>
        </div>
      </div>

      {seasonalMode && currentSeasonInfo && (
        <div className="card seasonal-alert">
          <div className="seasonal-header">
            <div className="seasonal-icon">
              {/* @ts-ignore */}
              <Calendar size={24} strokeWidth={2} />
            </div>
            <div className="seasonal-content">
              <h3>
                {currentSeasonInfo.description || `${currentSeason.charAt(0).toUpperCase() + currentSeason.slice(1)} Season`}
              </h3>
              <p>{seasonalRule.description}</p>
              <div className="seasonal-metrics">
                <Badge
                  label={`Hot Sensitivity: ${(seasonalRule.hotMultiplier * 100).toFixed(0)}%`}
                  tone={seasonalRule.hotMultiplier > 1 ? 'info' : 'success'}
                />
                <Badge
                  label={tierAssignments?.auto_tiering_enabled ? 'Auto-tiering Active' : 'Manual Mode'}
                  tone={tierAssignments?.auto_tiering_enabled ? 'success' : 'warning'}
                />
                <Badge label={`Month: ${currentSeasonInfo.month}`} tone="info" />
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="tiers-section">
        <h3>Storage Tier Breakdown</h3>
        <div className="storage-tiers-grid-detailed">
          {tiers.map((tier) => {
            const Icon = tier.icon;
            const isSelected = selectedTier === tier.name.toLowerCase();
            return (
              <div 
                key={tier.name} 
                className={`tier-card-detailed ${tier.color} ${isSelected ? 'selected' : ''}`}
                onClick={() => setSelectedTier(isSelected ? null : tier.name.toLowerCase())}
                style={{ cursor: 'pointer', transition: 'all 0.3s ease' }}
              >
                <div className="tier-card-header">
                  <div className="tier-icon-large">
                    {/* @ts-ignore */}
                    <Icon size={28} strokeWidth={2} />
                  </div>
                  <div className="tier-title-section">
                    <h4>{tier.name} Tier</h4>
                    <div className="tier-subtitle">{tier.description}</div>
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
                    <div className="datasets-header">Datasets in This Tier</div>
                    <div className="datasets-list">
                      {tier.datasets.slice(0, isSelected ? undefined : 8).map((datasetName) => (
                        <div key={`${tier.name}-${datasetName}`} className="dataset-chip">
                          {datasetName}
                        </div>
                      ))}
                    </div>
                    {!isSelected && tier.datasets.length > 8 && (
                      <div style={{ textAlign: 'center', color: 'var(--muted)', fontSize: '12px', marginTop: '8px' }}>
                        +{tier.datasets.length - 8} more • Click to see all
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Dataset Tier Decisions</h3>
          <Badge label={`${datasetDetails.length} datasets`} tone="info" />
        </div>
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Dataset Name</th>
                <th>Medallion Layer</th>
                <th>Current Azure Tier</th>
                <th>Target Tier (Policy)</th>
                <th>Data Age</th>
                <th>Retention Policy</th>
                <th>Tier Decision Reason</th>
              </tr>
            </thead>
            <tbody>
              {datasetDetails.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', color: 'var(--muted)' }}>
                    No dataset-level tier details available yet. Run "Sync from Azure" to generate policy decisions.
                  </td>
                </tr>
              )}
              {datasetDetails.map((item, index) => {
                const hasMismatch = isTierMismatch(
                  item.current_blob_tier,
                  item.target_policy_tier
                );
                const tooltipMessage = hasMismatch
                  ? `Policy drift detected: current tier (${normalizeTierLabel(item.current_blob_tier)}) does not match policy target (${normalizeTierLabel(item.target_policy_tier)}). ${item.tier_apply_error ? `Error: ${item.tier_apply_error}` : 'Awaiting application from next sync.'}`
                  : '';

                return (
                  <tr
                    key={`${item.blob_path}-${index}`}
                    className={hasMismatch ? 'tier-mismatch-row' : ''}
                  >
                    <td>
                      <div className="table-cell-main">{item.dataset_name}</div>
                      <div className="table-cell-sub">{item.blob_path}</div>
                    </td>
                    <td>{item.medallion_layer}</td>
                    <td>
                      <Badge label={normalizeTierLabel(item.current_blob_tier)} tone={tierBadgeTone(item.current_blob_tier)} />
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <Badge label={normalizeTierLabel(item.target_policy_tier)} tone={tierBadgeTone(item.target_policy_tier)} />
                        {hasMismatch && (
                          <div className="tier-mismatch-tooltip">
                            {/* @ts-ignore */}
                            <AlertCircle size={16} strokeWidth={2} style={{ color: 'var(--warning)' }} />
                            <span className="tooltip-text">{tooltipMessage}</span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td>
                      {item.data_age_days === null || item.data_age_days === undefined
                        ? 'N/A'
                        : `${item.data_age_days} days`}
                    </td>
                    <td>{item.retention_days} days</td>
                    <td>{item.tier_reason}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Policy Transparency</h3>
          <Badge label="Rule-Based" tone="info" />
        </div>
        <div className="policy-section">
          <div className="policy-rule">
            {/* @ts-ignore */}
            <div className="policy-icon"><Flame size={20} strokeWidth={2} /></div>
            <div className="policy-content">
              <div className="policy-title">Bronze Layer Rules</div>
              <div className="policy-condition">
                HOT {policyRules.layer_rules.bronze.hot} · COOL {policyRules.layer_rules.bronze.cool} · ARCHIVE {policyRules.layer_rules.bronze.archive}
              </div>
            </div>
          </div>
          <div className="policy-rule">
            {/* @ts-ignore */}
            <div className="policy-icon"><Sun size={20} strokeWidth={2} /></div>
            <div className="policy-content">
              <div className="policy-title">Silver Layer Rules</div>
              <div className="policy-condition">
                HOT {policyRules.layer_rules.silver.hot} · COOL {policyRules.layer_rules.silver.cool} · ARCHIVE {policyRules.layer_rules.silver.archive}
              </div>
            </div>
          </div>
          <div className="policy-rule">
            {/* @ts-ignore */}
            <div className="policy-icon"><Snowflake size={20} strokeWidth={2} /></div>
            <div className="policy-content">
              <div className="policy-title">Gold Layer Rules</div>
              <div className="policy-condition">
                HOT {policyRules.layer_rules.gold.hot} · COOL {policyRules.layer_rules.gold.cool} · ARCHIVE {policyRules.layer_rules.gold.archive}
              </div>
            </div>
          </div>
          <div className="policy-rule">
            {/* @ts-ignore */}
            <div className="policy-icon"><RefreshCw size={20} strokeWidth={2} /></div>
            <div className="policy-content">
              <div className="policy-title">Access-Based Override</div>
              <div className="policy-condition">
                {policyRules.access_overrides?.promote_to_hot || defaultPolicyRules.access_overrides?.promote_to_hot}
                {' · '}
                {policyRules.access_overrides?.promote_archive_to_cool || defaultPolicyRules.access_overrides?.promote_archive_to_cool}
              </div>
            </div>
          </div>
          <div className="policy-rule">
            {/* @ts-ignore */}
            <div className="policy-icon"><Calendar size={20} strokeWidth={2} /></div>
            <div className="policy-content">
              <div className="policy-title">Seasonal Override</div>
              <div className="policy-condition">
                {policyRules.seasonal_override || defaultPolicyRules.seasonal_override}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Cost Optimization Insights</h3>
        </div>
        <div className="optimization-grid">
          <div className="optimization-card success">
            {/* @ts-ignore */}
            <div className="opt-icon"><DollarSign size={24} strokeWidth={2} /></div>
            <div className="opt-content">
              <div className="opt-value">${estimatedMonthlySavings.toFixed(2)}</div>
              <div className="opt-label">Potential Monthly Savings</div>
              <div className="opt-description">Difference between current and policy target tiers</div>
            </div>
          </div>
          <div className="optimization-card info">
            {/* @ts-ignore */}
            <div className="opt-icon"><Zap size={24} strokeWidth={2} /></div>
            <div className="opt-content">
              <div className="opt-value">{policyAlignmentPct.toFixed(1)}%</div>
              <div className="opt-label">Policy Alignment</div>
              <div className="opt-description">{mismatchedDatasets.length} datasets still need tier convergence</div>
            </div>
          </div>
          <div className="optimization-card warning">
            {/* @ts-ignore */}
            <div className="opt-icon"><AlertCircle size={24} strokeWidth={2} /></div>
            <div className="opt-content">
              <div className="opt-value">{archiveCandidates}</div>
              <div className="opt-label">Archive Candidates</div>
              <div className="opt-description">
                Seasonal overrides: {seasonalOverrideCount} · Access overrides: {accessOverrideCount}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

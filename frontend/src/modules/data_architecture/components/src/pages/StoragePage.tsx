import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import * as dashboardApi from '../api/dashboardApi';
import type { DashboardSummaryResponse, SeasonalStorageAnalyticsResponse } from '../types';
import { MetricCard } from '../cards/MetricCard';
import { Panel } from '../panels/Panel';
import { compactDateTime, formatBytes } from '../utils/formatters';

interface StoragePageProps {
  summary: DashboardSummaryResponse;
}

const SEASON_OPTIONS = ['current', 'Summer', 'Winter', 'Festive', 'Clearance'];

const TIER_COLORS: Record<string, string> = {
  HOT: '#ef4444',
  WARM: '#f59e0b',
  COLD: '#3b82f6',
  ARCHIVE: '#6b7280',
  UNKNOWN: '#9ca3af',
};

function tierTone(value: string): React.CSSProperties {
  const tier = value.toUpperCase();
  if (tier === 'HOT') {
    return { backgroundColor: '#fee2e2', color: '#991b1b' };
  }
  if (tier === 'WARM' || tier === 'COOL') {
    return { backgroundColor: '#fef3c7', color: '#92400e' };
  }
  if (tier === 'COLD' || tier === 'ARCHIVE') {
    return { backgroundColor: '#dbeafe', color: '#1e40af' };
  }
  return { backgroundColor: '#f3f4f6', color: '#374151' };
}

export function StoragePage({ summary }: StoragePageProps) {
  const { storage } = summary;
  const [seasonalMode, setSeasonalMode] = useState(false);
  const [selectedSeason, setSelectedSeason] = useState('current');
  const [seasonalData, setSeasonalData] = useState<SeasonalStorageAnalyticsResponse | null>(null);
  const [seasonalLoading, setSeasonalLoading] = useState(false);
  const [seasonalError, setSeasonalError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;

    async function loadSeasonalAnalytics() {
      if (!seasonalMode) {
        setSeasonalData(null);
        setSeasonalError(null);
        return;
      }

      try {
        setSeasonalLoading(true);
        const payload = await dashboardApi.getSeasonalStorageAnalytics(
          selectedSeason === 'current' ? undefined : selectedSeason,
        );
        if (!disposed) {
          setSeasonalData(payload);
          setSeasonalError(null);
        }
      } catch (err) {
        if (!disposed) {
          const message = err instanceof Error ? err.message : 'Failed to load seasonal analytics.';
          setSeasonalError(message);
          setSeasonalData(null);
        }
      } finally {
        if (!disposed) {
          setSeasonalLoading(false);
        }
      }
    }

    loadSeasonalAnalytics();
    return () => {
      disposed = true;
    };
  }, [seasonalMode, selectedSeason]);

  const activeStorageBytes = useMemo(() => {
    if (seasonalMode && seasonalData) {
      return {
        total: seasonalData.hot_storage_bytes + seasonalData.warm_storage_bytes + seasonalData.cold_storage_bytes,
        hot: seasonalData.hot_storage_bytes,
        warm: seasonalData.warm_storage_bytes,
        cold: seasonalData.cold_storage_bytes,
      };
    }
    return {
      total: storage.total_size_bytes,
      hot: storage.hot_tier_bytes,
      warm: storage.warm_tier_bytes,
      cold: storage.cold_tier_bytes,
    };
  }, [seasonalMode, seasonalData, storage]);

  const tierUsageData = useMemo(() => {
    if (seasonalMode && seasonalData) {
      return seasonalData.storage_distribution.map((tier) => ({
        name: tier.tier,
        value: tier.size_gb,
        fill: TIER_COLORS[tier.tier.toUpperCase()] || TIER_COLORS.UNKNOWN,
      }));
    }

    return storage.tier_usage.map((tier) => {
      const tierName = String(tier.tier || 'UNKNOWN').toUpperCase();
      const gbValue =
        typeof tier.size_gb === 'number'
          ? tier.size_gb
          : Number(tier.size_bytes || 0) / (1024 ** 3);
      return {
        name: tierName,
        value: gbValue,
        fill: TIER_COLORS[tierName] || TIER_COLORS.UNKNOWN,
      };
    });
  }, [seasonalMode, seasonalData, storage.tier_usage]);

  const growthData = (storage.growth_timeline || []).map((point) => ({
    date: point.date,
    GB: point.total_gb,
  }));

  const fallbackGrowthData = (storage.storage_growth_over_time || []).map((point) => ({
    date: point.date,
    GB: point.cumulative_size_gb,
  }));

  const storageGrowthSeries = growthData.length > 0 ? growthData : fallbackGrowthData;

  const datasetActivityData = useMemo(() => {
    if (!seasonalMode || !seasonalData) {
      return [];
    }

    return seasonalData.dataset_activity.map((item) => ({
      dataset: item.dataset.length > 20 ? `${item.dataset.slice(0, 20)}...` : item.dataset,
      sizeGb: item.size_gb,
      tier: item.tier,
    }));
  }, [seasonalMode, seasonalData]);

  const tierMovementData = useMemo(
    () =>
      storage.tier_usage.map((tier) => ({
        tier: tier.tier,
        files: tier.file_count || 0,
      })),
    [storage.tier_usage],
  );

  const highlightedDatasets = useMemo(() => {
    if (!seasonalData) {
      return new Set<string>();
    }
    return new Set(seasonalData.highlighted_datasets.map((item) => item.toLowerCase()));
  }, [seasonalData]);

  return (
    <div className="grid-12 animate-fade page-grid">
      <div className="span-12">
        <Panel title="Seasonal Storage Tiering" subtitle="Analyze storage behavior by retail season">
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="action-button"
              onClick={() => setSeasonalMode((prev) => !prev)}
              style={{
                backgroundColor: seasonalMode ? '#0f766e' : '#1f2937',
                color: '#fff',
                border: 'none',
              }}
            >
              {seasonalMode ? 'Disable Seasonal Tiering Analytics' : 'Enable Seasonal Tiering Analytics'}
            </button>
            <label style={{ fontSize: '0.85rem', color: '#6b7280' }}>Simulate Season:</label>
            <select
              value={selectedSeason}
              onChange={(event) => setSelectedSeason(event.target.value)}
              disabled={!seasonalMode}
              style={{
                padding: '0.4rem 0.6rem',
                borderRadius: '6px',
                border: '1px solid #d1d5db',
                minWidth: '160px',
              }}
            >
              {SEASON_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option === 'current' ? 'Current Season' : option}
                </option>
              ))}
            </select>
            {seasonalLoading && <span style={{ color: '#6b7280', fontSize: '0.85rem' }}>Loading seasonal analytics...</span>}
            {seasonalError && <span style={{ color: '#b91c1c', fontSize: '0.85rem' }}>{seasonalError}</span>}
          </div>
        </Panel>
      </div>

      {seasonalMode && seasonalData && (
        <div className="span-12">
          <div
            style={{
              borderRadius: '10px',
              border: '1px solid #99f6e4',
              background: 'linear-gradient(90deg, #ecfeff, #f0fdfa)',
              padding: '0.9rem 1rem',
            }}
          >
            <div style={{ fontWeight: 700, color: '#134e4a' }}>
              Current Retail Season: {seasonalData.current_season}
            </div>
            <div style={{ fontSize: '0.9rem', color: '#115e59', marginTop: '0.15rem' }}>
              Seasonal Tiering Optimization Active
            </div>
          </div>
        </div>
      )}

      <div className="span-3">
        <MetricCard
          label={seasonalMode ? 'Seasonal Storage' : 'Total Storage'}
          value={formatBytes(activeStorageBytes.total)}
          hint={seasonalMode ? 'Current season datasets' : 'All tiers combined'}
          tone="neutral"
        />
      </div>
      <div className="span-3">
        <MetricCard
          label="HOT Tier"
          value={formatBytes(activeStorageBytes.hot)}
          hint={seasonalMode ? 'Seasonal hot allocation' : 'Active datasets'}
          tone="neutral"
        />
      </div>
      <div className="span-3">
        <MetricCard
          label="WARM Tier"
          value={formatBytes(activeStorageBytes.warm)}
          hint={seasonalMode ? 'Seasonal warm allocation' : 'Seasonal access'}
          tone="neutral"
        />
      </div>
      <div className="span-3">
        <MetricCard
          label="COLD Tier"
          value={formatBytes(activeStorageBytes.cold)}
          hint={seasonalMode ? 'Seasonal cold allocation' : 'Archived datasets'}
          tone="neutral"
        />
      </div>

      <div className="span-6">
        <Panel
          title={seasonalMode ? 'Seasonal Storage Distribution' : 'Tier Usage Distribution'}
          subtitle={seasonalMode ? 'Hot / Warm / Cold for current season datasets' : 'Storage by tier'}
        >
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={tierUsageData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={(entry) => `${entry.name}: ${entry.value.toFixed(2)} GB`}
                >
                  {tierUsageData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number | undefined) => (value !== undefined ? `${value.toFixed(2)} GB` : 'N/A')} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel title="Storage Growth" subtitle="Total storage growth over time">
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={storageGrowthSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip formatter={(value: number | undefined) => (value !== undefined ? `${value.toFixed(2)} GB` : 'N/A')} />
                <Line type="monotone" dataKey="GB" stroke="#3b82f6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel
          title={seasonalMode ? 'Dataset Activity (Seasonal)' : 'Tier Movement Activity'}
          subtitle={seasonalMode ? 'Most active seasonal datasets' : 'File count by tier'}
        >
          <div className="chart-box large">
            <ResponsiveContainer width="100%" height="100%">
              {seasonalMode ? (
                <BarChart data={datasetActivityData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="dataset" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip formatter={(value: number | undefined) => (value !== undefined ? `${value.toFixed(2)} GB` : 'N/A')} />
                  <Bar dataKey="sizeGb" fill="#0f766e" />
                </BarChart>
              ) : (
                <BarChart data={tierMovementData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="tier" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="files" fill="#3b82f6" />
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <div className="span-6">
        <Panel title="Largest Datasets" subtitle="Top datasets by size">
          <div className="table-scroll table-scroll-medium">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Size</th>
                  <th>Tier</th>
                  <th>Last Modified</th>
                </tr>
              </thead>
              <tbody>
                {storage.largest_datasets.length > 0 ? (
                  storage.largest_datasets.map((dataset, idx) => {
                    const datasetName = (dataset.name || dataset.dataset || '').toString();
                    const tier = (dataset.tier || dataset.layer || 'unknown').toString().toUpperCase();
                    const highlighted = seasonalMode && highlightedDatasets.has(datasetName.toLowerCase());
                    return (
                      <tr key={idx} style={highlighted ? { backgroundColor: '#fffbeb' } : undefined}>
                        <td>{datasetName}</td>
                        <td>{formatBytes(dataset.size_bytes)}</td>
                        <td>
                          <span
                            style={{
                              padding: '0.25rem 0.5rem',
                              borderRadius: '4px',
                              fontSize: '0.8rem',
                              ...tierTone(tier),
                            }}
                          >
                            {tier}
                          </span>
                        </td>
                        <td>{compactDateTime(dataset.last_modified)}</td>
                      </tr>
                    );
                  })
                ) : (
                  <tr className="loading-row">
                    <td colSpan={4}>No dataset information available</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {seasonalMode && seasonalData && (
        <div className="span-12">
          <Panel title="Storage Optimization Panel" subtitle="Seasonal optimization insights">
            <div style={{ display: 'grid', gap: '0.85rem' }}>
              <div style={{ fontSize: '0.92rem', color: '#374151' }}>{seasonalData.optimization_insight}</div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.86rem', marginBottom: '0.4rem' }}>
                  Highlighted Seasonal Datasets
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  {seasonalData.highlighted_datasets.length > 0 ? (
                    seasonalData.highlighted_datasets.map((name) => (
                      <span
                        key={name}
                        style={{
                          padding: '0.3rem 0.55rem',
                          borderRadius: '999px',
                          backgroundColor: '#fef3c7',
                          color: '#92400e',
                          fontSize: '0.8rem',
                        }}
                      >
                        {name}
                      </span>
                    ))
                  ) : (
                    <span style={{ color: '#6b7280', fontSize: '0.85rem' }}>
                      No datasets tagged for the selected season.
                    </span>
                  )}
                </div>
              </div>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}

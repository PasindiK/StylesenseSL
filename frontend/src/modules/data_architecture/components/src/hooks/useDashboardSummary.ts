import { useCallback, useEffect, useState } from 'react';
import * as dashboardApi from '../api/dashboardApi';
import type { DashboardSummaryResponse } from '../types';

interface UseDashboardSummaryOptions {
  autoRefreshMs?: number;
}

export function useDashboardSummary(options?: UseDashboardSummaryOptions) {
  const autoRefreshMs = options?.autoRefreshMs ?? 45000;
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRefreshing(true);
      const data = await dashboardApi.getSummary();
      setSummary(data);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch dashboard summary.';
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefreshMs) {
      return;
    }
    const timer = window.setInterval(() => {
      refresh();
    }, autoRefreshMs);
    return () => window.clearInterval(timer);
  }, [autoRefreshMs, refresh]);

  return {
    summary,
    loading,
    refreshing,
    error,
    refresh,
  };
}

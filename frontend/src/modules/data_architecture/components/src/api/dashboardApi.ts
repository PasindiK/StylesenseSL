import type {
  ActionApiResponse,
  CurrentSeasonResponse,
  DashboardSummaryResponse,
  DriftDecisionResponse,
  DriftEventsResponse,
  LakehouseBronzeMetricsResponse,
  LakehouseDataFreshnessResponse,
  LakehouseGoldMetricsResponse,
  LakehouseIngestionMetricsResponse,
  LakehouseSilverMetricsResponse,
  LakehouseStorageAnalyticsResponse,
  LakehouseStorageGrowthResponse,
  LayerId,
  MedallionFilesResponse,
  LiveInputDatasetsResponse,
  LiveValidationResult,
  SeasonalStorageAnalyticsResponse,
  StakeholderViewsResponse,
  StoragePayload,
  GovernanceAnalytics,
} from '../types';

const API_BASE = import.meta.env.VITE_DATA_ARCH_API_URL || 'http://localhost:8003/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const baseHeaders: HeadersInit = isFormData
    ? {}
    : {
      'Content-Type': 'application/json',
    };

  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...baseHeaders,
      ...(options?.headers || {}),
    },
    ...options,
  });

  const body = await response.text();
  const payload = body ? JSON.parse(body) : null;

  if (!response.ok) {
    const message = payload?.detail
      ? typeof payload.detail === 'string'
        ? payload.detail
        : JSON.stringify(payload.detail)
      : `HTTP ${response.status}`;
    throw new Error(message);
  }

  return payload as T;
}

// Named exports
export async function getSummary() {
  return request<DashboardSummaryResponse>('/dashboard/summary');
}

export async function getMedallionFiles(layer: LayerId) {
  return request<MedallionFilesResponse>(`/medallion/${layer}/files`);
}

export async function getDriftEvents() {
  return request<DriftEventsResponse>('/drift/events');
}

export async function getGovernanceAudit() {
  return request<GovernanceAnalytics>('/governance/audit-log');
}

export async function getStorageTierStatistics() {
  return request<StoragePayload>('/storage/tier-statistics');
}

export async function getStakeholderViews(type: string) {
  return request<StakeholderViewsResponse>(`/stakeholder/views/${encodeURIComponent(type)}`);
}

export async function approveDrift(table: string, eventId: string) {
  return request<DriftDecisionResponse>('/approve-drift', {
    method: 'POST',
    body: JSON.stringify({ table, event_id: eventId }),
  });
}

export async function rejectDrift(table: string, eventId: string) {
  return request<DriftDecisionResponse>('/reject-drift', {
    method: 'POST',
    body: JSON.stringify({ table, event_id: eventId }),
  });
}

export async function runKafkaIngestion() {
  return request<ActionApiResponse>('/actions/kafka-ingestion', { method: 'POST' });
}

export async function runBronzeToSilver() {
  return request<ActionApiResponse>('/actions/bronze-to-silver', { method: 'POST' });
}

export async function runSilverToGold() {
  return request<ActionApiResponse>('/actions/silver-to-gold', { method: 'POST' });
}

export async function runDataQualityChecks() {
  return request<ActionApiResponse>('/actions/data-quality-checks', { method: 'POST' });
}

export async function runStakeholderViews() {
  return request<ActionApiResponse>('/actions/generate-stakeholder-views', { method: 'POST' });
}

export async function getLakehouseBronzeMetrics() {
  return request<LakehouseBronzeMetricsResponse>('/lakehouse/bronze-metrics');
}

export async function getLakehouseSilverMetrics() {
  return request<LakehouseSilverMetricsResponse>('/lakehouse/silver-metrics');
}

export async function getLakehouseGoldMetrics() {
  return request<LakehouseGoldMetricsResponse>('/lakehouse/gold-metrics');
}

export async function getLakehouseStorageAnalytics() {
  return request<LakehouseStorageAnalyticsResponse>('/lakehouse/storage-analytics');
}

export async function getLakehouseStorageGrowth() {
  return request<LakehouseStorageGrowthResponse>('/lakehouse/storage-growth');
}

export async function getLakehouseIngestionMetrics() {
  return request<LakehouseIngestionMetricsResponse>('/lakehouse/ingestion-metrics');
}

export async function getLakehouseDataFreshness() {
  return request<LakehouseDataFreshnessResponse>('/lakehouse/data-freshness');
}

export async function getCurrentSeason(simulateSeason?: string) {
  const suffix = simulateSeason
    ? `?simulate_season=${encodeURIComponent(simulateSeason)}`
    : '';
  return request<CurrentSeasonResponse>(`/lakehouse/current-season${suffix}`);
}

export async function getSeasonalStorageAnalytics(simulateSeason?: string) {
  const suffix = simulateSeason
    ? `?simulate_season=${encodeURIComponent(simulateSeason)}`
    : '';
  return request<SeasonalStorageAnalyticsResponse>(`/lakehouse/seasonal-analytics${suffix}`);
}

export async function getLiveInputDatasets(limit = 15, sampleRows = 5) {
  const query = `?limit=${encodeURIComponent(String(limit))}&sample_rows=${encodeURIComponent(String(sampleRows))}`;
  return request<LiveInputDatasetsResponse>(`/drift/live-inputs${query}`);
}

export async function validateUploadedDataset(payload: {
  file: File;
  baselineDatasetId: string;
  datasetName?: string;
  ingestToBronze?: boolean;
}) {
  const body = new FormData();
  body.append('upload_file', payload.file);
  body.append('baseline_dataset_id', payload.baselineDatasetId);
  if (payload.datasetName) {
    body.append('dataset_name', payload.datasetName);
  }
  body.append('ingest_to_bronze', String(payload.ingestToBronze ?? true));

  return request<LiveValidationResult>('/drift/live-validate-upload', {
    method: 'POST',
    body,
  });
}

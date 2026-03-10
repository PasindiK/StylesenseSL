export type DashboardPageId =
  | 'overview'
  | 'live_validation'
  | 'explainability'
  | 'actions'
  | 'medallion'
  | 'approvals'
  | 'timeline'
  | 'storage';

export type LayerId = 'bronze' | 'silver' | 'gold';

export interface LayerFile {
  layer: LayerId | string;
  name: string;
  dataset_name: string;
  path: string;
  size_bytes: number;
  records: number;
  last_modified: string;
  access_tier: string;
  source: string;
}

export interface LayerSummary {
  file_count: number;
  size_bytes: number;
  size_gb: number;
  records: number;
  records_today: number;
  latest_ingestion: string | null;
}

export interface DriftCounts {
  new?: number;
  missing?: number;
  dtype?: number;
  renames?: number;
}

export interface DriftEvent {
  file: string;
  table: string;
  timestamp: string;
  decision?: string;
  requires_approval?: boolean;
  approved?: boolean;
  rejected?: boolean;
  risk_level?: string;
  counts?: DriftCounts;
  diff?: {
    new_columns?: string[];
    missing_columns?: string[];
    dtype_changes?: Array<{ column: string; expected: string; actual: string }>;
    renames?: Array<{ old_name: string; new_name: string; similarity: number; type_match: boolean }>;
  };
}

export interface TierUsageItem {
  tier: string;
  size_bytes: number;
  size_gb?: number;
  file_count?: number;
}

export interface PipelineStageMetric {
  stage: string;
  records_processed: number;
  success_rate: number;
  failed_records: number;
}

export interface IngestionPoint {
  timestamp: string;
  records: number;
}

export interface FailedMessagePoint {
  timestamp: string;
  failed: number;
}

export interface ConsumerLagPoint {
  timestamp: string;
  lag_minutes: number;
}

export interface DailyIngestionPoint {
  date: string;
  records: number;
}

export interface FreshnessPoint {
  date: string;
  bronze_freshness_hours: number | null;
  silver_freshness_hours: number | null;
  gold_freshness_hours: number | null;
  bronze_last_update?: string | null;
  silver_last_update?: string | null;
  gold_last_update?: string | null;
}

export interface OverviewPayload {
  metrics: {
    total_records_ingested_today: number;
    bronze_files_count: number;
    silver_datasets_count: number;
    gold_tables_count: number;
    active_drift_alerts: number;
    data_quality_score: number;
  };
  pipeline_flow: PipelineStageMetric[];
  freshness: FreshnessPoint[];
  ingestion_metrics: {
    records_per_minute: IngestionPoint[];
    records_per_hour: IngestionPoint[];
    daily_ingestion_volume: DailyIngestionPoint[];
    failed_messages: FailedMessagePoint[];
    consumer_lag: ConsumerLagPoint[];
  };
  data_volume_distribution: Array<{ layer: string; size_bytes: number }>;
  storage_tier_usage: TierUsageItem[];
}

export interface GovernanceAnalytics {
  metric_cards: {
    audit_events_today: number;
    access_requests: number;
    policy_violations: number;
    unauthorized_access_attempts: number;
  };
  audit_activity_per_hour: Array<{ hour: string; count: number }>;
  stakeholder_access: Array<{ stakeholder: string; count: number }>;
  regional_access: Array<{ province: string; count: number }>;
  compliance_indicators: Array<{ name: string; status: string }>;
  audit_events: Array<Record<string, unknown>>;
}

export interface ServiceRbacPrincipal {
  service_name: string;
  principal_id: string;
  container: string;
  allowed_operations: string[];
  allowed_layers: string[];
  data_categories: string[];
  created_at: string;
}

export interface ServiceRbacConfigResponse {
  generated_at: string;
  exported_at: string;
  total_services: number;
  service_principals: ServiceRbacPrincipal[];
}

export interface ServiceAccessCheckResponse {
  generated_at: string;
  service_name: string;
  operation: string;
  layer: string;
  data_category: string;
  access_granted: boolean;
  reason: string;
}

export interface ServiceRbacAuditEntry {
  timestamp: string;
  service_name: string;
  operation: string;
  layer: string;
  data_category: string;
  access_granted: boolean;
  reason: string;
}

export interface ServiceRbacAuditLogResponse {
  generated_at: string;
  service_filter: string | null;
  total_entries: number;
  entries: ServiceRbacAuditEntry[];
}

export interface ExplainabilityPayload {
  feature_importance: Array<{
    action: string;
    count?: number;
    features: Array<{ name: string; weight: number }>;
  }>;
  embedding_clusters: Array<{ x: number; y: number; cluster: string; label: string }>;
  recommendation_explanations: Array<{ title: string; reason: string; confidence: number }>;
  ml_dataset_metrics: {
    training_dataset_size: number;
    feature_count: number;
    embedding_vectors_generated: number;
    model_accuracy: number;
  };
}

export interface MedallionPayload {
  metrics: {
    bronze_records: number;
    silver_records: number;
    gold_records: number;
  };
  layer_comparison: Array<{ layer: string; records: number }>;
  transformation_success_rate: number;
  dataset_explorer: {
    bronze: LayerFile[];
    silver: LayerFile[];
    gold: LayerFile[];
  };
}

export interface ApprovalPayload {
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  events: DriftEvent[];
}

export interface TimelineEvent {
  timestamp: string;
  operation: string;
  records_processed: number;
  dataset?: string;
}

export interface StoragePayload {
  total_size_bytes: number;
  hot_tier_bytes: number;
  warm_tier_bytes: number;
  cold_tier_bytes: number;
  metric_cards: {
    total_storage_used: number;
    hot_tier_size: number;
    warm_tier_size: number;
    cold_tier_size: number;
  };
  tier_usage: TierUsageItem[];
  growth_timeline: Array<{
    date: string;
    total_gb: number;
  }>;
  storage_growth_over_time: Array<{
    date: string;
    daily_size_bytes: number;
    daily_size_gb: number;
    cumulative_size_bytes: number;
    cumulative_size_gb: number;
  }>;
  largest_datasets: Array<{
    name?: string;
    dataset: string;
    path: string;
    layer: string;
    tier?: string;
    size_bytes: number;
    size_mb: number;
    records: number;
    last_modified: string;
  }>;
  tier_movement_activity: Array<{ date: string; movements: number }>;
}

export interface DashboardSummaryResponse {
  generated_at: string;
  source: Record<string, string>;
  overview: OverviewPayload;
  governance: GovernanceAnalytics;
  explainability: ExplainabilityPayload;
  actions: {
    pipeline_status: string;
    last_run: string;
  };
  medallion: MedallionPayload;
  approvals: ApprovalPayload;
  timeline: TimelineEvent[];
  storage: StoragePayload;
}

export interface MedallionFilesResponse {
  layer: LayerId;
  source: string;
  count: number;
  files: LayerFile[];
  summary: LayerSummary;
}

export interface DriftEventsResponse {
  count: number;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  events: DriftEvent[];
}

export interface StakeholderViewsResponse {
  stakeholder_type: string;
  count: number;
  views: Array<{
    name: string;
    path: string;
    size_bytes: number;
    records: number;
    last_modified: string;
  }>;
}

export interface ActionApiResponse {
  operation: string;
  status: string;
  message: string;
  result: Record<string, unknown>;
}

export interface DriftDecisionResponse {
  status: string;
  table: string;
  event_id: string;
  timestamp: string;
}

export interface LakehouseBronzeMetricsResponse {
  generated_at: string;
  source: string;
  azure_error?: string | null;
  bronze_file_count: number;
  bronze_storage_bytes: number;
  bronze_storage_gb: number;
  files_ingested_today: number;
  latest_ingestion_timestamp: string | null;
  daily_ingestion_file_counts: Array<{ date: string; files: number; size_bytes: number }>;
}

export interface LakehouseSilverMetricsResponse {
  generated_at: string;
  source: string;
  azure_error?: string | null;
  silver_dataset_count: number;
  transformation_timestamps: string[];
  transformation_success_rate: number;
  bronze_record_estimate: number;
  silver_record_estimate: number;
}

export interface LakehouseGoldMetricsResponse {
  generated_at: string;
  source: string;
  azure_error?: string | null;
  gold_file_count: number;
  analytical_tables_count: number;
  feature_datasets_count: number;
  stakeholder_views_generated: number;
}

export interface LakehouseStorageAnalyticsResponse {
  generated_at: string;
  source_by_layer: Record<string, string>;
  azure_errors?: Record<string, string | null>;
  total_size_bytes: number;
  total_size_gb: number;
  tier_usage: Array<{ tier: string; size_bytes: number; size_gb: number; file_count: number }>;
  largest_datasets: Array<{
    dataset: string;
    file_name: string;
    path: string;
    layer: string;
    size_bytes: number;
    size_gb: number;
    access_tier: string;
    last_modified: string;
  }>;
}

export interface LakehouseStorageGrowthResponse {
  generated_at: string;
  source_by_layer: Record<string, string>;
  azure_errors?: Record<string, string | null>;
  points: Array<{ date: string; size_bytes: number; size_gb: number; file_count: number }>;
}

export interface LakehouseIngestionMetricsResponse {
  generated_at: string;
  source: string;
  azure_error?: string | null;
  records_ingested_per_minute: Array<{ timestamp: string; records: number }>;
  records_ingested_per_hour: Array<{ timestamp: string; records: number }>;
  records_ingested_per_day: Array<{ date: string; records: number }>;
}

export interface LakehouseDataFreshnessResponse {
  generated_at: string;
  layers: Array<{
    layer: string;
    latest_update: string | null;
    freshness_hours: number | null;
    file_count: number;
    source: string;
    azure_error?: string | null;
  }>;
}

export interface CurrentSeasonResponse {
  generated_at: string;
  current_season: string;
}

export interface SeasonalStorageAnalyticsResponse {
  generated_at: string;
  current_season: string;
  seasonal_mode: boolean;
  source_by_layer: Record<string, string>;
  azure_errors?: Record<string, string | null>;
  dataset_count: number;
  hot_storage_bytes: number;
  warm_storage_bytes: number;
  cold_storage_bytes: number;
  hot_storage_gb: number;
  warm_storage_gb: number;
  cold_storage_gb: number;
  storage_distribution: Array<{ tier: string; size_bytes: number; size_gb: number }>;
  dataset_activity: Array<{
    dataset: string;
    size_bytes: number;
    size_gb: number;
    tier: string;
    layer: string;
    latest_modified: string;
  }>;
  highlighted_datasets: string[];
  optimization_insight: string;
}

export interface LiveInputSchemaColumn {
  column: string;
  dtype: string;
}

export interface LiveInputDataset {
  id: string;
  dataset_name: string;
  file_name: string;
  path: string;
  source_layer: string;
  size_bytes: number;
  row_count_estimate: number;
  last_modified: string;
  columns: string[];
  schema: LiveInputSchemaColumn[];
  sample_rows: Array<Record<string, unknown>>;
}

export interface LiveInputDatasetsResponse {
  generated_at: string;
  count: number;
  datasets: LiveInputDataset[];
}

export interface LiveValidationMetricsSnapshot {
  total_records_ingested_today: number;
  bronze_files_count: number;
  active_drift_alerts: number;
  data_quality_score: number;
  total_storage_used_gb: number;
  pipeline_status: string;
}

export interface LiveValidationResult {
  generated_at: string;
  status_message: string;
  drift_detected: boolean;
  risk_level: string;
  drift_counts: DriftCounts;
  diff: {
    new_columns?: string[];
    missing_columns?: string[];
    dtype_changes?: Array<{ column: string; expected: string; actual: string }>;
    renames?: Array<{ old_name: string; new_name: string; similarity: number; type_match: boolean }>;
  };
  event_id: string | null;
  baseline_dataset_id: string;
  baseline_schema: LiveInputSchemaColumn[];
  uploaded_schema: LiveInputSchemaColumn[];
  uploaded_preview: Array<Record<string, unknown>>;
  ingestion: {
    saved: boolean;
    local_path: string | null;
    size_bytes?: number;
    azure_blob_path?: string;
    azure_upload_error?: string;
  };
  before_metrics: LiveValidationMetricsSnapshot;
  after_metrics: LiveValidationMetricsSnapshot;
}

export interface SchemaVersion {
  version: number;
  timestamp: string;
  approved_at: string;
  approved_by: string;
  source_file: string;
  event_id: string;
  changes: {
    new_columns: string[];
    missing_columns: string[];
    dtype_changes: Array<{ column: string; expected: string; actual: string }>;
    renames: Array<{ old_name: string; new_name: string; similarity: number; type_match: boolean }>;
  };
  change_summary: DriftCounts;
  risk_level: string;
  is_baseline?: boolean;
  is_current_baseline?: boolean;
  notes?: string;
  ingestion?: {
    saved: boolean;
    local_path: string;
    azure_blob_path: string;
    size_bytes: number;
  };
}

export interface SchemaVersionTableGroup {
  table: string;
  baseline_dataset?: string | null;
  current_schema?: LiveInputSchemaColumn[];
  version_count: number;
  active_baseline_version?: number | null;
  latest_available_version?: number | null;
  latest_version: SchemaVersion | null;
  versions: SchemaVersion[];
}

export interface SchemaVersionsResponse {
  generated_at: string;
  table?: string;
  baseline_dataset?: string | null;
  current_schema?: LiveInputSchemaColumn[];
  version_count?: number;
  active_baseline_version?: number | null;
  latest_available_version?: number | null;
  latest_version?: SchemaVersion | null;
  versions?: SchemaVersion[];
  table_count?: number;
  tables?: SchemaVersionTableGroup[];
}

export interface SchemaRollbackResponse {
  status: string;
  table: string;
  active_baseline_version: number;
  available_versions: number[];
  schema: SchemaVersionsResponse;
}

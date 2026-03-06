export interface Notification {
  timestamp?: string;
  table?: string;
  reason?: string;
  type?: string;
  risk_level?: string;
}

export interface LiveMetrics {
  total_drifts: number;
  auto_resolved: number;
  pending_approvals: number;
  quarantined: number;
  pipeline_status: string;
  automation_rate_pct?: number;
  success_rate_pct?: number;
  avg_resolution_hours?: number;
  governance_rules_count?: number;
  throughput_records_per_sec?: number;
  active_pipelines?: number;
  data_volume_tb?: number;
  quality_score_pct?: number;
}

export interface DriftEvent {
  file: string;
  table: string;
  timestamp: string;
  decision?: string;
  source_file?: string;
  diff?: {
    new_columns?: string[];
    missing_columns?: string[];
    dtype_changes?: { column: string; expected: string; actual: string }[];
    renames?: { old_name: string; new_name: string; similarity: number; type_match: boolean }[];
  };
  counts?: { new: number; missing: number; dtype: number; renames?: number };
  requires_approval?: boolean;
  risk_level?: string;
}

export interface QuarantineItem {
  dataset: string;
  filename: string;
  quarantine_date: string;
  reason: string[];
  rows_preview: number;
  columns: string[];
  preview: any[];
  status: string;
}

export interface DetailedMetrics {
  total_drifts_list: {
    timestamp?: string;
    table?: string;
    drift_type?: string;
    action?: string;
    approval_status?: string;
    policy_confidence?: number;
    counts?: { new?: number; missing?: number; dtype?: number; renames?: number };
    risk_level?: string;
  }[];
  auto_resolved_list: {
    timestamp?: string;
    table?: string;
    drift_type?: string;
    action?: string;
    approval_status?: string;
    policy_confidence?: number;
    counts?: { new?: number; missing?: number; dtype?: number; renames?: number };
    risk_level?: string;
  }[];
  pending_approvals_list: {
    timestamp?: string;
    table?: string;
    drift_type?: string;
    action?: string;
    approval_status?: string;
    policy_confidence?: number;
    counts?: { new?: number; missing?: number; dtype?: number; renames?: number };
    risk_level?: string;
  }[];
  quarantined_list: QuarantineItem[];
}

export interface DatasetTierDetail {
  dataset_name: string;
  medallion_layer: 'bronze' | 'silver' | 'gold' | string;
  blob_path: string;
  current_blob_tier: string;
  target_policy_tier: string;
  data_age_days?: number | null;
  retention_days: number;
  tier_reason: string;
  tier_reason_type?: string;
  access_frequency_days?: number | null;
  last_modified?: string | null;
  last_accessed?: string | null;
  tier_change_applied?: boolean;
  tier_apply_error?: string | null;
}

export interface StoragePolicyRules {
  layer_rules: {
    bronze: { hot: string; cool: string; archive: string };
    silver: { hot: string; cool: string; archive: string };
    gold: { hot: string; cool: string; archive: string };
  };
  access_overrides?: {
    promote_to_hot?: string;
    promote_archive_to_cool?: string;
  };
  seasonal_override?: string;
  seasonal_examples?: Record<string, string[]>;
}

export interface StorageTierAssignments {
  hot: string[];
  warm: string[];
  cold: string[];
  archive: string[];
  dataset_details: DatasetTierDetail[];
  policy_rules?: StoragePolicyRules;
  last_updated: string;
  season: string;
  auto_tiering_enabled: boolean;
  source?: string;
}

export interface SeasonalRecommendations {
  season: string;
  recommendations: {
    hot: string[];
    warm: string[];
    cold: string[];
    archive: string[];
  };
  source?: string;
}

export interface CurrentSeason {
  season: string;
  month: number;
  description: string;
  source?: string;
}

export interface GovernancePolicy {
  id: string;
  name: string;
  status: 'active' | 'review' | 'warning' | string;
  description: string;
  affected_datasets: number;
}

export interface GovernanceQualityRule {
  id: string;
  name: string;
  description: string;
  datasets: number;
  passed: number;
  failed: number;
  coverage: string;
}

export interface GovernanceCompliance {
  standard: string;
  status: 'compliant' | 'review' | 'warning' | string;
  score: string;
  audits: number;
}

export interface GovernanceSnapshot {
  generated_at: string;
  source: string;
  policies: GovernancePolicy[];
  quality_rules: GovernanceQualityRule[];
  compliance: GovernanceCompliance[];
}

export interface DashboardData {
  generated_at: string;
  live_metrics?: LiveMetrics;
  detailed_metrics?: DetailedMetrics;
  governance?: GovernanceSnapshot;
  notifications?: Notification[];
  drift_events: DriftEvent[];
  latest_decision?: {
    timestamp?: string;
    table?: string;
    drift_type?: string;
    action?: string;
    approval_status?: string;
    policy_confidence?: number;
    counts?: { new?: number; missing?: number; dtype?: number; renames?: number };
    risk_level?: string;
  } | null;
  decisions_timeline?: {
    timestamp?: string;
    table?: string;
    drift_type?: string;
    action?: string;
    approval_status?: string;
    policy_confidence?: number;
    counts?: { new?: number; missing?: number; dtype?: number; renames?: number };
    risk_level?: string;
  }[];
  pending_approvals?: DriftEvent[];
  architecture?: {
    stages?: { name: string; status?: string; datasets?: string[] }[];
    drift_gate_note?: string;
    storage_tiers?: {
      hot?: string[];
      warm?: string[];
      cold?: string[];
      archive?: string[];
    };
  };
  action_distribution?: {
    action: string;
    count: number;
    automated: number;
    human_reviewed: number;
  }[];
  feature_importance?: {
    action: string;
    features: { name: string; weight: number }[];
  }[];
  dq_results?: {
    file: string;
    is_acceptable: boolean;
    hard_failures: number;
    soft_warnings: number;
    hard_failures_list?: string[];
    soft_warnings_list?: string[];
  }[];
  quarantine_details?: QuarantineItem[];
  dataset_overview?: Record<string, any>;
  csv_previews?: Record<
    string,
    {
      layer: string;
      file: string;
      rows_total: number;
      columns: string[];
      preview: Record<string, any>[];
    }
  >;
}

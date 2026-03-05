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

export interface DashboardData {
  generated_at: string;
  live_metrics?: LiveMetrics;
  detailed_metrics?: DetailedMetrics;
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
  action_distribution?: { action: string; count: number; automated: number; human_reviewed: number }[];
  feature_importance?: { action: string; features: { name: string; weight: number }[] }[];
  architecture?: { 
    stages: { name: string; status: string; datasets?: string[] }[]; 
    drift_gate_note?: string;
    storage_tiers?: {
      hot: string[];
      warm: string[];
      cold: string[];
      archive: string[];
    };
  };
  dq_results?: { file: string; is_acceptable: boolean; hard_failures: number; soft_warnings: number; hard_failures_list?: string[]; soft_warnings_list?: string[] }[];
  pending_approvals: DriftEvent[];
  quarantine_details?: QuarantineItem[];
  dataset_overview?: Record<string, { rows: number; cols: string[] }>;
  csv_previews?: Record<string, {
    layer: string;
    file: string;
    rows_total: number;
    columns: string[];
    preview: Record<string, any>[];
  }>;
}

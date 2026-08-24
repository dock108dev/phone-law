export type DemoPrincipal = "demo-reviewer" | "demo-admin" | "demo-operations";

export type Evidence = {
  segment_id: string;
  start_seconds: number;
  end_seconds: number;
  speaker: string;
  excerpt: string;
};

export type ReportItem = {
  item_id: string;
  call_id: string;
  synthetic_reference: string;
  analysis_id: string | null;
  section: string;
  summary: string;
  category: string | null;
  priority: string;
  confidence: string | null;
  responsible_role: string | null;
  suggested_timing: string | null;
  evidence: Evidence[];
  failure: {
    failed_stage: string;
    diagnostic_code: string;
    retryable: boolean;
    terminal_state: string;
  } | null;
};

export type DailyReport = {
  report_id: string;
  business_date: string;
  timezone: string;
  cutoff_at: string;
  version: number;
  advisory_notice: string;
  completeness: {
    status: "complete" | "partial" | "failed" | "zero_activity";
    explanation: string;
    reconciliation: {
      expected: number;
      received: number;
      duplicate_deliveries: number;
      analyzed: number;
      failed: number;
      missing: number;
      late: number;
    };
  };
  sections: {
    kind: string;
    title: string;
    description: string;
    items: ReportItem[];
  }[];
  late_calls: {
    call_id: string;
    synthetic_reference: string;
    received_at: string;
  }[];
};

export type MonthHistory = {
  schema_version: "month-history-v1";
  year: number;
  month: number;
  label: string;
  synthetic: true;
  previous_month_path: string;
  next_month_path: string;
  days: {
    business_date: string;
    weekday: boolean;
    state: "complete" | "partial" | "failed" | "missing" | "zero_activity";
    report_status: "complete" | "partial" | "failed" | "zero_activity";
    expected: number;
    received: number;
    analyzed: number;
    failed: number;
    missing: number;
    late: number;
    duplicate_deliveries: number;
    scenarios: string[];
    report_path: string;
  }[];
};

export type ReviewEvent = {
  event_id: string;
  analysis_id: string;
  finding_id: string | null;
  label: string;
  note: string | null;
  principal: { principal_id: DemoPrincipal; role: string };
  created_at: string;
};

export type TranscriptSegment = {
  segment_id: string;
  speaker: string;
  start_seconds: number;
  end_seconds: number;
  text: string;
};

export type Finding = {
  finding_id: string;
  kind: string;
  statement: string;
  material: boolean;
  evidence: Evidence[];
};

export type CallDetail = {
  call_id: string;
  synthetic_reference: string;
  synthetic: true;
  occurred_at: string;
  direction: string;
  duration_seconds: number;
  staff_extension: string | null;
  language: "en" | "es";
  identity_state: string;
  identity_label: string | null;
  transcript_id: string;
  transcript_segments: TranscriptSegment[];
  analysis_id: string;
  summary: string;
  category: string;
  priority: string;
  confidence: string;
  uncertainty: string[];
  facts: {
    caller_request: { state: string; value: string | null; evidence: Evidence[] };
    reported_facts: { state: string; value: string | null; evidence: Evidence[] }[];
    dates: {
      state: string;
      expression: string | null;
      iso_date: string | null;
      is_deadline: boolean;
      evidence: Evidence[];
    }[];
    staff_commitments: {
      state: string;
      commitment: string | null;
      responsible_role: string;
      evidence: Evidence[];
    }[];
    missing_context: string[];
  };
  findings: Finding[];
  proposed_next_steps: string[];
  responsible_role: string;
  suggested_response_timing: string | null;
  provenance: Record<string, unknown>;
  attempts: {
    attempt_id: string;
    attempt_number: number;
    state: string;
    diagnostic_code: string | null;
    retryable: boolean | null;
    started_at: string;
    completed_at: string | null;
  }[];
  review_history: ReviewEvent[];
};

export type FailureQueue = {
  current: FailureItem[];
  resolved: FailureItem[];
};

export type FailureItem = {
  call_id: string;
  synthetic_reference: string;
  failed_stage: string;
  diagnostic_code: string;
  retryable: boolean;
  first_attempt_at: string;
  latest_attempt_at: string;
  attempt_count: number;
  current_terminal_state: string;
  resolved: boolean;
  attempt_history: {
    attempt_id: string;
    attempt_number: number;
    state: string;
    diagnostic_code: string | null;
    retryable: boolean | null;
  }[];
};

export type Playbook = {
  playbook_id: string;
  version: string;
  label: string;
  synthetic: true;
  lifecycle: "draft" | "published" | "retired";
  categories: string[];
  key_rules: string[];
  created_at: string;
  published_at: string | null;
};

export type PlaybookDraftCreate = {
  version: string;
  label: string;
  source_version: string;
};

export type UploadState =
  | "received"
  | "validating"
  | "ready"
  | "processing"
  | "analyzed"
  | "validation_failed"
  | "transcription_failed"
  | "analysis_failed"
  | "cancelled"
  | "deletion_failed";

export type UploadReceipt = {
  schema_version: "manual-upload-v1";
  upload_id: string;
  source_event_id: string;
  call_id: string | null;
  submission_kind: "synthetic_audio" | "transcript_only";
  synthetic: true;
  content_hash_reference: string;
  language_hint: "en" | "es";
  direction: "inbound" | "outbound" | "unknown";
  captured_at: string;
  staff_extension: string;
  principal_id: DemoPrincipal;
  role: "reviewer" | "administrator" | "operations";
  state: UploadState;
  attempt_number: number;
  diagnostic_code: string | null;
  retryable: boolean;
  deletion_confirmed: boolean | null;
  validation: {
    kind: "synthetic_audio" | "transcript_only";
    contract_version: string;
    byte_size: number;
    duration_seconds: number;
    media_format: string | null;
    channel_count: number | null;
    sample_rate_hz: number | null;
    segment_count: number | null;
  };
  created_at: string;
  updated_at: string;
  cancelled_at: string | null;
  deleted_at: string | null;
  duplicate: boolean;
  call_path: string | null;
  report_path: string | null;
  history: {
    event_id: string;
    state: UploadState;
    attempt_number: number;
    diagnostic_code: string | null;
    occurred_at: string;
  }[];
};

export type UploadCapabilities = {
  principal_id: DemoPrincipal;
  role: "reviewer" | "administrator" | "operations";
  can_open_completed: boolean;
  can_append_feedback: boolean;
  can_submit: boolean;
  can_view_receipts: boolean;
  can_retry: boolean;
  can_cancel: boolean;
  can_publish_playbook: boolean;
};

export type LocalRetention = {
  generated_media_days: number;
  invented_transcript_days: number;
  accepted_analysis_days: number;
  daily_report_days: number;
  processing_attempt_days: number;
  manual_upload_receipt_days: number;
  reviewer_feedback_days: number;
  playbook_version_days: number;
  audit_metadata_days: number;
};

export type LocalConfiguration = {
  schema_version: "local-firm-configuration-v1";
  firm_timezone: "America/New_York";
  daily_report_cutoff: string;
  eligible_call_directions: string[];
  eligible_call_categories: string[];
  staff_extension_mappings: { extension: string; synthetic_label: string }[];
  report_roles: ("reviewer" | "administrator" | "operations")[];
  synthetic_playbook_version: string;
  retention: LocalRetention;
  deletion_behavior: "scheduled_content_destruction_with_tombstone";
  notification_preference: "local_preview_noop";
};

export type ConfigurationVersion = {
  configuration_id: string;
  version: number;
  configuration: LocalConfiguration;
  principal: { principal_id: DemoPrincipal; role: string };
  content_hash_reference: string;
  created_at: string;
};

export type ConfigurationHistory = {
  current_version: number;
  versions: ConfigurationVersion[];
};

export type OperationsOverview = {
  environment: "Local development";
  data_label: "Synthetic demo data";
  configuration_version: number;
  processing_volume: { state: string; count: number }[];
  processing_latency: {
    completed_attempts: number;
    average_milliseconds: number;
    maximum_milliseconds: number;
  };
  success_count: number;
  failure_count: number;
  retry_count: number;
  reconciliation: {
    available: boolean;
    expected: number;
    received: number;
    analyzed: number;
    failed: number;
    missing: number;
    exact: boolean;
  };
  pending_deletions: number;
  failed_deletions: number;
  retention_policy_status: string;
  backup_restore_status: string;
  last_successful_maintenance_at: string | null;
  failure_explanations: string[];
  permitted_actions: string[];
  external_requests: 0;
};

export type DeletionJob = {
  job_id: string;
  resource_type: string;
  resource_id: string;
  configuration_version: number;
  state: "SCHEDULED" | "DELETING" | "RETRY_SCHEDULED" | "DELETED" | "DELETION_FAILED" | "RETAINED_EXCEPTION";
  attempt_count: number;
  diagnostic_code: string | null;
  scheduled_at: string;
  next_attempt_at: string | null;
  completed_at: string | null;
};

export type AuditEvent = {
  event_id: string;
  principal: { principal_id: DemoPrincipal; role: string };
  action: string;
  target_type: string;
  target_id: string;
  result: string;
  created_at: string;
};

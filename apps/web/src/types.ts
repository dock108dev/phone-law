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
    status: "complete" | "partial" | "failed";
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
  provenance: Record<string, string>;
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

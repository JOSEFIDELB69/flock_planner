export type Priority = "low" | "medium" | "high" | "critical";
export type Confidence = "low" | "medium" | "high";

export interface CalendarConfig {
  working_days: number[];
  hours_per_day: number;
  holidays: string[];
}

export interface Project {
  id: number;
  name: string;
  description: string;
  business_objective: string;
  owner: string;
  target_date: string | null;
  timezone: string;
  calendar_configuration: CalendarConfig;
  mode: "standalone" | "jira";
  currency: string;
  status: "draft" | "active" | "archived";
  active_plan_version_id: number | null;
  created_at: string;
  updated_at: string;
  requirement_count: number;
  epic_count: number;
  story_count: number;
  task_count: number;
  total_hours: number;
  has_baseline: boolean;
  export_count: number;
  active_version_number: number | null;
  estimated_completion_date: string | null;
  estimated_duration: number | null;
}

export interface Requirement {
  id: number;
  project_id: number;
  code: string;
  title: string;
  description: string;
  type: string;
  priority: Priority;
  source: string;
  status: string;
  group_name: string;
  assumptions: string;
  risks: string;
  duplicate_of_id: number | null;
  source_document_id: number | null;
  related_ids: number[];
  depends_on_ids: number[];
  created_at: string;
  updated_at: string;
}

export interface ClarificationQuestion {
  question: string;
  why_it_matters: string;
  impact: "low" | "medium" | "high";
}

export interface SuggestedRequirement {
  title: string;
  description: string;
  type: string;
  priority: Priority;
  rationale: string;
}

export interface AnalysisResult {
  summary: string;
  objectives: string[];
  actors: string[];
  functionalities: string[];
  constraints: string[];
  non_functional: string[];
  integrations: string[];
  dependencies: string[];
  ambiguities: string[];
  risks: string[];
  missing_information: string[];
  clarification_questions: ClarificationQuestion[];
  suggested_requirements: SuggestedRequirement[];
}

export interface Analysis {
  id: number;
  project_id: number;
  result: AnalysisResult;
  answers: Record<string, string>;
  proceed_with_assumptions: boolean;
  is_simulated: boolean;
  model: string;
  created_at: string;
  created_by: string;
}

export interface AcceptanceCriterion {
  given: string;
  when: string;
  then: string;
}

export interface Task {
  id: number;
  story_id: number;
  code: string;
  title: string;
  description: string;
  category: string;
  profile_key: string;
  estimated_hours: number;
  optimistic_hours: number | null;
  pessimistic_hours: number | null;
  original_estimate_hours: number;
  estimate_status: "initial" | "revised";
  done_criteria: string;
  risks: string;
  status: string;
  depends_on_ids: number[];
}

export interface Story {
  id: number;
  epic_id: number;
  code: string;
  title: string;
  description: string;
  acceptance_criteria: AcceptanceCriterion[];
  priority: Priority;
  business_value: number;
  assumptions: string;
  risks: string;
  estimate_confidence: Confidence;
  estimate_status: "initial" | "revised";
  status: string;
  depends_on_ids: number[];
  tasks: Task[];
  hours_by_profile: Record<string, number>;
  total_hours: number;
}

export interface Epic {
  id: number;
  project_id: number;
  code: string;
  title: string;
  description: string;
  priority: Priority;
  status: string;
  source: string;
  stories: Story[];
  total_hours: number;
}

export interface Backlog {
  project_id: number;
  epics: Epic[];
  total_hours: number;
  hours_by_profile: Record<string, number>;
  story_count: number;
  task_count: number;
  is_simulated: boolean;
  warnings?: string[];
  assumptions?: string[];
}

export type SeniorityLevel = "sr" | "ssr" | "jr";
export type SeniorityMix = Record<SeniorityLevel, number>;

export interface MemberAvailability {
  name: string;
  availability_percentage: number;
  hours_per_day: number | null;
  absences: { start: string; end: string }[];
}

export interface TeamProfile {
  id?: number;
  profile_key: string;
  profile_name: string;
  quantity: number;
  available_hours_per_day: number;
  dedication_percentage: number;
  hourly_rate: number | null;
  is_qa: boolean;
  availability_configuration: { members: MemberAvailability[]; seniority?: SeniorityMix | null };
}

export interface ProfileMetrics {
  profile_key: string;
  profile_name: string;
  is_qa: boolean;
  members: number;
  quantity: number;
  daily_capacity: number;
  base_hours: number;
  planned_hours: number;
  available_hours: number;
  utilization: number;
  avg_wait_days: number;
  max_wait_days: number;
  hourly_rate: number | null;
  cost: number | null;
  staffing_hours: number;
  staffing_cost: number | null;
}

export interface ScheduledTask {
  task_id: string;
  title: string;
  story_id: string;
  story_title: string;
  epic_id: string;
  epic_title: string;
  profile_key: string;
  member_id: string;
  member_name: string;
  seniority?: SeniorityLevel | null;
  seniority_pct?: number;
  base_hours: number;
  effective_hours: number;
  ready: number;
  start: number;
  finish: number;
  start_date: string;
  end_date: string;
  wait_days: number;
  depends_on: string[];
}

export interface Bottleneck {
  profile_key: string;
  profile_name: string;
  critical_share: number;
  utilization: number;
  score: number;
  reasons: string[];
}

export interface Risk {
  title: string;
  severity: "low" | "medium" | "high";
  detail: string;
  source?: string;
}

export interface Milestone {
  name: string;
  date: string;
  type: string;
}

export interface CriticalStep {
  task_id: string;
  title: string;
  profile_key: string;
  member_name: string;
  start_date: string;
  end_date: string;
  effective_hours: number;
  constraint: "dependency" | "resource" | "start";
}

export type Uncertainty = Record<Confidence, [number, number]>;

export interface ForecastPoint {
  working_days: number;
  date: string;
}

export interface Forecast {
  method: "monte_carlo";
  runs: number;
  seed: number;
  correlation: number;
  uncertainty: Uncertainty;
  tasks_with_own_range: number;
  base_hours_range: [number, number, number];
  p50: ForecastPoint;
  p80: ForecastPoint;
  p90: ForecastPoint;
  min_working_days: number;
  max_working_days: number;
  mean_working_days: number;
  probability_work_only: number;
  probability_plan: number;
  probability_target: number | null;
  contingency_for_p80_pct: number;
  curve: (ForecastPoint & { probability: number })[];
}

export interface PlanMetrics {
  start_date: string;
  completion_date: string;
  duration_working_days: number;
  calendar_days: number;
  work_duration_days?: number;
  work_completion_date?: string;
  contingency_pct?: number;
  contingency_days?: number;
  base_effort_hours: number;
  planned_effort_hours: number;
  total_cost: number | null;
  total_staffing_cost: number | null;
  by_profile: ProfileMetrics[];
  by_member: { member_id: string; name: string; profile_key: string; daily_capacity: number; assigned_hours: number; available_hours: number; utilization: number }[];
  by_epic: { epic_id: string; title: string; base_hours: number; planned_hours: number; start_date: string | null; end_date: string }[];
  critical_path: CriticalStep[];
  milestones: Milestone[];
  bottlenecks: Bottleneck[];
  main_bottleneck: string | null;
  assumptions: string[];
  risks: Risk[];
  target_date: string | null;
  meets_target: boolean | null;
  schedule?: ScheduledTask[];
  forecast?: Forecast | null;
}

export interface PlanningParameters {
  start_date: string;
  working_days: number[];
  holidays: string[];
  review_overhead_pct: number;
  rework_pct: number;
  coordination_overhead_pct: number;
  qa_after_dev: boolean;
  contingency_pct?: number;
  seniority_factors?: SeniorityMix;
  uncertainty?: Uncertainty;
}

export interface PlanVersionSummary {
  id: number;
  version_number: number;
  label: string;
  is_baseline: boolean;
  is_active: boolean;
  source_scenario_id: number | null;
  estimated_effort: number;
  estimated_duration: number;
  start_date: string;
  estimated_completion_date: string;
  change_reason: string;
  created_at: string;
  created_by: string;
  main_bottleneck: string | null;
  total_cost: number | null;
}

export interface PlanVersion extends PlanVersionSummary {
  project_id: number;
  restored_from_version_id: number | null;
  team_configuration: TeamProfile[];
  planning_parameters: PlanningParameters;
  metrics: PlanMetrics;
  schedule: ScheduledTask[];
  backlog_snapshot: { epics: unknown[]; requirements: unknown[] };
  assumptions: string[];
  risks: Risk[];
  executive_summary: string;
  executive_summary_simulated: boolean;
}

export interface PlanPreview {
  is_preview: true;
  team_configuration: TeamProfile[];
  planning_parameters: PlanningParameters;
  result: PlanMetrics & { schedule: ScheduledTask[] };
}

export interface CapacityChange {
  profile_key: string;
  profile_name: string;
  baseline_quantity: number;
  scenario_quantity: number;
  quantity_delta: number;
  baseline_daily_capacity: number;
  scenario_daily_capacity: number;
  daily_capacity_delta: number;
  baseline_utilization: number;
  scenario_utilization: number;
}

export interface ComparisonMetrics {
  baseline_duration: number;
  scenario_duration: number;
  time_savings_days: number;
  variation_pct: number;
  baseline_completion_date: string;
  scenario_completion_date: string;
  completion_delta_calendar_days: number;
  baseline_effort: number;
  scenario_effort: number;
  effort_delta: number;
  baseline_cost: number | null;
  scenario_cost: number | null;
  cost_delta: number | null;
  baseline_staffing_cost: number | null;
  scenario_staffing_cost: number | null;
  staffing_cost_delta: number | null;
  added_people: number;
  baseline_contingency_pct?: number;
  scenario_contingency_pct?: number;
  baseline_contingency_days?: number;
  scenario_contingency_days?: number;
  scenario_work_duration?: number;
  capacity_changes: CapacityChange[];
  baseline_main_bottleneck: string | null;
  scenario_main_bottleneck: string | null;
  baseline_version_id: number;
  baseline_version_number: number;
  profiles_without_gain?: string[];
  baseline_p80?: ForecastPoint | null;
  scenario_p80?: ForecastPoint | null;
  baseline_probability_plan?: number | null;
  scenario_probability_plan?: number | null;
}

export interface Scenario {
  id: number;
  project_id: number;
  base_version_id: number;
  name: string;
  description: string;
  source: "manual" | "suggested";
  team_configuration: TeamProfile[];
  planning_parameters: PlanningParameters;
  results: (PlanMetrics & { schedule: ScheduledTask[] }) | null;
  estimated_effort: number | null;
  estimated_duration: number | null;
  estimated_completion_date: string | null;
  comparison_metrics: ComparisonMetrics | null;
  status: "draft" | "simulated" | "applied" | "stale" | "error";
  error_message: string;
  applied_version_id: number | null;
  created_at: string;
  simulated_at: string | null;
}

export interface ExportItem {
  id: number;
  project_id: number;
  plan_version_id: number;
  report_type: "full" | "executive" | "optimization";
  filename: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
  created_by: string;
}

export interface AuditEntry {
  id: number;
  entity_type: string;
  entity_id: number | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string;
  actor: string;
  created_at: string;
}

export interface SystemStatus {
  app_env: string;
  database: string;
  database_ok: boolean;
  ai_demo_mode: boolean;
  ai_provider: "claude_code" | "demo" | null;
  ai_model: string;
  ai_available: boolean;
  secrets_encryption_configured: boolean;
  version: string;
}

export interface JiraConfig {
  project_id: number;
  enabled: boolean;
  configuration_status: "not_configured" | "configured" | "validated" | "error";
  site_url: string;
  auth_method: string;
  account_email: string;
  has_secret: boolean;
  last_validated_at: string | null;
  last_error: string;
  project_mode: "standalone" | "jira";
}

export interface JiraPreviewItem {
  local_type: "epic" | "story" | "task";
  local_id: number;
  code: string;
  summary: string;
  description: string;
  parent_code: string | null;
  estimated_hours?: number;
  existing_key: string | null;
}

export interface JiraRemoteProject {
  key: string;
  name: string;
  type: string;
  style: string;
}

export interface JiraIssueType {
  id: string;
  name: string;
  subtask: boolean;
  hierarchy_level: number;
}

export interface JiraPreview {
  project_key: string;
  issue_type_mapping: { epic: string; story: string; task: string };
  items: JiraPreviewItem[];
  counts: Record<string, number>;
  already_published: number;
  pending_fields: string[];
  remote_duplicates: { key: string; summary: string }[];
  fingerprint: string;
  can_publish: boolean;
}

export interface BacklogObservation {
  id: number;
  project_id: number;
  kind: "assumption" | "warning";
  text: string;
  position: number;
  status: "pending" | "accepted" | "correction";
  correction: string;
  links: { type: "requirement" | "story" | "task" | "epic"; id?: number; code: string }[];
  created_at: string;
  resolved_at: string | null;
  resolved_by: string;
}

export interface ProjectDocument {
  id: number;
  project_id: number;
  filename: string;
  kind: "pdf" | "docx" | "text";
  size_bytes: number;
  status: "pending" | "processing" | "processed" | "error";
  error: string;
  summary: string;
  requirements_created: number;
  ai_model: string;
  is_simulated: boolean;
  created_at: string;
  created_by: string;
  processed_at: string | null;
}

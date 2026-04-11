const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export async function fetchAPI<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export async function postAPI<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `API ${res.status}: ${path}`);
  }
  return res.json();
}

export async function putAPI<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `API ${res.status}: ${path}`);
  }
  return res.json();
}

export async function deleteAPI<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `API ${res.status}: ${path}`);
  }
  return res.json();
}

// ---- Types ----

export interface Problem {
  id: string;           // "01-rate-limiter"，即目录名
  title: string;
  difficulty: string;
  language: string;
  tags: string[];
  description?: string;
  scoring: Record<string, number>;
  concurrent?: boolean;
}

export interface Provider {
  uuid: string;
  name: string;
  api_format: string;   // "openai" | "anthropic"
  api_key_masked: string;
  base_url: string;
}

export interface ModelConfig {
  uuid: string;
  provider_uuid: string;
  provider_name: string;
  model_id: string;
  api_format: string;
  thinking: boolean;
  thinking_budget: number;
  enabled: boolean;
  max_tokens: number;
}

// 用于评测轮次选择的简化模型信息
export interface ModelSelectItem {
  uuid: string;
  provider_name: string;
  model_id: string;
  thinking: boolean;
}

export interface LeaderboardEntry {
  model_uuid: string;
  provider: string;     // provider_name
  model: string;        // model_id
  thinking: boolean;
  total_problems: number;
  total_score: number;
  completed: number;
  avg_score: number;
}

export interface ScoreBreakdown {
  compile?: number;
  tests?: number;
  safety?: number;
  quality?: number;
  resource?: number;
  performance?: number;
}

export interface EvalResult {
  compile_success: boolean;
  compile_warnings: number;
  compile_errors: string;
  compile_tsan_success: boolean;
  compile_asan_success: boolean;
  tests_passed: number;
  tests_total: number;
  test_output: string;
  tsan_issues: number;
  tsan_output: string;
  asan_issues: number;
  asan_output: string;
  clang_tidy_errors: number;
  clang_tidy_warnings: number;
  dangerous_apis: number;
  max_cyclomatic: number;
  avg_cyclomatic: number;
  max_func_length: number;
  total_loc: number;
  comment_ratio: number;
  valgrind_leaks: number;
  helgrind_issues: number;
  exec_time_ms: number;
  score_compile: number;
  score_tests: number;
  score_safety: number;
  score_resource: number;
  score_quality: number;
  score_performance: number;
  score_total: number;
  error: string;
  timed_out: boolean;
}

export interface GenerationToolCall {
  tool: string;
  file?: string;
  size?: number;
  compile_success?: boolean;
  test_success?: boolean;
  submitted?: boolean;
}

export interface GenerationRound {
  round: number;
  time: number;
  tool_calls: GenerationToolCall[];
  thinking?: string;
  output?: string;
  note?: string;
}

export interface Submission {
  round_id: string;
  problem_id: string;
  model_uuid: string;
  status: string;
  agent_round: number;
  used_tool_call: boolean;
  generated_code: string;
  generation_history: GenerationRound[];
  generation_duration: number;
  token_usage: Record<string, number>;
  generation_error: string;
  eval_result: EvalResult | null;
  score_breakdown: ScoreBreakdown | null;
  total_score: number;
  created_at: string;
  finished_at: string | null;
  // 附加的 model 元信息（后端 join 后附上）
  model_name?: string;
  model_provider?: string;
  model_thinking?: boolean;
}

export interface GlobalLeaderboardEntry {
  model_uuid: string;
  provider: string;
  model: string;
  thinking: boolean;
  total_score: number;
  problems_attempted: number;
  avg_score: number;
  win_rate: number;
  total_submissions: number;
  total_tokens: number;
}

export interface ModelProblem {
  problem_id: string;
  title: string;
  best_score: number;
  worst_score: number;
  avg_score: number;
  submission_count: number;
  avg_tokens: { prompt: number; completion: number; total: number };
}

export interface ModelStats {
  model_uuid: string;
  provider: string;
  model: string;
  thinking: boolean;
  problems: ModelProblem[];
}

export interface SubmissionProgress {
  model_uuid: string;
  problem_id: string;
  status: string;
  agent_round: number;
  total_score: number;
}

export interface RoundProgress {
  round_status: string;
  submissions: SubmissionProgress[];
}

export interface RoundInfo {
  id: string;
  name: string;
  status: string;
  problem_ids: string[];
  model_uuids: string[];
  created_at: string;
  finished_at: string | null;
  leaderboard?: LeaderboardEntry[];
}

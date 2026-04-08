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

// Types
export interface Problem {
  uuid: string;
  slug: string;
  id: string;
  title: string;
  difficulty: string;
  language: string;
  tags: string[];
  description?: string;
  scoring: Record<string, number>;
}

// model_id in submissions/rounds is now model_uuid
export interface LeaderboardEntry {
  model_uuid: string;
  provider: string;
  model: string;
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
  concurrency?: number;  // 旧数据兼容
  memory?: number;       // 旧数据兼容
  quality?: number;
  resource?: number;
  performance?: number;
  efficiency?: number;   // 旧数据兼容
}

export interface EvalResult {
  compile_success: boolean;
  compile_warnings: number;
  compile_errors: string;
  tests_passed: number;
  tests_total: number;
  test_output: string;
  tsan_issues: number;
  tsan_output: string;
  asan_issues: number;
  asan_output: string;
  cppcheck_errors: number;
  cppcheck_warnings: number;
  max_cyclomatic: number;
  avg_cyclomatic: number;
  total_loc: number;
  error: string;
  timed_out: boolean;
}

export interface Submission {
  id: number;
  round_id: string;
  problem_id: string;
  model_uuid: string;
  status: string;
  generated_code: string;
  used_tool_call: boolean;
  generation_error: string;
  eval_result: EvalResult | null;
  total_score: number;
  score_breakdown: ScoreBreakdown | null;
  created_at: string;
  finished_at: string;
  token_usage?: Record<string, number>;
  generation_duration?: number;
  model_name?: string;
  model_provider?: string;
  model_thinking?: boolean;
  generation_history?: GenerationRound[];
}

export interface GenerationRound {
  round: number;
  time: number;
  tool_calls: GenerationToolCall[];
  thinking?: string;
  output?: string;
  text_preview?: string;
  note?: string;
}

export interface GenerationToolCall {
  tool: string;
  file?: string;
  size?: number;
  compile_success?: boolean;
  test_success?: boolean;
  submitted?: boolean;
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
  thinking: boolean;
  avg_tokens: { prompt: number; completion: number; total: number };
}

export interface ModelStats {
  model_uuid: string;
  provider: string;
  model: string;
  thinking: boolean;
  problems: ModelProblem[];
}

export interface RoundInfo {
  id: string;
  name: string;
  status: string;
  problem_ids: string[];
  model_uuids: string[];
  created_at: string;
  finished_at: string;
  leaderboard?: LeaderboardEntry[];
}


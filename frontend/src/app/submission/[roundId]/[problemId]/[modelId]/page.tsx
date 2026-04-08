"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Nav from "@/components/nav";
import ModelBadge from "@/components/model-badge";
import { fetchAPI, Submission, GenerationRound } from "@/lib/api";

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="flex items-center gap-3 mb-2">
      <span className="text-sm text-gray-400 w-20 shrink-0">{label}</span>
      <div className="flex-1 bg-gray-800 rounded h-5 overflow-hidden">
        <div
          className="bg-gradient-to-r from-cyan-500 to-blue-500 h-full rounded transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm font-mono text-gray-300 w-12 text-right">{value}</span>
    </div>
  );
}

function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`text-xs px-2 py-1 rounded ${ok ? "bg-green-800/50 text-green-300" : "bg-red-800/50 text-red-300"}`}>
      {label}: {ok ? "✓" : "✗"}
    </span>
  );
}

function CollapsibleThinking({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-purple-900/30 rounded-lg overflow-hidden mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-1.5 bg-purple-900/10 hover:bg-purple-900/20 transition-colors text-left"
      >
        <span className="text-purple-400 text-xs">💭 思考内容</span>
        <span className="text-gray-600 text-xs">{open ? "▼ 收起" : "▶ 展开"}</span>
      </button>
      {open && (
        <div className="px-3 py-2 bg-purple-900/5">
          <pre className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">{content}</pre>
        </div>
      )}
    </div>
  );
}

function ToolCallIcon({ tool }: { tool: string }) {
  switch (tool) {
    case "write_file": return "📝";
    case "compile": return "🔨";
    case "run_tests": return "🧪";
    case "submit": return "✅";
    case "read_file": return "📖";
    case "list_files": return "📂";
    default: return "🔧";
  }
}

function ToolBadge({ tc }: { tc: Record<string, unknown> }) {
  const tool = tc.tool as string;
  const success = tc.compile_success as boolean | undefined;
  const testSuccess = tc.test_success as boolean | undefined;
  const submitted = tc.submitted as boolean | undefined;
  const file = tc.file as string | undefined;
  const size = tc.size as number | undefined;

  let statusColor = "text-gray-400";
  if (success !== undefined) statusColor = success ? "text-green-400" : "text-red-400";
  if (testSuccess !== undefined) statusColor = testSuccess ? "text-green-400" : "text-red-400";
  if (submitted) statusColor = "text-cyan-400";

  return (
    <span className="inline-flex items-center gap-1 text-xs bg-gray-800 px-2 py-0.5 rounded">
      <ToolCallIcon tool={tool} />
      <span className="text-gray-400">{tool}</span>
      {file && <span className="text-gray-500">{file}</span>}
      {size && <span className="text-gray-600">({size}B)</span>}
      <span className={statusColor}>
        {submitted ? "提交" : success !== undefined ? (success ? "✓" : "✗") : testSuccess !== undefined ? (testSuccess ? "✓" : "✗") : ""}
      </span>
    </span>
  );
}

function GenerationProcess({ history }: { history: GenerationRound[] }) {
  if (!history || history.length === 0) {
    return <p className="text-gray-500 text-sm">无生成记录</p>;
  }

  return (
    <div className="space-y-3">
      {history.map((round) => {
        // 兼容旧格式 text_preview 和新格式 thinking/output
        const thinking = round.thinking || "";
        const output = round.output || "";
        const oldText = round.text_preview || "";
        const note = round.note || "";

        // 新格式直接用 thinking/output
        // 旧格式（只有 text_preview）整体当输出，不拆分
        const displayThinking = thinking || "";
        const displayOutput = output || oldText || "";

        return (
          <div key={round.round} className="border border-gray-800 rounded-lg overflow-hidden">
            {/* Round header: 编号 + 耗时 */}
            <div className="flex items-center gap-3 px-4 py-2 bg-gray-900/80">
              <span className="text-xs font-mono text-cyan-400">Round {round.round}</span>
              <span className="text-xs text-gray-600">{round.time.toFixed(1)}s</span>
              {note && <span className="text-xs text-yellow-500 ml-auto">{note}</span>}
            </div>

            <div className="px-4 py-2 space-y-2">
              {/* 新格式：thinking + output 分开 */}
              {displayThinking && (
                <CollapsibleThinking content={displayThinking} />
              )}
              {displayOutput && (
                <pre className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">{displayOutput}</pre>
              )}

              {/* 工具调用（在下面） */}
              {round.tool_calls && round.tool_calls.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {round.tool_calls.map((tc, i) => (
                    <ToolBadge key={i} tc={tc as Record<string, unknown>} />
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function SubmissionPage() {
  const params = useParams();
  const roundId = params.roundId as string;
  const problemId = params.problemId as string;
  const encodedModelId = params.modelId as string;
  const modelUuid = encodedModelId || "";
  const [sub, setSub] = useState<Submission | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAPI<Submission>(`/api/submissions/${roundId}/${problemId}/${modelUuid}`)
      .then((data) => { setSub(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [roundId, problemId, modelUuid]);

  if (loading) return <><Nav /><main className="max-w-7xl mx-auto px-4 py-12"><p className="text-gray-500">加载中...</p></main></>;
  if (!sub) return <><Nav /><main className="max-w-7xl mx-auto px-4 py-12"><p className="text-gray-500">未找到提交</p></main></>;

  const sb = sub.score_breakdown;
  const ev = sub.eval_result;

  return (
    <>
      <Nav />
      <main className="max-w-7xl mx-auto px-4 py-12">
        <div className="mb-8">
          <div className="flex items-center gap-1 mb-2">
            <span className="text-2xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              {sub.model_name || modelUuid.slice(0, 8)}
            </span>
            <ModelBadge model="" provider={sub.model_provider || ""} thinking={sub.model_thinking} />
          </div>
          <p className="text-gray-400">
            {sub.problem_id} · {sub.status}
          </p>
        </div>

        {/* Generation Process */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-3">🔄 生成过程</h2>
          <GenerationProcess history={sub.generation_history || []} />
        </section>

        {/* Code */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-3">📝 生成的代码</h2>
          <pre className="bg-gray-900 border border-gray-800 rounded-xl p-6 overflow-x-auto text-sm text-gray-300 leading-relaxed max-h-96">
            <code>{sub.generated_code}</code>
          </pre>
        </section>

        {/* Eval Result */}
        {ev && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold mb-3">🔍 评测结果</h2>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-3">
              <div className="flex flex-wrap gap-3">
                <Badge ok={ev.compile_success} label="编译" />
                <Badge ok={ev.tsan_issues === 0} label="TSan" />
                <Badge ok={ev.asan_issues === 0} label="ASan" />
              </div>
              <div className="text-sm text-gray-400 space-y-1">
                <p>编译警告: <span className="text-white font-mono">{ev.compile_warnings}</span></p>
                <p>测试通过: <span className="text-white font-mono">{ev.tests_passed}/{ev.tests_total}</span></p>
                <p>TSan issues: <span className="text-white font-mono">{ev.tsan_issues}</span></p>
                <p>ASan issues: <span className="text-white font-mono">{ev.asan_issues}</span></p>
                <p>代码行数: <span className="text-white font-mono">{ev.total_loc}</span></p>
                <p>最大圈复杂度: <span className="text-white font-mono">{ev.max_cyclomatic}</span></p>
                {sub.token_usage && (
                  <p>Token 用量: <span className="text-white font-mono">
                    {sub.token_usage.prompt_tokens} / {sub.token_usage.completion_tokens} / {sub.token_usage.total_tokens}
                  </span> <span className="text-gray-500">(prompt / completion / total)</span></p>
                )}
                {sub.generation_duration != null && (
                  <p>生成耗时: <span className="text-white font-mono">{sub.generation_duration.toFixed(1)}s</span></p>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Score Breakdown */}
        {sb && (
          <section>
            <h2 className="text-lg font-semibold mb-3">📊 评分明细</h2>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <Bar label="编译" value={sb.compile ?? 0} max={10} />
              <Bar label="功能" value={sb.tests ?? 0} max={25} />
              <Bar label="安全性" value={(sb.safety ?? sb.concurrency ?? 0)} max={25} />
              <Bar label="代码质量" value={sb.quality ?? 0} max={15} />
              <Bar label="资源管理" value={(sb.resource ?? sb.memory ?? 0)} max={15} />
              <Bar label="性能" value={sb.performance ?? 0} max={10} />
              <div className="mt-4 pt-4 border-t border-gray-800 flex items-center gap-3">
                <span className="text-sm text-gray-400">总分</span>
                <span className="text-2xl font-bold text-cyan-400 font-mono">{sub.total_score}</span>
              </div>
            </div>
          </section>
        )}
      </main>
    </>
  );
}

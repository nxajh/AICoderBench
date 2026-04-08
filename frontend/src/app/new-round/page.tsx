"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import Nav from "@/components/nav";
import ModelBadge from "@/components/model-badge";
import type { Problem, RoundInfo, Submission } from "@/lib/api";

// 模型选择项类型（来自 /api/models 返回）
interface ModelSelectItem {
  uuid: string;
  provider: string;
  api_model: string;
  thinking: boolean;
}

interface RoundDetail extends RoundInfo {
  submissions: Submission[];
}

export default function NewRoundPage() {
  const [problems, setProblems] = useState<Problem[]>([]);
  const [models, setModels] = useState<ModelSelectItem[]>([]);
  const [selectedProblems, setSelectedProblems] = useState<Set<string>>(new Set());
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [roundName, setRoundName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [activeRoundId, setActiveRoundId] = useState<string | null>(null);
  const [roundDetail, setRoundDetail] = useState<RoundDetail | null>(null);
  const [error, setError] = useState("");
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    fetch("/api/problems").then(r => r.json()).then(setProblems).catch(console.error);
    fetch("/api/models").then(r => r.json()).then(setModels).catch(console.error);
  }, []);

  const toggleProblem = (id: string) => {
    setSelectedProblems(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleModel = (id: string) => {
    setSelectedModels(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectAllProblems = () => {
    if (selectedProblems.size === problems.length) {
      setSelectedProblems(new Set());
    } else {
      setSelectedProblems(new Set(problems.map(p => p.id)));
    }
  };

  const selectAllModels = () => {
    if (selectedModels.size === models.length) {
      setSelectedModels(new Set());
    } else {
      setSelectedModels(new Set(models.map(m => m.uuid)));
    }
  };

  const pollRound = useCallback(async (roundId: string) => {
    try {
      const res = await fetch(`/api/rounds/${roundId}`);
      const raw = await res.json();
      // API returns { round, submissions, leaderboard }
      const data: RoundDetail = raw.round ? { ...raw.round, submissions: raw.submissions ?? [] } : raw;
      setRoundDetail(data);
      if (data.status === "done" || data.status === "failed" || data.status === "cancelled") {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch {
      // ignore
    }
  }, []);

  const handleSubmit = async () => {
    if (selectedProblems.size === 0 || selectedModels.size === 0) {
      setError("请至少选择一道题目和一个模型");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch("/api/rounds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: roundName || undefined,
          problem_ids: Array.from(selectedProblems),
          model_uuids: Array.from(selectedModels),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || "创建失败");
        setSubmitting(false);
        return;
      }
      // Find the new round (latest one)
      const roundsRes = await fetch("/api/rounds");
      const rounds: RoundInfo[] = await roundsRes.json();
      const newRound = rounds.find(r => r.status === "running");
      if (newRound) {
        setActiveRoundId(newRound.id);
        await pollRound(newRound.id);
        pollRef.current = setInterval(() => pollRound(newRound.id), 3000);
      }
      setSubmitting(false);
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const statusIcon = (status: string) => {
    switch (status) {
      case "done": return "✅";
      case "failed": return "❌";
      case "running": case "generating": return "⏳";
      case "cancelled": return "🚫";
      default: return "⬜";
    }
  };

  const totalTasks = selectedProblems.size * selectedModels.size;

  return (
    <>
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-6">发起新评测</h1>

        {!activeRoundId ? (
          <>
            {/* Round Name */}
            <div className="mb-6">
              <label className="block text-sm text-gray-400 mb-2">轮次名称（可选）</label>
              <input
                type="text"
                value={roundName}
                onChange={e => setRoundName(e.target.value)}
                placeholder="例：GLM-5.1 vs MiniMax M2.7"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>

            {/* Model Selection */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold">选择模型</h2>
                <button
                  onClick={selectAllModels}
                  className="text-xs text-cyan-400 hover:text-cyan-300"
                >
                  {selectedModels.size === models.length ? "取消全选" : "全选"}
                </button>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {models.map(m => (
                  <button
                    key={m.uuid}
                    onClick={() => toggleModel(m.uuid)}
                    className={`rounded-lg border px-4 py-3 text-left transition-all ${
                      selectedModels.has(m.uuid)
                        ? "border-cyan-500 bg-cyan-500/10 text-cyan-400"
                        : "border-gray-700 bg-gray-900 text-gray-300 hover:border-gray-500"
                    }`}
                  >
                    <div className="font-medium"><ModelBadge model={m.api_model} provider={m.provider} thinking={m.thinking} /></div>
                  </button>
                ))}
              </div>
            </div>

            {/* Problem Selection */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold">选择题目</h2>
                <button
                  onClick={selectAllProblems}
                  className="text-xs text-cyan-400 hover:text-cyan-300"
                >
                  {selectedProblems.size === problems.length ? "取消全选" : "全选"}
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {problems.map(p => (
                  <button
                    key={p.id}
                    onClick={() => toggleProblem(p.id)}
                    className={`rounded-lg border px-4 py-3 text-left transition-all ${
                      selectedProblems.has(p.id)
                        ? "border-cyan-500 bg-cyan-500/10 text-cyan-400"
                        : "border-gray-700 bg-gray-900 text-gray-300 hover:border-gray-500"
                    }`}
                  >
                    <div className="font-medium text-sm">{p.id}</div>
                    <div className="text-xs text-gray-500 mt-1">{p.title} · {p.difficulty}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Submit */}
            <div className="border-t border-gray-800 pt-4">
              {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
              <div className="flex items-center gap-4">
                <span className="text-sm text-gray-400">
                  {selectedModels.size} 个模型 × {selectedProblems.size} 道题 = {totalTasks} 个任务
                </span>
                <button
                  onClick={handleSubmit}
                  disabled={submitting || totalTasks === 0}
                  className={`px-6 py-2 rounded-lg font-medium transition-all ${
                    submitting || totalTasks === 0
                      ? "bg-gray-700 text-gray-500 cursor-not-allowed"
                      : "bg-cyan-600 hover:bg-cyan-500 text-white"
                  }`}
                >
                  {submitting ? "启动中..." : "开始评测"}
                </button>
              </div>
            </div>
          </>
        ) : (
          /* Progress View */
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold">{roundDetail?.name || "评测进行中"}</h2>
                <p className="text-sm text-gray-400 mt-1">
                  {roundDetail?.model_uuids?.length ?? 0} 个模型 · {roundDetail?.problem_ids?.length ?? 0} 道题
                </p>
              </div>
              <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                roundDetail?.status === "running"
                  ? "bg-yellow-500/20 text-yellow-400"
                  : roundDetail?.status === "done"
                  ? "bg-green-500/20 text-green-400"
                  : "bg-gray-500/20 text-gray-400"
              }`}>
                {roundDetail?.status === "running" ? "运行中" : roundDetail?.status === "done" ? "已完成" : roundDetail?.status}
              </span>
            </div>

            {/* Progress bar */}
            {roundDetail?.submissions && (
              <div className="mb-6">
                {(() => {
                  const total = roundDetail.submissions.length;
                  const done = roundDetail.submissions.filter(s => s.status === "done" || s.status === "failed").length;
                  const pct = total > 0 ? Math.round(done / total * 100) : 0;
                  return (
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-gray-400">{done}/{total} 完成</span>
                        <span className="text-gray-400">{pct}%</span>
                      </div>
                      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-cyan-500 transition-all duration-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Submission grid */}
            <div className="space-y-2">
              {roundDetail?.submissions
                .sort((a, b) => a.problem_id.localeCompare(b.problem_id) || a.model_uuid.localeCompare(b.model_uuid))
                .map(s => (
                <div key={`${s.model_uuid}-${s.problem_id}`}
                  className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900/50 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className="text-lg">{statusIcon(s.status)}</span>
                    <div>
                      <span className="text-sm font-medium">{s.problem_id}</span>
                      <span className="text-xs text-gray-500 mx-2">·</span>
                      <span className="text-xs text-gray-400">
                        {(() => {
                          const m = models.find(m => m.uuid === s.model_uuid);
                          return m ? <ModelBadge model={m.api_model} provider={m.provider} thinking={m.thinking} /> : s.model_uuid.slice(0, 8);
                        })()}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    {s.status === "done" && s.score_breakdown && (
                      <div className="hidden sm:flex gap-2 text-xs text-gray-500">
                        <span>编译{s.score_breakdown.compile}</span>
                        <span>测试{s.score_breakdown.tests}</span>
                        <span>并发{s.score_breakdown.concurrency}</span>
                        <span>内存{s.score_breakdown.memory}</span>
                      </div>
                    )}
                    <span className={`text-sm font-mono font-bold ${
                      s.status === "done" ? "text-cyan-400" : "text-gray-600"
                    }`}>
                      {s.status === "done" ? `${s.total_score}分` : s.status === "generating" ? "生成中..." : s.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Actions */}
            {roundDetail?.status === "done" && (
              <div className="mt-6 flex gap-4">
                {roundDetail.id && (
                  <Link href={`/rounds/${roundDetail.id}`}
                    className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm text-gray-300">
                    查看详情
                  </Link>
                )}
                <button onClick={() => { setActiveRoundId(null); setRoundDetail(null); }}
                  className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white">
                  发起新评测
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

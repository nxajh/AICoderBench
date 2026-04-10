"use client";

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import Nav from "@/components/nav";
import ModelBadge from "@/components/model-badge";
import { fetchAPI, Submission, LeaderboardEntry, RoundInfo, Problem, RoundProgress, SubmissionProgress } from "@/lib/api";
import Link from "next/link";

const STATUS_LABELS: Record<string, string> = {
  pending:    "等待中",
  generating: "生成中",
  generated:  "待评测",
  evaluating: "评测中",
  done:       "完成",
  failed:     "失败",
};

function StatusBadge({ status, agentRound }: { status: string; agentRound?: number }) {
  const base = "text-xs px-2 py-0.5 rounded font-mono flex items-center gap-1";
  const variants: Record<string, string> = {
    pending:    "bg-gray-800 text-gray-400",
    generating: "bg-cyan-900/60 text-cyan-300",
    generated:  "bg-yellow-900/50 text-yellow-300",
    evaluating: "bg-purple-900/50 text-purple-300",
    done:       "bg-green-900/50 text-green-300",
    failed:     "bg-red-900/50 text-red-300",
  };
  const isActive = status === "generating" || status === "evaluating";
  const label = STATUS_LABELS[status] ?? status;

  return (
    <span className={`${base} ${variants[status] ?? "bg-gray-800 text-gray-400"}`}>
      {isActive && (
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      )}
      {label}
      {status === "generating" && agentRound != null && agentRound > 0 && (
        <span className="text-gray-400 ml-0.5">R{agentRound}</span>
      )}
    </span>
  );
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-gray-400">总进度</span>
        <span className="text-sm text-gray-400 font-mono">{done} / {total} 完成 ({pct}%)</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function RoundDetailPage({ params }: { params: { id: string } }) {
  const [round, setRound] = useState<RoundInfo | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [progress, setProgress] = useState<SubmissionProgress[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterProblem, setFilterProblem] = useState<string>("all");
  const [problemMap, setProblemMap] = useState<Record<string, Problem>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetchAPI<Problem[]>("/api/problems")
      .then((list) => {
        const m: Record<string, Problem> = {};
        list.forEach((p) => { m[p.uuid] = p; });
        setProblemMap(m);
      })
      .catch(() => {});
  }, []);

  // Full data load
  const loadFull = useCallback(() => {
    return fetchAPI<{ round: RoundInfo; leaderboard: LeaderboardEntry[]; submissions: Submission[] }>(
      `/api/rounds/${params.id}`
    ).then((d) => {
      setRound(d.round);
      setLeaderboard(d.leaderboard);
      setSubmissions(d.submissions);
      // Sync progress from full data too
      setProgress(d.submissions.map((s) => ({
        model_uuid: s.model_uuid,
        problem_id: s.problem_id,
        status: s.status,
        agent_round: (s as unknown as Record<string, number>).agent_round ?? 0,
        total_score: s.total_score,
      })));
    });
  }, [params.id]);

  useEffect(() => {
    loadFull()
      .catch((e: Error) => { setError(e.message || "加载失败"); })
      .finally(() => setLoading(false));
  }, [loadFull]);

  // Lightweight progress polling when round is running
  useEffect(() => {
    if (!round) return;
    if (round.status !== "running") {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }

    const poll = () => {
      fetchAPI<RoundProgress>(`/api/rounds/${params.id}/progress`)
        .then((data) => {
          setProgress(data.submissions);
          // When round finishes, do one full reload to get scores + leaderboard
          if (data.round_status !== "running") {
            if (intervalRef.current) clearInterval(intervalRef.current);
            loadFull().catch(() => {});
          }
        })
        .catch(() => {});
    };

    intervalRef.current = setInterval(poll, 4000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [round?.status, params.id, loadFull]);

  // Build score matrix
  const { scoreMap, modelUuids } = useMemo(() => {
    const map: Record<string, Record<string, number>> = {};
    submissions.forEach((s) => {
      if (!map[s.model_uuid]) map[s.model_uuid] = {};
      map[s.model_uuid][s.problem_id] = s.total_score;
    });
    return { scoreMap: map, modelUuids: Object.keys(map) };
  }, [submissions]);

  // Progress lookup by model+problem
  const progressMap = useMemo(() => {
    const m: Record<string, SubmissionProgress> = {};
    progress.forEach((p) => { m[`${p.model_uuid}:${p.problem_id}`] = p; });
    return m;
  }, [progress]);

  const doneCount = progress.filter((p) => p.status === "done" || p.status === "failed").length;
  const totalCount = progress.length;

  const filtered = filterProblem === "all"
    ? submissions
    : submissions.filter((s) => s.problem_id === filterProblem);

  if (loading) return <><Nav /><div className="max-w-7xl mx-auto px-4 py-8 text-gray-400">加载中...</div></>;
  if (error) return <><Nav /><div className="max-w-7xl mx-auto px-4 py-8 text-red-400">加载失败：{error}</div></>;
  if (!round) return <><Nav /><div className="max-w-7xl mx-auto px-4 py-8 text-red-400">Round 不存在</div></>;

  const isRunning = round.status === "running";

  return (
    <>
      <Nav />
      <main className="max-w-7xl mx-auto px-4 py-12">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
            {round.name || round.id}
          </h1>
          <div className="flex items-center gap-3">
            <StatusBadge status={round.status} />
            <Link href="/new-round"
              className="px-3 py-1 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-xs text-white">
              + 新评测
            </Link>
          </div>
        </div>
        <p className="text-gray-500 text-sm mb-6">{round.created_at?.slice(0, 10)}</p>

        {/* Overall progress bar — shown while running */}
        {isRunning && totalCount > 0 && (
          <ProgressBar done={doneCount} total={totalCount} />
        )}

        {/* Live status grid — shown while running */}
        {isRunning && progress.length > 0 && (
          <section className="mb-10">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">实时进度</h2>
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-800 text-xs uppercase">
                    <th className="px-4 py-2 text-left">模型</th>
                    {round.problem_ids.map((pid) => (
                      <th key={pid} className="px-3 py-2 text-center">
                        {problemMap[pid]?.title ?? pid.slice(0, 8)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {round.model_uuids.map((muuid) => {
                    const entry = leaderboard.find((e) => e.model_uuid === muuid);
                    return (
                      <tr key={muuid} className="border-b border-gray-800/40">
                        <td className="px-4 py-2">
                          <ModelBadge model={entry?.model ?? muuid.slice(0, 8)} provider={entry?.provider ?? ""} thinking={entry?.thinking} />
                        </td>
                        {round.problem_ids.map((pid) => {
                          const p = progressMap[`${muuid}:${pid}`];
                          if (!p) return <td key={pid} className="px-3 py-2 text-center text-gray-700">—</td>;
                          return (
                            <td key={pid} className="px-3 py-2 text-center">
                              {p.status === "done" ? (
                                <span className={`font-mono text-xs ${p.total_score >= 80 ? "text-green-400" : p.total_score > 0 ? "text-gray-300" : "text-red-400"}`}>
                                  {p.total_score}
                                </span>
                              ) : (
                                <StatusBadge status={p.status} agentRound={p.agent_round} />
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Leaderboard */}
        {leaderboard.length > 0 && (
          <section className="mb-12">
            <h2 className="text-lg font-semibold mb-4">排行榜</h2>
            <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-gray-400 text-sm border-b border-gray-800">
                    <th className="px-6 py-3">模型</th>
                    <th className="px-6 py-3">总分</th>
                    <th className="px-6 py-3">已完成</th>
                    <th className="px-6 py-3">平均分</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.map((entry) => (
                    <tr key={entry.model_uuid} className="border-b border-gray-800/50 hover:bg-gray-800/50">
                      <td className="px-6 py-3">
                        <ModelBadge model={entry.model} provider={entry.provider} thinking={entry.thinking} />
                      </td>
                      <td className="px-6 py-3 text-cyan-400 font-mono">{entry.total_score}</td>
                      <td className="px-6 py-3 text-gray-400">{entry.completed}/{entry.total_problems}</td>
                      <td className="px-6 py-3 text-gray-400 font-mono">{entry.avg_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Filter */}
        <div className="flex gap-3 mb-4 flex-wrap">
          <button onClick={() => setFilterProblem("all")}
            className={`px-3 py-1 rounded text-sm ${filterProblem === "all" ? "bg-cyan-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}>
            全部
          </button>
          {round.problem_ids.map((pid) => (
            <button key={pid} onClick={() => setFilterProblem(pid)}
              className={`px-3 py-1 rounded text-sm ${filterProblem === pid ? "bg-cyan-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}>
              {problemMap[pid]?.title || "未知题目"}
            </button>
          ))}
        </div>

        {/* Score matrix (completed rounds) */}
        {!isRunning && (
          <section>
            <h2 className="text-lg font-semibold mb-4">评测详情</h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-gray-400 text-sm border-b border-gray-800">
                    <th className="px-6 py-3">模型 / 题目</th>
                    {round.problem_ids.map((pid) => (
                      <th key={pid} className="px-6 py-3 text-center">{problemMap[pid]?.title || pid.slice(0, 8)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {modelUuids.map((muuid) => {
                    const entry = leaderboard.find((e) => e.model_uuid === muuid);
                    return (
                      <tr key={muuid} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                        <td className="px-6 py-3">
                          <ModelBadge model={entry ? entry.model : "未知模型"} provider={entry?.provider || ""} thinking={entry?.thinking} />
                        </td>
                        {round.problem_ids.map((pid) => {
                          const score = scoreMap[muuid]?.[pid] ?? -1;
                          return (
                            <td key={pid} className="px-6 py-3 text-center">
                              {score < 0 ? (
                                <span className="text-gray-600">-</span>
                              ) : score === 0 ? (
                                <span className="text-red-400 font-mono">{score}</span>
                              ) : (
                                <span className={`font-mono ${score >= 80 ? "text-green-400" : "text-gray-300"}`}>{score}</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-8 grid gap-3">
              {filtered.map((s) => {
                const entry = leaderboard.find((e) => e.model_uuid === s.model_uuid);
                return (
                  <div key={s.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex items-center justify-between">
                    <div>
                      <ModelBadge model={entry ? entry.model : "未知模型"} provider={entry?.provider || ""} thinking={entry?.thinking} />
                      <span className="text-gray-500 text-sm ml-3">{problemMap[s.problem_id]?.title || "未知题目"}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className={`font-mono ${s.total_score >= 80 ? "text-green-400" : s.total_score > 0 ? "text-gray-300" : "text-red-400"}`}>
                        {s.total_score}
                      </span>
                      <StatusBadge status={s.status} />
                      <Link href={`/submission/${s.round_id}/${s.problem_id}/${s.model_uuid}`}
                        className="text-xs text-cyan-400 hover:underline">
                        详情
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </main>
    </>
  );
}

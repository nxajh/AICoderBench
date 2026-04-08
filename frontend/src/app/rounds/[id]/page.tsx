"use client";

import { useEffect, useState, useMemo } from "react";
import Nav from "@/components/nav";
import ModelBadge from "@/components/model-badge";
import { fetchAPI, Submission, LeaderboardEntry, RoundInfo, Problem } from "@/lib/api";
import Link from "next/link";

export default function RoundDetailPage({ params }: { params: { id: string } }) {
  const [round, setRound] = useState<RoundInfo | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterProblem, setFilterProblem] = useState<string>("all");
  const [problemMap, setProblemMap] = useState<Record<string, Problem>>({});

  useEffect(() => {
    fetchAPI<Problem[]>("/api/problems")
      .then((list) => {
        const m: Record<string, Problem> = {};
        list.forEach((p) => { m[p.uuid] = p; });
        setProblemMap(m);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchAPI<{ round: RoundInfo; leaderboard: LeaderboardEntry[]; submissions: Submission[] }>(
      `/api/rounds/${params.id}`
    )
      .then((d) => { setRound(d.round); setLeaderboard(d.leaderboard); setSubmissions(d.submissions); setLoading(false); })
      .catch((e: Error) => { setError(e.message || "加载失败"); setLoading(false); });
  }, [params.id]);

  if (loading) return <><Nav /><div className="max-w-7xl mx-auto px-4 py-8 text-gray-400">加载中...</div></>;

  if (error) return <><Nav /><div className="max-w-7xl mx-auto px-4 py-8 text-red-400">加载失败：{error}</div></>;

  if (!round) return <><Nav /><div className="max-w-7xl mx-auto px-4 py-8 text-red-400">Round 不存在</div></>;

  const filtered = filterProblem === "all"
    ? submissions
    : submissions.filter((s) => s.problem_id === filterProblem);

  // Build score matrix（useMemo 避免每次渲染重建）
  const { scoreMap, modelUuids } = useMemo(() => {
    const map: Record<string, Record<string, number>> = {};
    submissions.forEach((s) => {
      if (!map[s.model_uuid]) map[s.model_uuid] = {};
      map[s.model_uuid][s.problem_id] = s.total_score;
    });
    return { scoreMap: map, modelUuids: Object.keys(map) };
  }, [submissions]);

  return (
    <>
      <Nav />
      <main className="max-w-7xl mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold mb-2 bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
          {round.name || round.id}
        </h1>
        <p className="text-gray-500 text-sm mb-8">
          {round.status === "done" ? "已完成" : round.status} · {round.created_at?.slice(0, 10)}
        </p>

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
              {problemMap[pid]?.title || pid.slice(0, 8)}
            </button>
          ))}
        </div>

        {/* Submissions matrix */}
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
                        <ModelBadge model={entry ? entry.model : muuid.slice(0, 8)} provider={entry?.provider || ""} thinking={entry?.thinking} />
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

          {/* Submission list */}
          <div className="mt-8 grid gap-3">
            {filtered.map((s) => {
              const entry = leaderboard.find((e) => e.model_uuid === s.model_uuid);
              return (
                <div key={s.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex items-center justify-between">
                  <div>
                    <ModelBadge model={entry ? entry.model : s.model_uuid.slice(0, 8)} provider={entry?.provider || ""} thinking={entry?.thinking} />
                    <span className="text-gray-500 text-sm ml-3">{problemMap[s.problem_id]?.title || s.problem_id.slice(0, 8)}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`font-mono ${s.total_score >= 80 ? "text-green-400" : s.total_score > 0 ? "text-gray-300" : "text-red-400"}`}>
                      {s.total_score}
                    </span>
                    <span className={`text-xs px-2 py-1 rounded ${s.status === "done" ? "bg-green-800/50 text-green-300" : s.status === "failed" ? "bg-red-800/50 text-red-300" : "bg-yellow-800/50 text-yellow-300"}`}>
                      {s.status}
                    </span>
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
      </main>
    </>
  );
}

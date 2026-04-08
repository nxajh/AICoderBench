"use client";

import { useEffect, useState, useMemo } from "react";
import { useParams } from "next/navigation";
import Nav from "@/components/nav";
import { fetchAPI, ModelStats, Problem } from "@/lib/api";
import Link from "next/link";

type SortKey = "problem_id" | "title" | "best_score" | "worst_score" | "avg_score" | "submission_count";
type SortDir = "asc" | "desc";

export default function ModelDetailPage() {
  const { modelId: modelUuid } = useParams<{ modelId: string }>();

  const [stats, setStats] = useState<ModelStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("best_score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expandedProblem, setExpandedProblem] = useState<string | null>(null);
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
    if (!modelUuid) return;
    fetchAPI<ModelStats>(`/api/model-stats/${modelUuid}`)
      .then((d) => { setStats(d); setLoading(false); })
      .catch((e: Error) => { setError(e.message || "加载失败"); setLoading(false); });
  }, [modelUuid]);

  const sorted = useMemo(() => {
    if (!stats) return [];
    const arr = [...stats.problems];
    arr.sort((a, b) => {
      const va = a[sortKey] as number;
      const vb = b[sortKey] as number;
      return sortDir === "asc" ? va - vb : vb - va;
    });
    return arr;
  }, [stats, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir(key === "best_score" ? "desc" : "asc"); }
  };

  const arrow = (key: SortKey) => sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  if (loading) return <><Nav /><div className="max-w-5xl mx-auto px-4 py-8 text-gray-400">加载中...</div></>;
  if (error) return <><Nav /><div className="max-w-5xl mx-auto px-4 py-8 text-red-400">加载失败：{error}</div></>;

  return (
    <>
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="mb-6">
          <Link href="/" className="text-cyan-400 hover:underline text-sm">← 返回排行榜</Link>
        </div>

        {stats ? (
          <>
            <div className="mb-6 flex items-center gap-3">
              <h1 className="text-2xl font-bold">{stats.model}</h1>
              <span className="text-xs text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">{stats.provider}</span>
              {stats.thinking && (
                <span className="text-xs text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">思考</span>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="text-gray-500 text-sm">总分</div>
                <div className="text-2xl font-mono text-cyan-400">{stats.problems.reduce((s, p) => s + p.best_score, 0)}</div>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="text-gray-500 text-sm">答题数</div>
                <div className="text-2xl font-mono">{stats.problems.length}</div>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="text-gray-500 text-sm">平均分</div>
                <div className="text-2xl font-mono">{stats.problems.length > 0 ? (stats.problems.reduce((s, p) => s + p.best_score, 0) / stats.problems.length).toFixed(1) : 0}</div>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="text-gray-500 text-sm">提交次数</div>
                <div className="text-2xl font-mono">{stats.problems.reduce((s, p) => s + p.submission_count, 0)}</div>
              </div>
            </div>

            <h2 className="text-lg font-semibold mb-4">各题目详情</h2>
            <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-gray-400 text-sm border-b border-gray-800">
                    <th className="px-4 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("problem_id")}>题目{arrow("problem_id")}</th>
                    <th className="px-4 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("best_score")}>最高分{arrow("best_score")}</th>
                    <th className="px-4 py-3 hidden sm:table-cell cursor-pointer hover:text-white" onClick={() => toggleSort("worst_score")}>最低分{arrow("worst_score")}</th>
                    <th className="px-4 py-3 hidden sm:table-cell cursor-pointer hover:text-white" onClick={() => toggleSort("avg_score")}>平均分{arrow("avg_score")}</th>
                    <th className="px-4 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("submission_count")}>提交次数{arrow("submission_count")}</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((p) => (
                    <tr key={p.problem_id}
                      className={`border-b border-gray-800/50 hover:bg-gray-800/50 cursor-pointer transition-colors ${expandedProblem === p.problem_id ? "bg-gray-800/30" : ""}`}
                      onClick={() => setExpandedProblem(expandedProblem === p.problem_id ? null : p.problem_id)}>
                      <td className="px-4 py-3 font-medium">{problemMap[p.problem_id]?.title || p.problem_id.slice(0, 8)}</td>
                      <td className="px-4 py-3">
                        <span className={`font-mono ${p.best_score >= 80 ? "text-green-400" : p.best_score >= 50 ? "text-yellow-400" : "text-red-400"}`}>
                          {p.best_score}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell font-mono text-gray-400">{p.worst_score}</td>
                      <td className="px-4 py-3 hidden sm:table-cell font-mono text-gray-400">{p.avg_score}</td>
                      <td className="px-4 py-3 text-gray-400">{p.submission_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="text-gray-500">暂无数据</p>
        )}
      </div>
    </>
  );
}

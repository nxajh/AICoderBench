"use client";

import { useEffect, useState, useMemo } from "react";
import Nav from "@/components/nav";
import ModelBadge from "@/components/model-badge";
import { fetchAPI, GlobalLeaderboardEntry } from "@/lib/api";

type SortKey = "rank" | "model" | "total_score" | "problems_attempted" | "avg_score" | "win_rate" | "total_tokens";
type SortDir = "asc" | "desc";

export default function HomePage() {
  const [data, setData] = useState<GlobalLeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("total_score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    fetchAPI<GlobalLeaderboardEntry[]>("/api/global-leaderboard")
      .then((d) => { setData(d); setLoading(false); })
      .catch((e: Error) => { setError(e.message || "加载失败"); setLoading(false); });
  }, []);

  const sorted = useMemo(() => {
    const arr = [...data];
    arr.sort((a, b) => {
      let va: number | string, vb: number | string;
      if (sortKey === "rank") {
        va = a.total_score; vb = b.total_score;
      } else {
        va = a[sortKey as keyof GlobalLeaderboardEntry] as number;
        vb = b[sortKey as keyof GlobalLeaderboardEntry] as number;
      }
      if (typeof va === "number") {
        return sortDir === "asc" ? va - vb : vb - va;
      }
      return 0;
    });
    return arr;
  }, [data, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir(key === "model" ? "asc" : "desc"); }
  };

  const arrow = (key: SortKey) => sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  return (
    <>
      <Nav />
      <main className="max-w-7xl mx-auto px-4 py-12">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-500 bg-clip-text text-transparent mb-3">
            AICoderBench
          </h1>
          <p className="text-gray-400 text-lg">国产大模型系统编程能力评测</p>
        </div>

        {loading && <p className="text-center text-gray-500">加载中...</p>}
        {!loading && error && <p className="text-center text-red-400">加载失败：{error}</p>}

        {!loading && sorted.length > 0 && (
          <section className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-800">
              <h2 className="text-lg font-semibold">全局排行榜</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-gray-400 text-sm border-b border-gray-800">
                    <th className="px-6 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("rank")}>排名{arrow("rank")}</th>
                    <th className="px-6 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("model")}>模型{arrow("model")}</th>
                    <th className="px-6 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("total_score")}>总分{arrow("total_score")}</th>
                    <th className="px-6 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("problems_attempted")}>答题数量{arrow("problems_attempted")}</th>
                    <th className="px-6 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("avg_score")}>平均分{arrow("avg_score")}</th>
                    <th className="px-6 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("win_rate")}>胜率{arrow("win_rate")}</th>
                    <th className="px-6 py-3 cursor-pointer hover:text-white" onClick={() => toggleSort("total_tokens")}>Token用量{arrow("total_tokens")}</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((entry, i) => (
                    <tr key={entry.model_uuid} className="border-b border-gray-800/50 hover:bg-gray-800/50 cursor-pointer transition-colors"
                        onClick={() => window.location.href = `/models/${entry.model_uuid}`}>
                      <td className="px-6 py-3 font-mono text-gray-500">{i + 1}</td>
                      <td className="px-6 py-3">
                        <ModelBadge model={entry.model} provider={entry.provider} thinking={entry.thinking} />
                      </td>
                      <td className="px-6 py-3 text-cyan-400 font-mono">{entry.total_score}</td>
                      <td className="px-6 py-3 text-gray-400">{entry.problems_attempted}</td>
                      <td className="px-6 py-3 text-gray-400 font-mono">{entry.avg_score}</td>
                      <td className="px-6 py-3">
                        <span className={`font-mono ${entry.win_rate >= 80 ? 'text-green-400' : entry.win_rate >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
                          {entry.win_rate}%
                        </span>
                      </td>
                      <td className="px-6 py-3 text-gray-400 font-mono">{entry.total_tokens > 0 ? (entry.total_tokens >= 1000 ? `${(entry.total_tokens / 1000).toFixed(1)}K` : entry.total_tokens) : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {!loading && data.length === 0 && (
          <p className="text-center text-gray-500">暂无评测数据。运行一轮评测开始吧！</p>
        )}
      </main>
    </>
  );
}

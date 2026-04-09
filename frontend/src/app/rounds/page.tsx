"use client";

import { useEffect, useState, useRef } from "react";
import Nav from "@/components/nav";
import { fetchAPI, RoundInfo } from "@/lib/api";
import Link from "next/link";

function StatusDot({ status }: { status: string }) {
  if (status === "running") {
    return <span className="inline-block w-2 h-2 rounded-full bg-cyan-400 animate-pulse mr-1.5" />;
  }
  if (status === "done") {
    return <span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1.5" />;
  }
  return <span className="inline-block w-2 h-2 rounded-full bg-gray-600 mr-1.5" />;
}

export default function RoundsPage() {
  const [rounds, setRounds] = useState<RoundInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = () =>
    fetchAPI<RoundInfo[]>("/api/rounds")
      .then((data) => { setRounds(data); setError(null); })
      .catch((e: Error) => { setError(e.message || "加载失败"); });

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  // Auto-refresh while any round is running
  useEffect(() => {
    const hasRunning = rounds.some((r) => r.status === "running");
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (hasRunning) {
      intervalRef.current = setInterval(load, 8000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [rounds.map((r) => r.status).join(",")]);

  return (
    <>
      <Nav />
      <main className="max-w-7xl mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold mb-8 bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
          评测轮次
        </h1>
        {loading && <p className="text-gray-500">加载中...</p>}
        {!loading && error && <p className="text-red-400 text-sm mb-4">加载失败：{error}</p>}
        <div className="grid gap-4">
          {rounds.map((r) => {
            const lb = r.leaderboard || [];
            const champion = lb.length > 0 ? lb[0] : null;
            const completed = lb.reduce((s, e) => s + (e.completed || 0), 0);
            const total = (r.problem_ids?.length || 0) * (r.model_uuids?.length || 0);
            const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

            return (
              <Link
                key={r.id}
                href={`/rounds/${r.id}`}
                className="block bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-cyan-800 transition-colors"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h2 className="text-lg font-semibold flex items-center">
                      <StatusDot status={r.status} />
                      {r.name || r.id}
                    </h2>
                    <p className="text-gray-500 text-sm mt-0.5">{r.created_at?.slice(0, 10)}</p>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded ${
                    r.status === "done" ? "bg-green-800/50 text-green-300" :
                    r.status === "running" ? "bg-cyan-900/50 text-cyan-300" :
                    "bg-yellow-800/50 text-yellow-300"
                  }`}>
                    {r.status === "running" ? "运行中" : r.status === "done" ? "已完成" : r.status}
                  </span>
                </div>

                <div className="flex gap-4 mt-3 text-sm text-gray-400">
                  <span>{r.problem_ids?.length || 0} 题</span>
                  <span>{r.model_uuids?.length || 0} 模型</span>
                  {total > 0 && <span>{completed}/{total} 完成</span>}
                </div>

                {/* Progress bar for running rounds */}
                {r.status === "running" && total > 0 && (
                  <div className="mt-3 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all duration-700"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                )}

                {champion && (
                  <div className="mt-2 text-sm text-cyan-400">
                    🏆 {champion.model} — {champion.total_score} 分
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      </main>
    </>
  );
}

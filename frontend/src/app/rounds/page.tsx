"use client";

import { useEffect, useState } from "react";
import Nav from "@/components/nav";
import { fetchAPI, RoundInfo } from "@/lib/api";
import Link from "next/link";

export default function RoundsPage() {
  const [rounds, setRounds] = useState<RoundInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAPI<RoundInfo[]>("/api/rounds")
      .then((data) => { setRounds(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <>
      <Nav />
      <main className="max-w-7xl mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold mb-8 bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
          评测轮次
        </h1>
        {loading && <p className="text-gray-500">加载中...</p>}
        <div className="grid gap-4">
          {rounds.map((r) => {
            const lb = r.leaderboard || [];
            const champion = lb.length > 0 ? lb[0] : null;
            const completed = lb.reduce((s, e) => s + (e.completed || 0), 0);
            const total = (r.problem_ids?.length || 0) * (r.model_uuids?.length || 0);

            return (
              <Link
                key={r.id}
                href={`/rounds/${r.id}`}
                className="block bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-cyan-800 transition-colors"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h2 className="text-lg font-semibold">{r.name || r.id}</h2>
                    <p className="text-gray-500 text-sm">{r.created_at?.slice(0, 10)}</p>
                  </div>
                  <div className="text-right">
                    <span className={`text-xs px-2 py-1 rounded ${r.status === "done" ? "bg-green-800/50 text-green-300" : "bg-yellow-800/50 text-yellow-300"}`}>
                      {r.status}
                    </span>
                  </div>
                </div>
                <div className="flex gap-4 mt-3 text-sm text-gray-400">
                  <span>{r.problem_ids?.length || 0} 题</span>
                  <span>{r.model_uuids?.length || 0} 模型</span>
                  {total > 0 && <span>{completed}/{total} 完成</span>}
                </div>
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

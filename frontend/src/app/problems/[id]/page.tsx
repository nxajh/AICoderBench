"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/nav";
import { fetchAPI, deleteAPI } from "@/lib/api";

interface ProblemDetail {
  title: string;
  difficulty: string;
  language: string;
  tags: string[];
  description: string;
  interface_h: string;
  compile_flags: string;
  scoring: Record<string, number>;
  timeout_seconds: number;
}

interface ProblemLeaderboardEntry {
  model_uuid: string;
  provider: string;
  model: string;
  thinking: boolean;
  best_score: number;
  total_tokens: number;
  duration: number;
  rounds: number;
  best_round_id?: string;
}

export default function ProblemDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;
  const [problem, setProblem] = useState<ProblemDetail | null>(null);
  const [leaderboard, setLeaderboard] = useState<ProblemLeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAPI<ProblemDetail>(`/api/problems/${id}`)
      .then((data) => { setProblem(data); setLoading(false); })
      .catch(() => setLoading(false));
    fetchAPI<ProblemLeaderboardEntry[]>(`/api/problem-leaderboard/${id}`)
      .then((data) => setLeaderboard(data))
      .catch(() => setLeaderboard([]));
  }, [id]);

  if (loading) return <><Nav /><main className="max-w-4xl mx-auto px-4 py-12"><p className="text-gray-500">加载中...</p></main></>;
  if (!problem) return <><Nav /><main className="max-w-4xl mx-auto px-4 py-12"><p className="text-gray-500">未找到题目</p></main></>;

  const handleDelete = async () => {
    if (!confirm(`确定删除题目 "${problem.title}"？此操作不可恢复。`)) return;
    try {
      await deleteAPI(`/api/problems/${id}`);
      router.push("/problems");
    } catch (e) {
      alert(`删除失败: ${e instanceof Error ? e.message : e}`);
    }
  };

  const diffColors: Record<string, string> = {
    easy: "bg-green-700/50 text-green-300",
    medium: "bg-yellow-700/50 text-yellow-300",
    hard: "bg-red-700/50 text-red-300",
  };

  return (
    <>
      <Nav />
      <main className="max-w-4xl mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold mb-2 bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
          {problem.title}
        </h1>
        <div className="flex items-center gap-3 mb-8">
          <span className={`text-xs px-2 py-0.5 rounded ${diffColors[problem.difficulty] || "bg-gray-700 text-gray-300"}`}>
            {problem.difficulty}
          </span>
          <span className="text-xs bg-cyan-900/40 text-cyan-300 px-2 py-0.5 rounded">{problem.language}</span>
          {problem.tags.map((tag) => (
            <span key={tag} className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded">{tag}</span>
          ))}
          <div className="flex-1" />
          <Link href={`/problems/${id}/edit`}
            className="px-3 py-1 rounded text-xs bg-gray-700 hover:bg-gray-600 text-gray-300">
            编辑
          </Link>
          <button onClick={handleDelete}
            className="px-3 py-1 rounded text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20">
            删除
          </button>
        </div>

        {/* 题目描述 */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-3">📝 题目描述</h2>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 prose prose-invert prose-sm max-w-none">
            <div dangerouslySetInnerHTML={{ __html: simpleMarkdown(problem.description) }} />
          </div>
        </section>

        {/* 接口定义 */}
        {problem.interface_h && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold mb-3">🔌 接口定义</h2>
            <pre className="bg-gray-900 border border-gray-800 rounded-xl p-6 overflow-x-auto text-sm text-gray-300 leading-relaxed">
              <code>{problem.interface_h}</code>
            </pre>
          </section>
        )}

        {/* 本题排行榜 */}
        {leaderboard.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold mb-3">🏆 本题排行榜</h2>
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-gray-400 text-sm border-b border-gray-800">
                    <th className="px-4 py-3 w-16">排名</th>
                    <th className="px-4 py-3">模型</th>
                    <th className="px-4 py-3">最高分</th>
                    <th className="px-4 py-3">Token用量</th>
                    <th className="px-4 py-3">耗时</th>
                    <th className="px-4 py-3">轮次</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.map((entry, idx) => {
                    const canNavigate = !!entry.best_round_id;
                    const handleClick = canNavigate
                      ? () => router.push(`/submission/${entry.best_round_id}/${id}/${entry.model_uuid}`)
                      : undefined;
                    return (
                      <tr
                        key={entry.model_uuid}
                        className={`border-b border-gray-800/50 hover:bg-gray-800/50 transition-colors ${canNavigate ? 'cursor-pointer' : ''}`}
                        onClick={handleClick}
                      >
                        <td className="px-4 py-3 text-gray-400 font-mono">
                          {idx === 0 ? "🥇" : idx === 1 ? "🥈" : idx === 2 ? "🥉" : idx + 1}
                        </td>
                        <td className="px-4 py-3">
                          <span>
                            <span className="text-cyan-400">{entry.model}</span>
                            <span className="ml-1 text-xs text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">{entry.provider}</span>
                            {entry.thinking && <span className="ml-1 text-xs text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">思考</span>}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono">
                          <span className={entry.best_score >= 80 ? "text-green-400" : entry.best_score >= 50 ? "text-yellow-400" : "text-red-400"}>
                            {entry.best_score}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-400 font-mono">{entry.total_tokens > 0 ? `${(entry.total_tokens / 1000).toFixed(1)}K` : '-'}</td>
                        <td className="px-4 py-3 text-gray-400 font-mono">{entry.duration > 0 ? `${entry.duration.toFixed(1)}s` : '-'}</td>
                        <td className="px-4 py-3 text-gray-400 font-mono">{entry.rounds > 0 ? entry.rounds : '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* 编译参数 */}
        <section>
          <h2 className="text-lg font-semibold mb-3">⚙️ 编译参数</h2>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-sm text-gray-400 space-y-2">
            <p>编译标志: <code className="text-gray-300 bg-gray-800 px-2 py-0.5 rounded">{problem.compile_flags || "无"}</code></p>
            <p>超时: <code className="text-gray-300 bg-gray-800 px-2 py-0.5 rounded">{problem.timeout_seconds}s</code></p>
          </div>
        </section>
      </main>
    </>
  );
}

function simpleMarkdown(text: string): string {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/```(\w*)\n([\s\S]*?)```/g, "<pre class=\"bg-gray-800 rounded p-3 overflow-x-auto text-sm\"><code>$2</code></pre>")
    .replace(/`([^`]+)`/g, "<code class=\"bg-gray-800 px-1 rounded text-sm\">$1</code>")
    .replace(/^### (.+)$/gm, "<h3 class=\"text-base font-semibold mt-4 mb-2\">$1</h3>")
    .replace(/^## (.+)$/gm, "<h2 class=\"text-lg font-semibold mt-4 mb-2\">$1</h2>")
    .replace(/^# (.+)$/gm, "<h1 class=\"text-xl font-bold mt-4 mb-2\">$1</h1>")
    .replace(/^- (.+)$/gm, "<li class=\"ml-4\">$1</li>")
    .replace(/\n/g, "<br />");
}

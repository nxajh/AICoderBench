"use client";

import { useEffect, useState } from "react";
import Nav from "@/components/nav";
import { fetchAPI, deleteAPI, Problem } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";

const difficultyColors: Record<string, string> = {
  easy: "bg-green-700/50 text-green-300",
  medium: "bg-yellow-700/50 text-yellow-300",
  hard: "bg-red-700/50 text-red-300",
};

export default function ProblemsPage() {
  const [problems, setProblems] = useState<Problem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const router = useRouter();

  const load = async () => {
    try {
      const data = await fetchAPI<Problem[]>("/api/problems");
      setProblems(data);
    } catch {
      setError("加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (id: string, title: string) => {
    if (!confirm(`确定删除题目 "${title}"？此操作不可恢复。`)) return;
    try {
      await deleteAPI(`/api/problems/${id}`);
      setProblems(problems.filter(p => p.uuid !== id));
    } catch (e) {
      alert(`删除失败: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <>
      <Nav />
      <main className="max-w-7xl mx-auto px-4 py-12">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
            题库
          </h1>
          <Link
            href="/problems/new"
            className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white"
          >
            + 添加题目
          </Link>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
        {loading && <p className="text-gray-500">加载中...</p>}

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {problems.map((p) => (
            <div
              key={p.uuid}
              className="block bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-cyan-800 transition-colors"
            >
              <div className="flex items-center gap-3 mb-3">
                <Link href={`/problems/${p.uuid}`} className="font-semibold text-lg hover:text-cyan-400 transition-colors flex-1 min-w-0 truncate">
                  {p.title}
                </Link>
                <span className={`text-xs px-2 py-0.5 rounded ${difficultyColors[p.difficulty] || "bg-gray-700 text-gray-300"}`}>
                  {p.difficulty}
                </span>
              </div>
              <Link href={`/problems/${p.uuid}`}>
                <p className="text-gray-400 text-sm mb-4 line-clamp-3">{p.description || p.slug}</p>
              </Link>
              <div className="flex flex-wrap gap-2 mb-4">
                {p.tags?.map((tag) => (
                  <span key={tag} className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded">
                    {tag}
                  </span>
                ))}
                {p.language && (
                  <span className="text-xs bg-cyan-900/40 text-cyan-300 px-2 py-1 rounded">
                    {p.language}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 pt-3 border-t border-gray-800">
                <Link
                  href={`/problems/${p.uuid}/edit`}
                  className="px-3 py-1 rounded text-xs bg-gray-700 hover:bg-gray-600 text-gray-300"
                >
                  编辑
                </Link>
                <button
                  onClick={() => handleDelete(p.uuid, p.title)}
                  className="px-3 py-1 rounded text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}

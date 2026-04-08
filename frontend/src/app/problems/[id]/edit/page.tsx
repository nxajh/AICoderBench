"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Nav from "@/components/nav";
import { fetchAPI, putAPI, postAPI } from "@/lib/api";

const SCORING_KEYS = ["compile", "tests", "concurrency", "memory", "quality", "performance", "efficiency"] as const;

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

export default function EditProblemPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [testC, setTestC] = useState("");

  const [form, setForm] = useState({
    title: "",
    difficulty: "medium",
    tags: "",
    language: "c",
    compile_flags: "",
    timeout_seconds: 30,
    description: "",
    interface_h: "",
    scoring: {} as Record<string, number>,
  });

  useEffect(() => {
    fetchAPI<ProblemDetail>(`/api/problems/${id}`)
      .then(data => {
        setForm({
          title: data.title,
          difficulty: data.difficulty,
          tags: (data.tags || []).join(", "),
          language: data.language,
          compile_flags: data.compile_flags,
          timeout_seconds: data.timeout_seconds,
          description: data.description,
          interface_h: data.interface_h,
          scoring: data.scoring || {},
        });
        setLoading(false);
      })
      .catch(() => {
        setError("加载失败");
        setLoading(false);
      });
  }, [id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!form.title.trim()) {
      setError("标题不能为空");
      return;
    }

    setSaving(true);
    try {
      await putAPI(`/api/problems/${id}`, {
        title: form.title,
        difficulty: form.difficulty,
        tags: form.tags.split(",").map(t => t.trim()).filter(Boolean),
        language: form.language,
        compile_flags: form.compile_flags,
        timeout_seconds: form.timeout_seconds,
        scoring: form.scoring,
        description: form.description,
        interface_h: form.interface_h,
      });
      if (testC.trim()) {
        await postAPI(`/api/problems/${id}/test-file`, { test_c: testC });
      }
      router.push(`/problems/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "更新失败");
    } finally {
      setSaving(false);
    }
  };

  const updateScoring = (key: string, value: number) => {
    setForm(f => ({ ...f, scoring: { ...f.scoring, [key]: value } }));
  };

  if (loading) return <><Nav /><main className="max-w-4xl mx-auto px-4 py-12"><p className="text-gray-500">加载中...</p></main></>;

  return (
    <>
      <Nav />
      <main className="max-w-4xl mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold mb-8 bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
          编辑题目: {form.title}
        </h1>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* 基本信息 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">基本信息</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1">题目 ID</label>
                <input value={id} disabled
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-500" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">标题 *</label>
                <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" required />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">难度</label>
                <select value={form.difficulty} onChange={e => setForm(f => ({ ...f, difficulty: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm">
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">语言</label>
                <input value={form.language} onChange={e => setForm(f => ({ ...f, language: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-xs text-gray-400 mb-1">标签（逗号分隔）</label>
                <input value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">编译参数</label>
                <input value={form.compile_flags} onChange={e => setForm(f => ({ ...f, compile_flags: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">超时时间（秒）</label>
                <input type="number" value={form.timeout_seconds} onChange={e => setForm(f => ({ ...f, timeout_seconds: parseInt(e.target.value) || 30 }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" />
              </div>
            </div>
          </div>

          {/* 评分权重 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">评分权重</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
              {SCORING_KEYS.map(key => (
                <div key={key}>
                  <label className="block text-xs text-gray-400 mb-1 capitalize">{key}</label>
                  <input type="number" value={form.scoring[key] ?? 0} onChange={e => updateScoring(key, parseInt(e.target.value) || 0)}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" />
                </div>
              ))}
            </div>
          </div>

          {/* 题目描述 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">题目描述（Markdown）</h2>
            <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm font-mono min-h-[200px]" />
          </div>

          {/* 接口头文件 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">接口头文件 (solution.h)</h2>
            <textarea value={form.interface_h} onChange={e => setForm(f => ({ ...f, interface_h: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm font-mono min-h-[200px]" />
          </div>

          {/* 测试文件 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">测试文件 (test.c)</h2>
            <p className="text-xs text-gray-500">留空则不更新测试文件</p>
            <textarea value={testC} onChange={e => setTestC(e.target.value)}
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm font-mono min-h-[200px]" />
          </div>

          {/* 提交按钮 */}
          <div className="flex gap-3">
            <button type="submit" disabled={saving}
              className="px-5 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white disabled:opacity-50">
              {saving ? "保存中..." : "保存"}
            </button>
            <button type="button" onClick={() => router.push(`/problems/${id}`)}
              className="px-5 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">
              取消
            </button>
          </div>
        </form>
      </main>
    </>
  );
}

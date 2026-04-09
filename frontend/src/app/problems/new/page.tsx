"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/nav";
import { postAPI } from "@/lib/api";

const SCORING_KEYS = ["compile", "tests", "concurrency", "memory", "quality", "performance", "efficiency"] as const;
const DEFAULT_SCORING: Record<string, number> = {
  compile: 10, tests: 20, concurrency: 25, memory: 15, quality: 10, performance: 10, efficiency: 10,
};

export default function NewProblemPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    title: "",
    slug: "",
    difficulty: "medium",
    tags: "",
    language: "c",
    compile_flags: "",
    timeout_seconds: 30,
    description: "",
    interface_h: "",
    test_c: "",
    scoring: { ...DEFAULT_SCORING },
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!form.title.trim()) {
      setError("标题不能为空");
      return;
    }

    setSaving(true);
    try {
      const created = await postAPI<{ slug?: string; id?: string }>("/api/problems", {
        title: form.title,
        slug: form.slug.trim() || undefined,
        difficulty: form.difficulty,
        tags: form.tags.split(",").map(t => t.trim()).filter(Boolean),
        language: form.language,
        compile_flags: form.compile_flags,
        timeout_seconds: form.timeout_seconds,
        scoring: form.scoring,
        description: form.description,
        interface_h: form.interface_h,
      });
      // Upload test file if provided
      const problemSlug = created.slug || created.id;
      if (form.test_c.trim() && problemSlug) {
        await postAPI(`/api/problems/${problemSlug}/test-file`, { test_c: form.test_c });
      }
      router.push("/problems");
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setSaving(false);
    }
  };

  const updateScoring = (key: string, value: number) => {
    setForm(f => ({ ...f, scoring: { ...f.scoring, [key]: value } }));
  };

  return (
    <>
      <Nav />
      <main className="max-w-4xl mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold mb-8 bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
          创建题目
        </h1>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* 基本信息 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">基本信息</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1">标题 *</label>
                <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" placeholder="如: 线程池实现" required />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">英文标识 <span className="text-gray-600">（可选，用于目录名）</span></label>
                <input value={form.slug} onChange={e => setForm(f => ({ ...f, slug: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" placeholder="如: thread-pool" />
                <p className="text-xs text-gray-600 mt-1">留空则仅用序号，如 11</p>
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
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" placeholder="concurrency, lock, thread-pool" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">编译参数</label>
                <input value={form.compile_flags} onChange={e => setForm(f => ({ ...f, compile_flags: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" placeholder="-lpthread" />
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
                  <input type="number" value={form.scoring[key]} onChange={e => updateScoring(key, parseInt(e.target.value) || 0)}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" />
                </div>
              ))}
            </div>
          </div>

          {/* 题目描述 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">题目描述（Markdown）</h2>
            <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm font-mono min-h-[200px]" placeholder="# 题目标题&#10;&#10;题目描述..." />
          </div>

          {/* 接口头文件 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">接口头文件 (solution.h)</h2>
            <textarea value={form.interface_h} onChange={e => setForm(f => ({ ...f, interface_h: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm font-mono min-h-[200px]" placeholder="#ifndef EXAMPLE_H&#10;#define EXAMPLE_H&#10;&#10;...&#10;&#10;#endif" />
          </div>

          {/* 测试文件 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-semibold">测试文件 (test.c)</h2>
            <textarea value={form.test_c} onChange={e => setForm(f => ({ ...f, test_c: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm font-mono min-h-[200px]" placeholder="#include &quot;solution.h&quot;&#10;#include &quot;test_framework.h&quot;&#10;&#10;..." />
          </div>

          {/* 提交按钮 */}
          <div className="flex gap-3">
            <button type="submit" disabled={saving}
              className="px-5 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white disabled:opacity-50">
              {saving ? "创建中..." : "创建题目"}
            </button>
            <button type="button" onClick={() => router.push("/problems")}
              className="px-5 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">
              取消
            </button>
          </div>
        </form>
      </main>
    </>
  );
}

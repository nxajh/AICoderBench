"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/nav";
import ModelBadge from "@/components/model-badge";
import type { Problem } from "@/lib/api";

interface ModelSelectItem {
  uuid: string;
  provider: string;
  api_model: string;
  thinking: boolean;
}

export default function NewRoundPage() {
  const router = useRouter();
  const [problems, setProblems] = useState<Problem[]>([]);
  const [models, setModels] = useState<ModelSelectItem[]>([]);
  const [selectedProblems, setSelectedProblems] = useState<Set<string>>(new Set());
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [roundName, setRoundName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/problems").then(r => r.json()).then(setProblems).catch(console.error);
    fetch("/api/models").then(r => r.json()).then(setModels).catch(console.error);
  }, []);

  const toggleProblem = (id: string) => {
    setSelectedProblems(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleModel = (id: string) => {
    setSelectedModels(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectAllProblems = () => {
    if (selectedProblems.size === problems.length) {
      setSelectedProblems(new Set());
    } else {
      setSelectedProblems(new Set(problems.map(p => p.uuid)));
    }
  };

  const selectAllModels = () => {
    if (selectedModels.size === models.length) {
      setSelectedModels(new Set());
    } else {
      setSelectedModels(new Set(models.map(m => m.uuid)));
    }
  };

  const handleSubmit = async () => {
    if (selectedProblems.size === 0 || selectedModels.size === 0) {
      setError("请至少选择一道题目和一个模型");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch("/api/rounds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: roundName || undefined,
          problem_ids: Array.from(selectedProblems),
          model_uuids: Array.from(selectedModels),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || "创建失败");
        setSubmitting(false);
        return;
      }
      const roundId: string = data.round_id || data.id;
      if (roundId) {
        router.push(`/rounds/${roundId}`);
      }
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  };

  const totalTasks = selectedProblems.size * selectedModels.size;

  return (
    <>
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-6">发起新评测</h1>

        {/* Round Name */}
        <div className="mb-6">
          <label className="block text-sm text-gray-400 mb-2">轮次名称（可选）</label>
          <input
            type="text"
            value={roundName}
            onChange={e => setRoundName(e.target.value)}
            placeholder="例：GLM-5.1 vs MiniMax M2.7"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-cyan-500"
          />
        </div>

        {/* Model Selection */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">选择模型</h2>
            <button onClick={selectAllModels} className="text-xs text-cyan-400 hover:text-cyan-300">
              {selectedModels.size === models.length ? "取消全选" : "全选"}
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {models.map(m => (
              <button
                key={m.uuid}
                onClick={() => toggleModel(m.uuid)}
                className={`rounded-lg border px-4 py-3 text-left transition-all ${
                  selectedModels.has(m.uuid)
                    ? "border-cyan-500 bg-cyan-500/10 text-cyan-400"
                    : "border-gray-700 bg-gray-900 text-gray-300 hover:border-gray-500"
                }`}
              >
                <div className="font-medium">
                  <ModelBadge model={m.api_model} provider={m.provider} thinking={m.thinking} />
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Problem Selection */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">选择题目</h2>
            <button onClick={selectAllProblems} className="text-xs text-cyan-400 hover:text-cyan-300">
              {selectedProblems.size === problems.length ? "取消全选" : "全选"}
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {problems.map(p => (
              <button
                key={p.uuid}
                onClick={() => toggleProblem(p.uuid)}
                className={`rounded-lg border px-4 py-3 text-left transition-all ${
                  selectedProblems.has(p.uuid)
                    ? "border-cyan-500 bg-cyan-500/10 text-cyan-400"
                    : "border-gray-700 bg-gray-900 text-gray-300 hover:border-gray-500"
                }`}
              >
                <div className="font-medium text-sm">{p.title}</div>
                <div className="text-xs text-gray-500 mt-1">{p.difficulty} · {p.tags?.join(", ")}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Submit */}
        <div className="border-t border-gray-800 pt-4">
          {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <span className="text-sm text-gray-400">
              {selectedModels.size} 个模型 × {selectedProblems.size} 道题 = {totalTasks} 个任务
            </span>
            <button
              onClick={handleSubmit}
              disabled={submitting || totalTasks === 0}
              className={`px-6 py-2 rounded-lg font-medium transition-all ${
                submitting || totalTasks === 0
                  ? "bg-gray-700 text-gray-500 cursor-not-allowed"
                  : "bg-cyan-600 hover:bg-cyan-500 text-white"
              }`}
            >
              {submitting ? "启动中..." : "开始评测"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

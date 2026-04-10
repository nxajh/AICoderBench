"use client";

import { useEffect, useState } from "react";
import Nav from "@/components/nav";
import ModelBadge from "@/components/model-badge";

interface ModelConfig {
  uuid: string;
  provider: string;      // 显示名（如 "DeepSeek"、"GLM"）
  model: string;
  api_key_masked: string;
  base_url: string;
  enabled: boolean;
  thinking: boolean;
}

interface EditForm {
  display_name: string;
  api_model: string;
  api_key: string;
  base_url: string;
  thinking: boolean;
}

export default function ModelsPage() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<EditForm>(emptyForm());
  const [saving, setSaving] = useState(false);

  function emptyForm(): EditForm {
    return { display_name: "", api_model: "", api_key: "", base_url: "", thinking: false };
  }

  const load = async () => {
    try {
      const res = await fetch("/api/model-configs");
      if (!res.ok) throw new Error("加载失败");
      setModels(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const startAdd = () => {
    setEditing("new");
    setForm(emptyForm());
    setError("");
  };

  const startEdit = (m: ModelConfig) => {
    setEditing(m.uuid);
    setForm({
      display_name: m.provider,
      api_model: m.model,
      api_key: "",
      base_url: m.base_url || "",
      thinking: m.thinking,
    });
    setError("");
  };

  const cancelEdit = () => {
    setEditing(null);
    setError("");
  };

  const handleSave = async () => {
    if (!form.api_model) {
      setError("API 模型名不能为空");
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (editing === "new") {
        if (!form.api_key) {
          setError("新增模型时 API Key 不能为空");
          setSaving(false);
          return;
        }
        const res = await fetch("/api/model-configs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: "openai",
            display_name: form.display_name,
            api_model: form.api_model,
            api_key: form.api_key,
            base_url: form.base_url,
            thinking: form.thinking,
          }),
        });
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          throw new Error(d.detail || d.error || `添加失败 (HTTP ${res.status})`);
        }
      } else {
        const body: Record<string, unknown> = {
          base_url: form.base_url,
          thinking: form.thinking,
        };
        if (form.api_key) body.api_key = form.api_key;
        const res = await fetch(`/api/model-configs/${editing}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          throw new Error(d.detail || d.error || `更新失败 (HTTP ${res.status})`);
        }
      }
      setEditing(null);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (m: ModelConfig) => {
    if (!confirm(`确定删除模型 "${m.provider} / ${m.model}"？`)) return;
    try {
      const res = await fetch(`/api/model-configs/${m.uuid}`, { method: "DELETE" });
      if (!res.ok) throw new Error("删除失败");
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleToggleEnabled = async (m: ModelConfig) => {
    try {
      const res = await fetch(`/api/model-configs/${m.uuid}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !m.enabled }),
      });
      if (!res.ok) throw new Error("操作失败");
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  if (loading) return <><Nav /><div className="max-w-5xl mx-auto px-4 py-8 text-gray-400">加载中...</div></>;

  return (
    <>
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">模型管理</h1>
          {editing === null && (
            <button onClick={startAdd}
              className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white">
              + 添加模型
            </button>
          )}
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {/* Add / Edit form */}
        {editing !== null && (
          <div className="mb-6 rounded-lg border border-gray-700 bg-gray-900 p-5">
            <h2 className="text-lg font-semibold mb-4">
              {editing === "new" ? "添加模型" : <>编辑: <ModelBadge model={form.api_model} provider={form.display_name} thinking={form.thinking} /></>}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1">显示名称</label>
                <input value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
                  placeholder="如: DeepSeek、GLM、Qwen" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">API 模型名</label>
                <input value={form.api_model} onChange={e => setForm(f => ({ ...f, api_model: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
                  placeholder="如: deepseek-chat、glm-4-plus" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">API Key{editing !== "new" ? "（留空保留原值）" : ""}</label>
                <input type="password" value={form.api_key} onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm" placeholder="sk-..." />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Base URL</label>
                <input value={form.base_url} onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
                  placeholder="https://api.example.com/v1" />
              </div>
              <div className="flex items-center gap-2 sm:col-span-2">
                <input type="checkbox" id="thinking" checked={form.thinking}
                  onChange={e => setForm(f => ({ ...f, thinking: e.target.checked }))}
                  className="rounded" />
                <label htmlFor="thinking" className="text-sm text-gray-300">启用思考模式（extended thinking）</label>
              </div>
            </div>
            <div className="mt-3 text-xs text-gray-500">模型将获得唯一 UUID 作为内部标识</div>
            <div className="flex gap-3 mt-5">
              <button onClick={handleSave} disabled={saving}
                className="px-5 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white disabled:opacity-50">
                {saving ? "保存中..." : "保存"}
              </button>
              <button onClick={cancelEdit}
                className="px-5 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">
                取消
              </button>
            </div>
          </div>
        )}

        {/* Model list */}
        <div className="space-y-3">
          {models.length === 0 && (
            <p className="text-gray-500 text-center py-10">暂无模型配置，点击上方按钮添加</p>
          )}
          {models.map(m => (
            <div key={m.uuid}
              className={`rounded-lg border px-5 py-4 flex items-center justify-between transition-all ${
                m.enabled ? "border-gray-700 bg-gray-900" : "border-gray-800 bg-gray-900/40 opacity-60"
              }`}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3">
                  <ModelBadge model={m.model} provider={m.provider} thinking={m.thinking} />
                  {!m.enabled && <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">已禁用</span>}
                </div>
                <div className="flex gap-4 mt-1 text-xs text-gray-500">
                  <span className="font-mono">{m.api_key_masked}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 ml-4">
                <button onClick={() => handleToggleEnabled(m)}
                  className={`px-3 py-1 rounded text-xs ${m.enabled ? "bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20" : "bg-green-500/10 text-green-400 hover:bg-green-500/20"}`}>
                  {m.enabled ? "禁用" : "启用"}
                </button>
                <button onClick={() => startEdit(m)}
                  className="px-3 py-1 rounded text-xs bg-gray-700 hover:bg-gray-600 text-gray-300">
                  编辑
                </button>
                <button onClick={() => handleDelete(m)}
                  className="px-3 py-1 rounded text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20">
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

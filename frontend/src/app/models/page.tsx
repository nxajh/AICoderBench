"use client";

import { useEffect, useState } from "react";
import Nav from "@/components/nav";
import ModelBadge from "@/components/model-badge";
import {
  fetchAPI, postAPI, putAPI, deleteAPI,
  Provider, ModelConfig,
} from "@/lib/api";

// ---- sub-forms ----

interface ProviderForm {
  name: string;
  api_format: string;
  api_key: string;
  base_url: string;
}

function emptyProviderForm(): ProviderForm {
  return { name: "", api_format: "openai", api_key: "", base_url: "" };
}

interface ModelForm {
  model_id: string;
  thinking: boolean;
  thinking_budget: number;
  max_tokens: number;
}

function emptyModelForm(): ModelForm {
  return { model_id: "", thinking: false, thinking_budget: 10000, max_tokens: 65536 };
}

function ProviderFormView({
  form,
  setForm,
  isEdit,
}: {
  form: ProviderForm;
  setForm: (f: ProviderForm) => void;
  isEdit: boolean;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div>
        <label className="block text-xs text-gray-400 mb-1">名称</label>
        <input
          value={form.name}
          onChange={e => setForm({ ...form, name: e.target.value })}
          className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
          placeholder="如: Anthropic、DeepSeek"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">API 格式</label>
        <select
          value={form.api_format}
          onChange={e => setForm({ ...form, api_format: e.target.value })}
          className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
        >
          <option value="openai">OpenAI 兼容</option>
          <option value="anthropic">Anthropic</option>
        </select>
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          API Key{isEdit ? "（留空保留原值）" : ""}
        </label>
        <input
          type="password"
          value={form.api_key}
          onChange={e => setForm({ ...form, api_key: e.target.value })}
          className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
          placeholder="sk-..."
        />
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">Base URL</label>
        <input
          value={form.base_url}
          onChange={e => setForm({ ...form, base_url: e.target.value })}
          className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
          placeholder="https://api.example.com（留空使用默认）"
        />
      </div>
    </div>
  );
}

function ModelFormView({
  form,
  setForm,
  apiFormat,
}: {
  form: ModelForm;
  setForm: (f: ModelForm) => void;
  apiFormat: string;
}) {
  const showThinkingBudget = apiFormat === "anthropic" && form.thinking;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div className="sm:col-span-2">
        <label className="block text-xs text-gray-400 mb-1">模型 ID</label>
        <input
          value={form.model_id}
          onChange={e => setForm({ ...form, model_id: e.target.value })}
          className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
          placeholder="如: claude-opus-4-5、deepseek-chat"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">max_tokens（生成上限）</label>
        <input
          type="number"
          value={form.max_tokens}
          onChange={e => setForm({ ...form, max_tokens: Math.max(1, parseInt(e.target.value) || 65536) })}
          className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
          min={1} max={131072} step={1024}
        />
      </div>
      <div className="flex items-center gap-2 self-end pb-2">
        <input
          type="checkbox"
          id="model-thinking"
          checked={form.thinking}
          onChange={e => setForm({ ...form, thinking: e.target.checked })}
          className="rounded"
        />
        <label htmlFor="model-thinking" className="text-sm text-gray-300">
          启用 Extended Thinking
          {apiFormat !== "anthropic" && (
            <span className="ml-1 text-xs text-gray-500">（仅 Anthropic 格式支持）</span>
          )}
        </label>
      </div>
      {showThinkingBudget && (
        <div className="sm:col-span-2">
          <label className="block text-xs text-gray-400 mb-1">Thinking Budget（tokens）</label>
          <input
            type="number"
            value={form.thinking_budget}
            onChange={e => setForm({ ...form, thinking_budget: Math.max(1000, parseInt(e.target.value) || 10000) })}
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
            min={1000} max={100000} step={1000}
          />
        </div>
      )}
    </div>
  );
}

// ---- main page ----

type EditingState =
  | { kind: "none" }
  | { kind: "add-provider" }
  | { kind: "edit-provider"; uuid: string }
  | { kind: "add-model"; providerUuid: string }
  | { kind: "edit-model"; uuid: string; providerUuid: string };

export default function ModelsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<EditingState>({ kind: "none" });
  const [providerForm, setProviderForm] = useState<ProviderForm>(emptyProviderForm());
  const [modelForm, setModelForm] = useState<ModelForm>(emptyModelForm());
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const [provs, mods] = await Promise.all([
        fetchAPI<Provider[]>("/api/providers"),
        fetchAPI<ModelConfig[]>("/api/model-configs"),
      ]);
      setProviders(provs);
      setModels(mods);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggleExpand = (uuid: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(uuid) ? next.delete(uuid) : next.add(uuid);
      return next;
    });
  };

  const cancel = () => {
    setEditing({ kind: "none" });
    setError("");
  };

  // ---- provider actions ----

  const startAddProvider = () => {
    setProviderForm(emptyProviderForm());
    setEditing({ kind: "add-provider" });
    setError("");
  };

  const startEditProvider = (p: Provider) => {
    setProviderForm({ name: p.name, api_format: p.api_format, api_key: "", base_url: p.base_url });
    setEditing({ kind: "edit-provider", uuid: p.uuid });
    setError("");
  };

  const saveProvider = async () => {
    if (!providerForm.name.trim()) { setError("名称不能为空"); return; }
    setSaving(true); setError("");
    try {
      if (editing.kind === "add-provider") {
        if (!providerForm.api_key.trim()) { setError("API Key 不能为空"); setSaving(false); return; }
        await postAPI("/api/providers", providerForm);
      } else if (editing.kind === "edit-provider") {
        const body: Record<string, string> = { name: providerForm.name, api_format: providerForm.api_format, base_url: providerForm.base_url };
        if (providerForm.api_key.trim()) body.api_key = providerForm.api_key;
        await putAPI(`/api/providers/${editing.uuid}`, body);
      }
      setEditing({ kind: "none" });
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const deleteProvider = async (p: Provider) => {
    if (!confirm(`确定删除 Provider "${p.name}"？其下所有模型也将被删除。`)) return;
    setError("");
    try {
      await deleteAPI(`/api/providers/${p.uuid}`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  // ---- model actions ----

  const startAddModel = (providerUuid: string) => {
    setModelForm(emptyModelForm());
    setEditing({ kind: "add-model", providerUuid });
    setExpanded(prev => new Set(prev).add(providerUuid));
    setError("");
  };

  const startEditModel = (m: ModelConfig) => {
    setModelForm({
      model_id: m.model_id,
      thinking: m.thinking,
      thinking_budget: m.thinking_budget ?? 10000,
      max_tokens: m.max_tokens ?? 65536,
    });
    setEditing({ kind: "edit-model", uuid: m.uuid, providerUuid: m.provider_uuid });
    setError("");
  };

  const saveModel = async () => {
    if (!modelForm.model_id.trim()) { setError("模型 ID 不能为空"); return; }
    setSaving(true); setError("");
    try {
      if (editing.kind === "add-model") {
        await postAPI("/api/model-configs", {
          provider_uuid: editing.providerUuid,
          model_id: modelForm.model_id,
          thinking: modelForm.thinking,
          thinking_budget: modelForm.thinking_budget,
          max_tokens: modelForm.max_tokens,
        });
      } else if (editing.kind === "edit-model") {
        await putAPI(`/api/model-configs/${editing.uuid}`, {
          model_id: modelForm.model_id,
          thinking: modelForm.thinking,
          thinking_budget: modelForm.thinking_budget,
          max_tokens: modelForm.max_tokens,
        });
      }
      setEditing({ kind: "none" });
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const deleteModel = async (m: ModelConfig) => {
    if (!confirm(`确定删除模型 "${m.provider_name} / ${m.model_id}"？`)) return;
    setError("");
    try {
      await deleteAPI(`/api/model-configs/${m.uuid}`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const toggleModelEnabled = async (m: ModelConfig) => {
    setError("");
    try {
      await putAPI(`/api/model-configs/${m.uuid}`, { enabled: !m.enabled });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  // ---- helpers ----

  const modelsForProvider = (providerUuid: string) =>
    models.filter(m => m.provider_uuid === providerUuid);

  const getProviderApiFormat = (providerUuid: string) =>
    providers.find(p => p.uuid === providerUuid)?.api_format ?? "openai";

  const isEditingProvider = (uuid: string) =>
    (editing.kind === "edit-provider" && editing.uuid === uuid) ||
    (editing.kind === "add-provider");

  const isEditingModel = (uuid: string) =>
    editing.kind === "edit-model" && editing.uuid === uuid;

  const isAddingModelFor = (providerUuid: string) =>
    editing.kind === "add-model" && editing.providerUuid === providerUuid;

  if (loading) return <><Nav /><div className="max-w-5xl mx-auto px-4 py-8 text-gray-400">加载中...</div></>;

  return (
    <>
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">模型管理</h1>
          {editing.kind === "none" && (
            <button onClick={startAddProvider}
              className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white">
              + 添加 Provider
            </button>
          )}
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {/* Add-provider inline form */}
        {editing.kind === "add-provider" && (
          <div className="mb-6 rounded-lg border border-cyan-700 bg-gray-900 p-5">
            <h2 className="text-base font-semibold mb-4 text-cyan-300">新增 Provider</h2>
            <ProviderFormView form={providerForm} setForm={setProviderForm} isEdit={false} />
            <div className="flex gap-3 mt-5">
              <button onClick={saveProvider} disabled={saving}
                className="px-5 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-sm text-white disabled:opacity-50">
                {saving ? "保存中..." : "保存"}
              </button>
              <button onClick={cancel}
                className="px-5 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">
                取消
              </button>
            </div>
          </div>
        )}

        {/* Provider list */}
        <div className="space-y-4">
          {providers.length === 0 && editing.kind !== "add-provider" && (
            <p className="text-gray-500 text-center py-10">暂无 Provider，点击上方按钮添加</p>
          )}

          {providers.map(p => {
            const pModels = modelsForProvider(p.uuid);
            const isOpen = expanded.has(p.uuid);
            const editingThisProvider = isEditingProvider(p.uuid);

            return (
              <div key={p.uuid} className="rounded-lg border border-gray-700 bg-gray-900 overflow-hidden">
                {/* Provider header */}
                <div className="px-4 py-3 flex items-center justify-between gap-3">
                  <button
                    onClick={() => toggleExpand(p.uuid)}
                    className="flex items-center gap-2 flex-1 min-w-0 text-left"
                  >
                    <span className={`text-xs transition-transform ${isOpen ? "rotate-90" : ""}`}>▶</span>
                    <span className="font-semibold text-gray-100">{p.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${p.api_format === "anthropic" ? "bg-purple-500/20 text-purple-300" : "bg-cyan-500/20 text-cyan-300"}`}>
                      {p.api_format}
                    </span>
                    <span className="text-xs text-gray-500 font-mono truncate">{p.api_key_masked}</span>
                    <span className="ml-auto text-xs text-gray-500">{pModels.length} 个模型</span>
                  </button>
                  <div className="flex items-center gap-2 shrink-0">
                    <button onClick={() => startEditProvider(p)}
                      className="px-3 py-1 rounded text-xs bg-gray-700 hover:bg-gray-600 text-gray-300">
                      编辑
                    </button>
                    <button onClick={() => deleteProvider(p)}
                      className="px-3 py-1 rounded text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20">
                      删除
                    </button>
                  </div>
                </div>

                {/* Edit-provider inline form */}
                {editing.kind === "edit-provider" && editing.uuid === p.uuid && (
                  <div className="border-t border-gray-700 px-4 py-4 bg-gray-800/50">
                    <h3 className="text-sm font-semibold mb-3 text-cyan-300">编辑 Provider</h3>
                    <ProviderFormView form={providerForm} setForm={setProviderForm} isEdit={true} />
                    <div className="flex gap-3 mt-4">
                      <button onClick={saveProvider} disabled={saving}
                        className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-sm text-white disabled:opacity-50">
                        {saving ? "保存中..." : "保存"}
                      </button>
                      <button onClick={cancel}
                        className="px-4 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">
                        取消
                      </button>
                    </div>
                  </div>
                )}

                {/* Models list */}
                {isOpen && !editingThisProvider && (
                  <div className="border-t border-gray-700">
                    {pModels.map(m => (
                      <div key={m.uuid}>
                        <div className={`px-5 py-3 flex flex-col sm:flex-row sm:items-center gap-3 border-b border-gray-800 last:border-b-0 transition-opacity ${m.enabled ? "" : "opacity-50"}`}>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <ModelBadge model={m.model_id} provider={p.name} thinking={m.thinking} />
                              {!m.enabled && (
                                <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">已禁用</span>
                              )}
                            </div>
                            <div className="flex flex-wrap gap-3 mt-1 text-xs text-gray-500">
                              <span>max_tokens: {m.max_tokens}</span>
                              {m.thinking && <span>thinking_budget: {m.thinking_budget}</span>}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <button onClick={() => toggleModelEnabled(m)}
                              className={`px-3 py-1 rounded text-xs ${m.enabled ? "bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20" : "bg-green-500/10 text-green-400 hover:bg-green-500/20"}`}>
                              {m.enabled ? "禁用" : "启用"}
                            </button>
                            <button onClick={() => startEditModel(m)}
                              className="px-3 py-1 rounded text-xs bg-gray-700 hover:bg-gray-600 text-gray-300">
                              编辑
                            </button>
                            <button onClick={() => deleteModel(m)}
                              className="px-3 py-1 rounded text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20">
                              删除
                            </button>
                          </div>
                        </div>

                        {/* Edit-model inline form */}
                        {isEditingModel(m.uuid) && (
                          <div className="px-5 py-4 bg-gray-800/50 border-b border-gray-700">
                            <h4 className="text-sm font-semibold mb-3 text-cyan-300">编辑模型</h4>
                            <ModelFormView form={modelForm} setForm={setModelForm} apiFormat={p.api_format} />
                            <div className="flex gap-3 mt-4">
                              <button onClick={saveModel} disabled={saving}
                                className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-sm text-white disabled:opacity-50">
                                {saving ? "保存中..." : "保存"}
                              </button>
                              <button onClick={cancel}
                                className="px-4 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">
                                取消
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}

                    {/* Add-model inline form */}
                    {isAddingModelFor(p.uuid) && (
                      <div className="px-5 py-4 bg-gray-800/50 border-t border-gray-700">
                        <h4 className="text-sm font-semibold mb-3 text-cyan-300">添加模型</h4>
                        <ModelFormView form={modelForm} setForm={setModelForm} apiFormat={p.api_format} />
                        <div className="flex gap-3 mt-4">
                          <button onClick={saveModel} disabled={saving}
                            className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-sm text-white disabled:opacity-50">
                            {saving ? "保存中..." : "添加"}
                          </button>
                          <button onClick={cancel}
                            className="px-4 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">
                            取消
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Add model button */}
                    {!isAddingModelFor(p.uuid) && editing.kind === "none" && (
                      <div className="px-5 py-2">
                        <button onClick={() => startAddModel(p.uuid)}
                          className="text-xs text-cyan-400 hover:text-cyan-300">
                          + 添加模型
                        </button>
                      </div>
                    )}

                    {pModels.length === 0 && !isAddingModelFor(p.uuid) && (
                      <p className="px-5 py-3 text-xs text-gray-500">暂无模型</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

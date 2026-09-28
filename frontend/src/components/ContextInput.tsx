import { useState } from "react";
import { api } from "../api";

export default function ContextInput({ onRetained }: { onRetained?: () => void }) {
  const [text, setText] = useState("");
  const [category, setCategory] = useState<"shipped"|"roadmap"|"constraint"|"target_user"|"preference">("shipped");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  async function submit() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api.context(text.trim(), category);
      setFlash("Retained");
      setText("");
      onRetained?.();
      setTimeout(() => setFlash(null), 2000);
    } catch(e) { setFlash(`Failed: ${e}`); }
    finally { setBusy(false); }
  }

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold">Teach the agent</h3>
        {flash && <span className="text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5">{flash}</span>}
      </div>
      <p className="text-xs text-slate-500 mb-2">Facts, shipped features, constraints — retained for future briefs.</p>
      <textarea value={text} onChange={e => setText(e.target.value)} rows={2}
        placeholder='e.g. "We shipped a startup speed fix in v2.3"'
        className="w-full text-sm border border-slate-300 rounded px-2 py-1.5 resize-none" />
      <div className="flex items-center gap-2 mt-2">
        <select value={category} onChange={e => setCategory(e.target.value as typeof category)}
          className="text-xs border border-slate-300 rounded px-2 py-1 bg-white">
          <option value="shipped">shipped</option>
          <option value="roadmap">roadmap</option>
          <option value="constraint">constraint</option>
          <option value="target_user">target user</option>
          <option value="preference">preference</option>
        </select>
        <button onClick={submit} disabled={busy || !text.trim()}
          className="ml-auto text-xs px-3 py-1.5 bg-slate-900 text-white rounded disabled:opacity-40">
          {busy ? "Retaining…" : "Retain"}
        </button>
      </div>
    </div>
  );
}

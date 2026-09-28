import { useState } from "react";
import type { Recommendation } from "../types";
import { api } from "../api";

export default function BriefPanel({ batch, summary, recommendations, memoryEnabled, onFeedback }:{
  batch: number; summary: string; recommendations: Recommendation[];
  memoryEnabled: boolean; onFeedback?: () => void;
}) {
  const [active, setActive] = useState<{id:string;decision:"accepted"|"rejected"|"edited"}|null>(null);
  const [reason, setReason] = useState("");
  const [sent, setSent] = useState<Record<string,"accepted"|"rejected"|"edited">>({});
  const [busy, setBusy] = useState(false);

  async function submit(rec: Recommendation, d: "accepted"|"rejected"|"edited") {
    if (!reason.trim()) return;
    setBusy(true);
    try {
      await api.feedback(rec.title, d, reason.trim(), batch);
      setSent(s => ({ ...s, [rec.id]: d }));
      setActive(null); setReason(""); onFeedback?.();
    } catch(e) { alert(`Feedback failed: ${e}`); }
    finally { setBusy(false); }
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-semibold">What to build next</h2>
        <span className={`text-[10px] uppercase rounded px-2 py-0.5 border ${
          memoryEnabled ? "bg-amber-50 text-amber-800 border-amber-200"
                       : "bg-slate-100 text-slate-500 border-slate-200"}`}>
          memory {memoryEnabled ? "on" : "off"}
        </span>
      </div>
      <p className="text-sm text-slate-600 mb-4">{summary}</p>
      <ol className="space-y-3">
        {recommendations.map((rec, i) => {
          const decided = sent[rec.id];
          return (
            <li key={rec.id} className="border border-slate-200 rounded-md p-3 bg-slate-50/50">
              <div className="flex items-start gap-3">
                <span className="text-xs font-mono text-slate-400 mt-1">#{i+1}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-medium">{rec.title}</h3>
                    <span className="text-xs font-mono bg-indigo-50 text-indigo-700 rounded px-1.5 py-0.5">
                      {rec.score.toFixed(2)}
                    </span>
                    {decided && (
                      <span className={`text-[10px] uppercase rounded px-1.5 py-0.5 border ${
                        decided==="accepted" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : decided==="rejected" ? "bg-rose-50 text-rose-700 border-rose-200"
                        : "bg-slate-100 text-slate-600 border-slate-200"}`}>{decided}</span>
                    )}
                  </div>
                  <p className="text-sm text-slate-700 mt-1">{rec.action}</p>
                  <p className="text-xs text-slate-500 mt-1">{rec.rationale}</p>
                  {memoryEnabled && rec.memory_citations.length > 0 && (
                    <div className="mt-2 text-[11px]">
                      <span className="text-amber-800 bg-amber-100 rounded px-1.5 py-0.5 font-medium">
                        {rec.memory_citations.length} memory citation(s)
                      </span>
                    </div>
                  )}
                  {!decided && (
                    <div className="flex gap-2 mt-2">
                      {(["accepted","rejected","edited"] as const).map(d => (
                        <button key={d} onClick={() => { setActive({ id: rec.id, decision: d }); setReason(""); }}
                          className={`text-xs px-2.5 py-1 rounded border ${
                            active?.id===rec.id && active.decision===d
                              ? "bg-slate-900 text-white border-slate-900"
                              : "bg-white text-slate-700 border-slate-300 hover:border-slate-400"}`}>
                          {d}
                        </button>
                      ))}
                    </div>
                  )}
                  {active?.id === rec.id && !decided && (
                    <div className="mt-2 flex gap-2">
                      <input autoFocus value={reason} onChange={e => setReason(e.target.value)}
                        placeholder={`Why ${active.decision}? (retained to memory)`}
                        className="flex-1 text-xs border border-slate-300 rounded px-2 py-1.5"
                        onKeyDown={e => { if (e.key==="Enter" && reason.trim() && !busy) submit(rec, active.decision); }} />
                      <button disabled={busy || !reason.trim()} onClick={() => submit(rec, active.decision)}
                        className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded disabled:opacity-40">
                        {busy ? "…" : "Send"}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

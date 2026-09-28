import type { MemoryItem } from "../types";

export default function ProfileView({ profile, timeline, loading, onRefresh }:{
  profile: string; timeline: MemoryItem[]; loading: boolean; onRefresh: () => void;
}) {
  const color: Record<string,string> = {
    analysis: "bg-indigo-100 text-indigo-700",
    product_context: "bg-sky-100 text-sky-700",
    pm_decision: "bg-amber-100 text-amber-800",
    analysis_names: "bg-violet-100 text-violet-700",
    analysis_stats: "bg-teal-100 text-teal-700",
  };
  return (
    <div className="space-y-4">
      <div className="card p-5">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold">What the agent has learned</h2>
          <button onClick={onRefresh} disabled={loading}
            className="text-xs px-2.5 py-1 border border-slate-300 rounded hover:bg-slate-50 disabled:opacity-50">
            {loading ? "Reflecting…" : "Refresh"}
          </button>
        </div>
        <div className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
          {profile || <span className="text-slate-400 italic">Run analyses and give feedback, then refresh.</span>}
        </div>
      </div>
      <div className="card p-5">
        <h3 className="font-semibold mb-3">Memory timeline · {timeline.length} entries</h3>
        <ol className="relative border-l border-slate-200 ml-2 space-y-4">
          {timeline.map((m,i) => (
            <li key={m.id ?? i} className="pl-4 relative">
              <span className="absolute -left-[5px] top-2 w-2.5 h-2.5 rounded-full bg-white border-2 border-slate-400" />
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${color[m.type] ?? "bg-slate-100 text-slate-600"}`}>
                  {m.type.replace(/_/g," ")}
                </span>
                {m.date && <span className="text-[10px] font-mono text-slate-400">{m.date.slice(0,10)}</span>}
              </div>
              <p className="text-xs text-slate-600 line-clamp-2 break-words">{m.snippet}</p>
            </li>
          ))}
          {timeline.length === 0 && (
            <li className="pl-4 text-xs text-slate-400 italic">No memories retained yet.</li>
          )}
        </ol>
      </div>
    </div>
  );
}

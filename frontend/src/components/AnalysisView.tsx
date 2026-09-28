import type { AnalysisResult } from "../types";
import BriefPanel from "./BriefPanel";

export default function AnalysisView({ analysis, onFeedback }:{
  analysis: AnalysisResult; onFeedback: () => void;
}) {
  return (
    <div className="space-y-6">
      {analysis.warning && (
        <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          {analysis.warning}
        </div>
      )}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-3">
          Themes · batch {analysis.batch} · {analysis.date}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {analysis.themes.map(t => (
            <div key={t.id} className="card p-4">
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="min-w-0">
                  <h3 className="font-semibold truncate">{t.name}</h3>
                  <p className="text-sm text-slate-600 line-clamp-2">{t.summary}</p>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-lg font-semibold font-mono">{t.score.toFixed(2)}</div>
                  <div className={`text-[10px] uppercase border rounded px-1.5 py-0.5 mt-1 ${
                    t.trend==="up" ? "bg-rose-50 text-rose-700 border-rose-200"
                    : t.trend==="down" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                    : t.trend==="new" ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                    : "bg-slate-100 text-slate-600 border-slate-200"}`}>
                    {t.trend ?? "new"}
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-500 mb-2">
                <span>{t.frequency} reviews</span>
                <span>sentiment {t.sentiment_score.toFixed(2)}</span>
              </div>
              <div className="space-y-1">
                {Object.entries(t.score_breakdown).map(([k,v]) => (
                  <div key={k} className="flex items-center gap-2 text-xs">
                    <span className="w-28 text-slate-500 shrink-0">{k.replace(/_/g," ")}</span>
                    <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.min(100,v*100)}%` }} />
                    </div>
                    <span className="w-10 text-right font-mono">{v.toFixed(2)}</span>
                  </div>
                ))}
              </div>
              {t.evidence.length > 0 && (
                <ul className="mt-2 border-t border-slate-100 pt-2 space-y-1">
                  {t.evidence.slice(0,2).map((q,i) => (
                    <li key={i} className="text-xs text-slate-500 italic line-clamp-1">"{q}"</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </div>
      <BriefPanel batch={analysis.batch} summary={analysis.brief.summary}
        recommendations={analysis.brief.recommendations}
        memoryEnabled={analysis.memory_enabled} onFeedback={onFeedback} />
    </div>
  );
}

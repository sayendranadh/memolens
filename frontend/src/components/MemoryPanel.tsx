import { useEffect, useState } from "react";
import type { RecallLog } from "../types";
import { api } from "../api";
import { purposeLabel } from "../lib/time";

export default function MemoryPanel({ refreshKey }: { refreshKey: number }) {
  const [recalls, setRecalls] = useState<RecallLog[]>([]);
  const [open, setOpen] = useState<Record<number, boolean>>({});

  useEffect(() => {
    api.recalls(30).then(r => setRecalls(r.recalls)).catch(() => {});
  }, [refreshKey]);

  const totalHits = recalls.reduce((n, r) => n + r.result_count, 0);
  const recent = [...recalls].reverse().slice(0, 20);

  return (
    <aside className="card p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="font-semibold flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
            Memory panel
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">Live recalls</p>
        </div>
        <span className="text-xs font-mono bg-amber-50 text-amber-800 border border-amber-200 rounded px-2 py-1">
          {totalHits} hits
        </span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {recent.length === 0 && (
          <p className="text-sm text-slate-400 italic py-8 text-center">
            No recalls yet. Run an analysis.
          </p>
        )}
        {recent.map((log, i) => {
          const isOpen = open[i] ?? false;
          return (
            <div key={i} className="border border-amber-200 bg-amber-50/60 rounded-md">
              <button
                onClick={() => setOpen(o => ({ ...o, [i]: !isOpen }))}
                className="w-full text-left px-3 py-2 hover:bg-amber-100/60 rounded-md"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-amber-900">
                    {purposeLabel(log.purpose)}
                  </span>
                  <span className="text-[10px] font-mono text-amber-700">
                    {log.result_count} · {log.latency_ms}ms
                  </span>
                </div>
                <p className="text-xs text-slate-600 mt-1 line-clamp-2">
                  "{log.query}"
                </p>
              </button>
              {isOpen && (
                <div className="px-3 pb-3 space-y-2 border-t border-amber-200 pt-2">
                  {log.results.slice(0, 5).map((r, j) => (
                    <div key={j} className="text-xs bg-white border border-slate-200 rounded p-2">
                      <p className="text-slate-700 line-clamp-3 break-words">
                        {r.text.slice(0, 220)}{r.text.length > 220 ? "…" : ""}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}

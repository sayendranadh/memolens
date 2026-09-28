import type { AnalysisResult, Recommendation } from "../types";

function keyOf(r: Recommendation): string {
  return (r.theme_key || r.title.trim().toLowerCase()).trim();
}

function Column({
  title, recs, other, side,
}: {
  title: string;
  recs: Recommendation[];
  other: Recommendation[];
  side: "off" | "on";
}) {
  const otherKeys = new Set(other.map(keyOf));
  return (
    <div className="card p-4">
      <h3 className="font-semibold mb-3 flex items-center gap-2">
        {title}
        <span className={`text-[10px] uppercase rounded px-1.5 py-0.5 border ${
          side === "off"
            ? "bg-slate-100 text-slate-500 border-slate-200"
            : "bg-amber-50 text-amber-800 border-amber-200"
        }`}>
          {side === "off" ? "baseline" : "memory"}
        </span>
      </h3>
      <ol className="space-y-2">
        {recs.map((r, i) => {
          const onlyHere = !otherKeys.has(keyOf(r));
          const hl =
            onlyHere && side === "off"
              ? "border-rose-300 bg-rose-50"
              : onlyHere && side === "on"
              ? "border-emerald-300 bg-emerald-50"
              : "border-slate-200 bg-white";
          return (
            <li key={r.id} className={`border rounded-md p-3 ${hl}`}>
              <div className="flex items-center justify-between gap-2 text-xs font-mono text-slate-400">
                <span>#{i + 1}</span>
                <span
                  className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600"
                  title="theme key (used for matching across conditions)"
                >
                  {keyOf(r)}
                </span>
                <span>{r.score.toFixed(2)}</span>
              </div>
              <p className="font-medium text-sm mt-1">{r.title}</p>
              <p className="text-xs text-slate-600 mt-0.5 line-clamp-2">
                {r.action}
              </p>
              {r.memory_citations.length > 0 && (
                <p className="mt-1 text-[10px] text-amber-800 bg-amber-100 inline-block rounded px-1.5 py-0.5">
                  {r.memory_citations.length} citations
                </p>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function CompareView({
  off, on,
}: {
  batch: number;
  off: AnalysisResult;
  on: AnalysisResult;
}) {
  const offKeys = off.brief.recommendations.map(keyOf);
  const onKeys = on.brief.recommendations.map(keyOf);
  const added = onKeys.filter((k) => !offKeys.includes(k)).length;
  const suppressed = offKeys.filter((k) => !onKeys.includes(k)).length;

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <h2 className="font-semibold mb-1">Same batch, two minds</h2>
        <p className="text-sm text-slate-600">
          Identical input. Memory OFF vs ON. Cards are matched by{" "}
          <span className="font-mono text-xs bg-slate-100 px-1 rounded">
            theme_key
          </span>{" "}
          so a rewording of the same theme doesn't count as a change.
        </p>
        <div className="flex gap-4 mt-3 text-xs">
          <span className="text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-1">
            {added} newly surfaced
          </span>
          <span className="text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-1">
            {suppressed} suppressed
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Column
          title="Memory OFF"
          recs={off.brief.recommendations}
          other={on.brief.recommendations}
          side="off"
        />
        <Column
          title="Memory ON"
          recs={on.brief.recommendations}
          other={off.brief.recommendations}
          side="on"
        />
      </div>

      <div className="card p-4 grid grid-cols-3 gap-3 text-center text-xs">
        <div className="bg-slate-50 rounded p-2">
          <div className="text-lg font-semibold">
            {off.recalled_memories.length}
          </div>
          <div className="text-slate-500">OFF recalls</div>
        </div>
        <div className="bg-amber-50 rounded p-2">
          <div className="text-lg font-semibold text-amber-900">
            {on.recalled_memories.length}
          </div>
          <div className="text-amber-700">ON recalls</div>
        </div>
        <div className="bg-slate-50 rounded p-2">
          <div className="text-lg font-semibold">
            {on.brief.recommendations.reduce(
              (n, r) => n + r.memory_citations.length, 0
            )}
          </div>
          <div className="text-slate-500">brief citations</div>
        </div>
      </div>
    </div>
  );
}

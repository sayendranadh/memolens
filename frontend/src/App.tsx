import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { AnalysisResult, CompareResult, MemoryItem } from "./types";
import AnalysisView from "./components/AnalysisView";
import CompareView from "./components/CompareView";
import ProfileView from "./components/ProfileView";
import MemoryPanel from "./components/MemoryPanel";
import ContextInput from "./components/ContextInput";

type Tab = "analysis" | "compare" | "profile";

export default function App() {
  const [tab, setTab] = useState<Tab>("analysis");
  const [batch, setBatch] = useState<1 | 2 | 3>(1);
  const [memory, setMemory] = useState(true);
  const [analyses, setAnalyses] = useState<Record<number, AnalysisResult>>({});
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState("");
  const [timeline, setTimeline] = useState<MemoryItem[]>([]);
  const [profileLoading, setProfileLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [demoStep, setDemoStep] = useState<string | null>(null);

  const current = analyses[batch];

  const refreshProfile = useCallback(async () => {
    setProfileLoading(true);
    try {
      const [p, t] = await Promise.all([api.profile(), api.timeline(200)]);
      setProfile(p.profile);
      setTimeline(t.items);
    } catch (e) {
      setProfile(`Failed: ${e}`);
    } finally {
      setProfileLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  async function runAnalysis(b: 1 | 2 | 3, m: boolean) {
    setLoading(true);
    setError(null);
    try {
      const r = await api.analyze(b, m);
      setAnalyses((p) => ({ ...p, [b]: r }));
      setBatch(b);
      setMemory(m);
      setRefreshKey((k) => k + 1);
      // Hindsight indexes retained memories asynchronously. Without this
      // wait, the next manual Analyze won't see this batch's stats and
      // every theme will report trend="new".
      if (m) {
        setDemoStep("Indexing memories (~12s)…");
        await new Promise((res) => setTimeout(res, 12000));
        setDemoStep(null);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function runCompare(b: 1 | 2 | 3) {
    setLoading(true);
    setError(null);
    try {
      const r = await api.compare(b);
      setCompare(r);
      setAnalyses((p) => ({ ...p, [b]: r.memory_on }));
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function runDemo() {
    setError(null);
    try {
      setDemoStep("Resetting bank…");
      try { await api.reset(); } catch { /* reset disabled — continue */ }

      setDemoStep("Session 1 · analyzing batch 1 (cold)…");
      const a1 = await api.analyze(1, true);
      setAnalyses((p) => ({ ...p, 1: a1 }));
      setBatch(1);
      setMemory(true);

      setDemoStep("Session 1 · PM feedback (reject dark mode, accept sync)…");
      await api.feedback("Add dark mode", "rejected",
        "Enterprise customers only — theming is a distraction", 1);
      await api.feedback("Fix sync bugs", "accepted",
        "Top complaint from paying users", 1);
      await api.context("Shipped startup speed fix in v2.3 on 2026-09-01", "shipped");

      setDemoStep("Waiting for indexing…");
      await new Promise((r) => setTimeout(r, 12000));

      setDemoStep("Session 2 · analyzing batch 2 (memory warm)…");
      const a2 = await api.analyze(2, true);
      setAnalyses((p) => ({ ...p, 2: a2 }));

      setDemoStep("Session 3 · analyzing batch 3 (two sessions of history)…");
      const a3 = await api.analyze(3, true);
      setAnalyses((p) => ({ ...p, 3: a3 }));

      setDemoStep("Session 3 · memory OFF vs ON comparison…");
      const cmp = await api.compare(3);
      setCompare(cmp);

      setDemoStep("Reflecting profile…");
      await refreshProfile();

      setBatch(3);
      setTab("analysis");
      setRefreshKey((k) => k + 1);
      setDemoStep(null);
    } catch (e) {
      setError(`Demo failed: ${e}`);
      setDemoStep(null);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            <h1 className="font-semibold">MemoLens</h1>
            <span className="text-xs text-slate-400 hidden sm:inline">
              feedback synthesizer with memory
            </span>
          </div>
          <button
            onClick={runDemo}
            disabled={!!demoStep}
            className="ml-auto text-xs px-3 py-1.5 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 font-medium"
          >
            {demoStep ? "Running…" : "▶ Run 3-session demo"}
          </button>
        </div>
        {demoStep && (
          <div className="bg-indigo-50 border-t border-indigo-100 text-xs text-indigo-800 px-6 py-1.5">
            {demoStep}
          </div>
        )}
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-5 grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-5">
        <section className="space-y-5 min-w-0">
          <div className="flex items-center gap-2">
            {([
              ["analysis", "Analysis"],
              ["compare", "Before / After"],
              ["profile", "Learned profile"],
            ] as const).map(([k, label]) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                className={`text-sm px-3 py-1.5 rounded-md border ${
                  tab === k
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white text-slate-700 border-slate-200 hover:border-slate-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "analysis" && (
            <div className="card p-3 flex flex-wrap items-center gap-3">
              <span className="text-xs font-medium text-slate-500">Batch</span>
              {[1, 2, 3].map((b) => (
                <button
                  key={b}
                  onClick={() => setBatch(b as 1 | 2 | 3)}
                  className={`text-xs px-2.5 py-1 rounded border ${
                    batch === b
                      ? "bg-slate-900 text-white border-slate-900"
                      : "bg-white border-slate-300 text-slate-700"
                  }`}
                >
                  {b}
                </button>
              ))}
              <span className="text-xs font-medium text-slate-500 ml-2">Memory</span>
              <button
                onClick={() => setMemory((m) => !m)}
                className={`text-xs px-2.5 py-1 rounded border ${
                  memory
                    ? "bg-amber-500 text-white border-amber-500"
                    : "bg-white border-slate-300 text-slate-700"
                }`}
              >
                {memory ? "ON" : "OFF"}
              </button>
              <button
                onClick={() => runAnalysis(batch, memory)}
                disabled={loading}
                className="ml-auto text-xs px-3 py-1.5 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
              >
                {loading ? "Analyzing…" : "Analyze"}
              </button>
            </div>
          )}

          {tab === "compare" && (
            <div className="card p-3 flex items-center gap-3">
              <span className="text-xs font-medium text-slate-500">Batch</span>
              {[1, 2, 3].map((b) => (
                <button
                  key={b}
                  onClick={() => runCompare(b as 1 | 2 | 3)}
                  disabled={loading}
                  className={`text-xs px-2.5 py-1 rounded border ${
                    compare?.memory_on.batch === b
                      ? "bg-slate-900 text-white border-slate-900"
                      : "bg-white border-slate-300 text-slate-700"
                  }`}
                >
                  Compare {b}
                </button>
              ))}
              <span className="text-[11px] text-slate-400 ml-auto">
                Runs same batch twice: OFF, then ON
              </span>
            </div>
          )}

          {error && (
            <div className="card p-3 border-rose-200 bg-rose-50 text-sm text-rose-800">
              {error}
            </div>
          )}

          {tab === "analysis" && (current ? (
            <AnalysisView
              analysis={current}
              onFeedback={() => setRefreshKey((k) => k + 1)}
            />
          ) : (
            <div className="card p-10 text-center">
              <p className="text-slate-500">No analysis yet.</p>
              <p className="text-xs text-slate-400 mt-1">
                Click Analyze, or run the 3-session demo.
              </p>
            </div>
          ))}

          {tab === "compare" && (compare ? (
            <CompareView
              batch={compare.memory_on.batch}
              off={compare.memory_off}
              on={compare.memory_on}
            />
          ) : (
            <div className="card p-10 text-center">
              <p className="text-slate-500">No comparison yet.</p>
              <p className="text-xs text-slate-400 mt-1">
                Pick a batch, or run the demo.
              </p>
            </div>
          ))}

          {tab === "profile" && (
            <ProfileView
              profile={profile}
              timeline={timeline}
              loading={profileLoading}
              onRefresh={refreshProfile}
            />
          )}

          {tab !== "profile" && (
            <ContextInput onRetained={() => setRefreshKey((k) => k + 1)} />
          )}
        </section>

        <MemoryPanel refreshKey={refreshKey} />
      </main>
    </div>
  );
}

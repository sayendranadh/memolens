export type Theme = {
  id: string; name: string; summary: string; frequency: number;
  sentiment_score: number; trend: string | null; evidence: string[];
  score: number; score_breakdown: Record<string, number>;
};
export type Recommendation = {
  id: string; title: string; action: string; rationale: string;
  evidence: string[]; score: number; score_breakdown: Record<string, number>;
  source_theme_id: string; memory_citations: string[];
};
export type Brief = {
  batch: number; date: string; summary: string; recommendations: Recommendation[];
  generated_with_memory: boolean; pm_preferences_applied: string[];
};
export type RecalledMemory = {
  purpose: string; query: string; text: string;
  score: number | null; metadata: Record<string, unknown> | null;
};
export type AnalysisResult = {
  batch: number; memory_enabled: boolean; date: string;
  themes: Theme[]; brief: Brief; recalled_memories: RecalledMemory[];
  cached: boolean; warning: string | null;
};
export type MemoryItem = { id: string | null; date: string; type: string; snippet: string };
export type RecallLog = {
  ts: string; purpose: string; query: string; bank_id: string;
  result_count: number; latency_ms: number;
  results: Array<{ text: string; score: number | null; metadata: unknown }>;
};
export type CompareResult = { memory_off: AnalysisResult; memory_on: AnalysisResult };

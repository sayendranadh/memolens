import type { AnalysisResult, CompareResult, MemoryItem, RecallLog } from "./types";
const BASE = (import.meta.env.VITE_API_URL as string) ?? "http://localhost:8000";
async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? ` — ${body}` : ""}`);
  }
  return res.json() as Promise<T>;
}
export const api = {
  analyze: (batch: number, memory: boolean) =>
    req<AnalysisResult>("/analyze", { method: "POST", body: JSON.stringify({ batch, memory }) }),
  feedback: (id: string, decision: "accepted"|"rejected"|"edited", reason: string, batch: number) =>
    req<{ok:boolean}>( "/feedback", { method: "POST", body: JSON.stringify({ recommendation_id: id, decision, reason, batch }) }),
  context: (text: string, category: string) =>
    req<{ok:boolean}>("/context", { method: "POST", body: JSON.stringify({ text, category }) }),
  profile: () => req<{profile:string}>("/memory/profile"),
  timeline: (limit=100) => req<{items:MemoryItem[]}>("/memory/timeline?limit="+limit),
  recalls: (limit=30) => req<{recalls:RecallLog[]}>("/memory/recalls?limit="+limit),
  compare: (batch: number) => req<CompareResult>("/compare", { method: "POST", body: JSON.stringify({ batch }) }),
  reset: () => req<{ok:boolean;message?:string}>("/reset", { method: "POST", headers: { "X-Confirm-Reset": "yes" } }),
};

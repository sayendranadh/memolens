export function relativeTime(dateStr: string): string {
  const t = new Date(dateStr).getTime();
  if (Number.isNaN(t)) return "";
  const days = Math.floor((Date.now() - t) / 86400000);
  if (days < 1) return "today";
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days/7)}w ago`;
  return `${Math.floor(days/30)}mo ago`;
}
export function purposeLabel(p: string): string {
  return ({
    theme_labeling: "Theme naming",
    scoring_trends: "Trend scoring",
    prior_frequencies: "Prior frequencies",
    brief_shipped_and_context: "Product context",
    brief_rejected_ideas: "Rejected ideas",
    brief_pm_preferences: "PM preferences",
  } as Record<string,string>)[p] ?? p.replace(/_/g," ");
}

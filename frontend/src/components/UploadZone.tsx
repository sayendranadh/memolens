import { useState } from "react";
import { api } from "../api";

export type UploadInfo = {
  upload_id: string;
  n_reviews: number;
};

export default function UploadZone({
  onUploaded,
}: {
  onUploaded: (info: UploadInfo) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      const info = await api.upload(file);
      setFlash(`Uploaded ${info.n_reviews} reviews`);
      onUploaded(info);
      setTimeout(() => setFlash(null), 3000);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f) handleFile(f);
      }}
      className={`card p-3 border-2 border-dashed transition ${
        dragging
          ? "border-indigo-400 bg-indigo-50"
          : "border-slate-300 bg-white"
      }`}
    >
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs font-medium text-slate-500">
          Upload your own reviews
        </span>
        <label className="text-xs px-2.5 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:border-slate-400 cursor-pointer">
          {busy ? "Uploading…" : "Choose file"}
          <input
            type="file"
            accept=".json,.jsonl,.csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
              e.target.value = "";
            }}
            disabled={busy}
          />
        </label>
        <span className="text-[11px] text-slate-400">
          or drag a .json / .jsonl / .csv here
        </span>
        {flash && (
          <span className="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-0.5 ml-auto">
            {flash}
          </span>
        )}
        {error && (
          <span className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-0.5 ml-auto">
            {error.slice(0, 120)}
          </span>
        )}
      </div>
      <p className="text-[11px] text-slate-400 mt-2">
        Fields: text (required), rating 1-5 (optional), id, date. Extra
        fields ignored. Uploads live in-memory and are cleared on restart.
      </p>
    </div>
  );
}

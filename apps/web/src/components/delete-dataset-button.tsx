"use client";

import { useState } from "react";
import { LoaderCircle, Trash2 } from "lucide-react";
import { api } from "@/lib/api";

export function DeleteDatasetButton({
  datasetId,
  datasetName,
  onDeleted,
}: {
  datasetId: string;
  datasetName: string;
  onDeleted: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  async function removeDataset() {
    if (!window.confirm(`Delete “${datasetName}”? This permanently removes the uploaded file, processed versions, and analytics for this dataset.`)) return;
    setDeleting(true);
    setError("");
    try {
      await api<void>(`/datasets/${datasetId}`, { method: "DELETE" });
      onDeleted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this dataset.");
    } finally {
      setDeleting(false);
    }
  }

  return <span className="delete-dataset-wrap">
    <button className="delete-dataset-button" type="button" onClick={() => void removeDataset()} disabled={deleting} aria-label={`Delete ${datasetName}`} title={`Delete ${datasetName}`}>
      {deleting ? <LoaderCircle className="spin" size={15}/> : <Trash2 size={15}/>}
      <span>{deleting ? "Deleting…" : "Delete"}</span>
    </button>
    {error && <span className="delete-dataset-error" role="alert">{error}</span>}
  </span>;
}

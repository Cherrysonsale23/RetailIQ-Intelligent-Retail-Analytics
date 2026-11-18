
"use client";

import { useState } from "react";
import { ArrowLeft, Check, RefreshCw } from "lucide-react";
import Link from "next/link";

const DEFAULT_DATASET =
  "https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store";

export function KaggleImport() {
  const [datasetUrl, setDatasetUrl] = useState(DEFAULT_DATASET);
  const [message, setMessage] = useState("");

  function previewDemo() {
    if (!datasetUrl.trim()) {
      setMessage("Please enter a Kaggle dataset URL.");
      return;
    }

    setMessage(
      "Demo mode: Dataset URL accepted for preview. No request was sent to Kaggle or any server."
    );
  }

  return (
    <div>
      <Link href="/datasets" className="back-link">
        <ArrowLeft size={15} /> Back to datasets
      </Link>

      <div className="page-heading upload-heading">
        <div>
          <div className="eyebrow">KAGGLE SOURCE</div>
          <h1>Import large CSVs</h1>
          <p>
            Preview the Kaggle import experience locally. Demo mode does not
            download files or connect to external services.
          </p>
        </div>
      </div>

      <div className="upload-card kaggle-source-form">
        <label htmlFor="kaggle-url">Kaggle dataset URL</label>

        <div className="kaggle-url-row">
          <input
            id="kaggle-url"
            value={datasetUrl}
            onChange={(event) => setDatasetUrl(event.target.value)}
            placeholder="https://www.kaggle.com/datasets/owner/dataset-slug"
          />

          <button
            className="button-secondary"
            type="button"
            onClick={previewDemo}
          >
            <RefreshCw size={14} /> Preview demo
          </button>
        </div>

        {message && (
          <div className="privacy-note" role="status">
            <Check size={15} /> {message}
          </div>
        )}

        <div className="upload-actions">
          <span>No files are downloaded, imported, or stored.</span>
        </div>
      </div>

      <div className="kaggle-storage-note">
        <b>How this demo works</b>
        <p>
          In the original application, a background worker downloads and
          analyzes CSV files from Kaggle. This demonstration keeps that
          functionality disabled to protect the original hosted project.
        </p>
        <p>
          No Kaggle API, backend worker, Supabase storage, or external
          database is contacted.
        </p>
      </div>
    </div>
  );
}

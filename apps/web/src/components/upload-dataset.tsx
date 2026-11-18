
"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { ArrowLeft, Check, FileUp, UploadCloud, X } from "lucide-react";
import Link from "next/link";

type AnalysisResult = {
  originalTransactions: number;
  cleanedTransactions: number;
  totalCustomers: number;
  totalRevenue: number;
  numberOfClusters: number;
  silhouetteScore: number;
  segments: {
    cluster: number;
    name: string;
    customers: number;
    averageRecency: number;
    averageFrequency: number;
    averageMonetary: number;
  }[];
};

type UploadResult = {
  message: string;
  filename: string;
  rows: number;
  columns: number;
  column_names: string[];
  preview: Record<string, unknown>[];
  analysis: AnalysisResult;
};

export function UploadDataset() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [drag, setDrag] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

  function choose(candidate?: File) {
    if (!candidate) return;

    setMessage("");
    setResult(null);

    if (!candidate.name.toLowerCase().endsWith(".csv")) {
      setMessage("Please choose a CSV file.");
      return;
    }

    if (candidate.size === 0) {
      setMessage("This file is empty.");
      return;
    }

    if (candidate.size > 100 * 1024 * 1024) {
      setMessage("Please choose a CSV file smaller than 100 MB.");
      return;
    }

    setFile(candidate);
    setProgress(0);
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDrag(false);
    choose(event.dataTransfer.files[0]);
  }

  async function submit() {
    if (!file || loading) return;

    setLoading(true);
    setProgress(0);
    setMessage("");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch("http://127.0.0.1:8002/upload-csv", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Upload failed.");
      }

      setResult(data);
      setProgress(100);
      setMessage("CSV uploaded and processed successfully!");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not connect to the local API."
      );
    } finally {
      setLoading(false);
    }
  }

  const onInput = (event: ChangeEvent<HTMLInputElement>) => {
    choose(event.target.files?.[0]);
  };

  return (
    <div>
      <Link href="/datasets" className="back-link">
        <ArrowLeft size={15} /> Back to datasets
      </Link>

      <div className="page-heading upload-heading">
        <div>
          <div className="eyebrow">ADD DATA</div>
          <h1>Upload a dataset</h1>
          <p>
            Select a CSV file to upload and process using your local
            machine-learning API.
          </p>
        </div>

        <Link className="button-secondary" href="/datasets/kaggle">
          Large public Kaggle files? Import directly
        </Link>
      </div>

      <div className="upload-layout">
        <div className="upload-card">
          <div
            className={`dropzone ${drag ? "dragging" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={drop}
            onClick={() => input.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter") input.current?.click();
            }}
          >
            <input
              ref={input}
              type="file"
              accept=".csv,text/csv"
              hidden
              onChange={onInput}
            />
            <div className="drop-icon">
              <UploadCloud size={22} />
            </div>
            <b>Drag and drop your CSV here</b>
            <span>
              or <u>browse files</u>
            </span>
            <small>CSV only · Local API upload</small>
          </div>

          {file && (
            <div className="selected-file">
              <span className="file-icon">
                <FileUp size={17} />
              </span>
              <div>
                <b>{file.name}</b>
                <small>{(file.size / 1024 / 1024).toFixed(2)} MB</small>
              </div>
              <button
                aria-label="Remove file"
                className="remove-file"
                disabled={loading}
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                  setProgress(0);
                  setMessage("");
                  setResult(null);
                  if (input.current) input.current.value = "";
                }}
              >
                <X size={16} />
              </button>
            </div>
          )}

          {progress > 0 && (
            <div
              className="progress-track"
              role="progressbar"
              aria-label="Upload progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
            >
              <div style={{ width: `${progress}%` }} />
            </div>
          )}

          {message && (
            <div className="privacy-note" role="status">
              {message}
            </div>
          )}

          <div className="upload-actions">
            <button
              className="button-primary"
              disabled={!file || loading}
              onClick={submit}
            >
              <FileUp size={15} />
              {loading ? "Processing..." : "Upload CSV"}
            </button>
            <span>Sent to your local API only.</span>
          </div>

          {result && (
            <>
              <div className="privacy-note">
                <Check size={15} />
                {result.filename}: {result.rows.toLocaleString()} rows
                and {result.columns} columns received.
              </div>

              <h3>CSV details</h3>
              <p><b>Rows:</b> {result.rows.toLocaleString()}</p>
              <p><b>Columns:</b> {result.column_names.join(", ")}</p>

              <h3>Machine Learning Results</h3>

              <div className="analysis-results">
                <p>
                  <b>Original transactions:</b>{" "}
                  {result.analysis.originalTransactions.toLocaleString()}
                </p>
                <p>
                  <b>Cleaned transactions:</b>{" "}
                  {result.analysis.cleanedTransactions.toLocaleString()}
                </p>
                <p>
                  <b>Total customers:</b>{" "}
                  {result.analysis.totalCustomers.toLocaleString()}
                </p>
                <p>
                  <b>Total revenue:</b>{" "}
                  {result.analysis.totalRevenue.toLocaleString("en-IN", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </p>
                <p>
                  <b>Number of clusters:</b>{" "}
                  {result.analysis.numberOfClusters}
                </p>
                <p>
                  <b>Silhouette score:</b>{" "}
                  {result.analysis.silhouetteScore}
                </p>
              </div>

              <h3>Customer Segments</h3>

              {result.analysis.segments.map((segment) => (
                <div key={segment.cluster} className="privacy-note">
                  <b>{segment.name}</b>
                  <p>Customers: {segment.customers.toLocaleString()}</p>
                  <p>Average Recency: {segment.averageRecency} days</p>
                  <p>Average Frequency: {segment.averageFrequency}</p>
                  <p>Average Monetary: {segment.averageMonetary}</p>
                </div>
              ))}

              <h3>First five rows</h3>
              <pre style={{ overflowX: "auto", whiteSpace: "pre-wrap" }}>
                {JSON.stringify(result.preview, null, 2)}
              </pre>
            </>
          )}
        </div>

        <aside className="upload-info">
          <h3>What happens next</h3>
          <ol>
            <li>
              <i>1</i>
              <span>
                <b>Validate</b>
                <small>Check the uploaded CSV structure and headers.</small>
              </span>
            </li>
            <li>
              <i>2</i>
              <span>
                <b>Profile</b>
                <small>Read rows, columns, and a data preview.</small>
              </span>
            </li>
            <li>
              <i>3</i>
              <span>
                <b>Analyze</b>
                <small>Calculate RFM features and perform K-Means clustering.</small>
              </span>
            </li>
          </ol>

          <div className="privacy-note">
            <Check size={15} /> Local API only
          </div>

          <p className="upload-plan-note">
            The CSV is processed by the local API running on your computer.
            It is not sent to your friend's Supabase project.
          </p>
        </aside>
      </div>
    </div>
  );
}


"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, Database, FileUp, RefreshCw } from "lucide-react";

type Segment = {
  cluster: number;
  customers: number;
  averageRecency: number;
  averageFrequency: number;
  averageMonetary: number;
};

type AnalysisData = {
  dataset: string;
  totalCustomers: number;
  totalRevenue: number;
  originalTransactions: number;
  cleanedTransactions: number;
  numberOfClusters: number;
  silhouetteScore: number;
  segments: Segment[];
};

export function DatasetLibrary() {
  const [data, setData] = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await fetch(
        "http://127.0.0.1:8002/latest-analysis",
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("Unable to load the processed dataset.");
      }

      const result = await response.json();

      if (!result.dataset || !Array.isArray(result.segments)) {
        throw new Error("No processed dataset is available.");
      }

      setData(result);
    } catch (err) {
      setData(null);
      setError(
        err instanceof Error ? err.message : "Could not load dataset."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const money = (value: number) =>
    new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "GBP",
      maximumFractionDigits: 2,
    }).format(value);

  return (
    <div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">DATA MANAGEMENT</div>
          <h1>Your datasets</h1>
          <p>
            View your latest processed dataset and its machine-learning
            analysis.
          </p>
        </div>

        <div className="heading-actions">
          <Link
            className="button-secondary"
            href="/datasets/kaggle"
          >
            <Database size={15} /> Import from Kaggle
          </Link>

          <Link
            className="button-primary"
            href="/datasets/upload"
          >
            <FileUp size={16} /> Upload CSV
          </Link>
        </div>
      </div>

      <div className="data-table-card">
        <div className="table-toolbar">
          <div>
            <b>Processed dataset</b>
            <small>
              {loading
                ? "Loading…"
                : data
                  ? "1 latest processed dataset"
                  : "No processed dataset"}
            </small>
          </div>

          <button
            className="refresh-button"
            onClick={() => void load()}
            aria-label="Refresh dataset"
          >
            <RefreshCw size={15} />
          </button>
        </div>

        {loading ? (
          <div className="table-loading">
            Loading your dataset…
          </div>
        ) : error ? (
          <div className="library-empty">
            <h3>Unable to load dataset</h3>
            <p>{error}</p>
            <button
              className="button-primary"
              onClick={() => void load()}
            >
              Retry
            </button>
          </div>
        ) : data ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Status</th>
                    <th>Customers</th>
                    <th>Transactions</th>
                    <th>Clusters</th>
                    <th>Silhouette score</th>
                  </tr>
                </thead>

                <tbody>
                  <tr>
                    <td>
                      <span className="dataset-name">
                        <span className="file-icon">
                          <Database size={16} />
                        </span>
                        <span>
                          <b>{data.dataset}</b>
                          <small>Latest processed dataset</small>
                        </span>
                      </span>
                    </td>

                    <td>
                      <span className="status-pill ready">
                        Processed
                      </span>
                    </td>

                    <td>
                      {data.totalCustomers.toLocaleString()}
                    </td>

                    <td>
                      {data.cleanedTransactions.toLocaleString()}
                    </td>

                    <td>{data.numberOfClusters}</td>

                    <td>{data.silhouetteScore.toFixed(4)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="overview-shortcuts">
              <Link
                className="starter-card"
                href="/analytics"
              >
                <span className="starter-icon blue">
                  <Database size={18} />
                </span>
                <b>Dataset analytics</b>
                <p>
                  Total revenue: {money(data.totalRevenue)}
                </p>
                <span className="card-link">
                  View analytics <ArrowUpRight size={14} />
                </span>
              </Link>

              <Link
                className="starter-card"
                href="/agent"
              >
                <span className="starter-icon violet">
                  <Database size={18} />
                </span>
                <b>AI analyst</b>
                <p>
                  Explore insights from this processed dataset.
                </p>
                <span className="card-link">
                  Open analyst <ArrowUpRight size={14} />
                </span>
              </Link>
            </div>
          </>
        ) : (
          <div className="library-empty">
            <div className="empty-metrics-icon">
              <Database size={18} />
            </div>
            <h3>No datasets processed</h3>
            <p>
              Upload a CSV to start profiling and processing your data.
            </p>
            <Link
              className="button-primary"
              href="/datasets/upload"
            >
              <FileUp size={15} /> Upload CSV
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

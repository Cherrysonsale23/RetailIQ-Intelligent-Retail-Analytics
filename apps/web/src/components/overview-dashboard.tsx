
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Database,
  FileUp,
  RefreshCw,
  Sparkles,
} from "lucide-react";

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

export function OverviewDashboard() {
  const [data, setData] = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");

    try {
      const response = await fetch(
        "http://127.0.0.1:8002/latest-analysis",
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("Unable to load the latest analysis.");
      }

      const result = await response.json();

      if (!result.dataset || !Array.isArray(result.segments)) {
        throw new Error("No processed dataset is available.");
      }

      setData(result);
    } catch (err) {
      setData(null);
      setError(
        err instanceof Error ? err.message : "Could not load workspace data."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const money = (value: number) =>
    new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "GBP",
      maximumFractionDigits: 2,
    }).format(value);

  return (
    <div className="overview-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR ANALYTICS WORKSPACE</div>
          <h1>Workspace overview</h1>
          <p>Dataset health, recent processing, and paths into your analysis.</p>
        </div>

        <div className="heading-actions">
          <Link className="button-primary" href="/datasets/upload">
            <FileUp size={16} /> Upload dataset
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="table-loading">Loading workspace activity…</div>
      ) : error ? (
        <div className="notice-error" role="alert">
          {error}
          <button onClick={() => void load()}>Retry</button>
        </div>
      ) : data ? (
        <>
          <section className="welcome-panel">
            <div className="welcome-copy">
              <div className="welcome-pill">
                <Sparkles size={14} /> Evidence-first analytics
              </div>
              <h2>
                Turn raw data into
                <br />
                clear decisions.
              </h2>
              <p>
                Your latest dataset has been processed using Python machine
                learning and is ready for analysis.
              </p>
              <Link className="button-light" href="/analytics">
                Explore analytics <ArrowUpRight size={16} />
              </Link>
            </div>
            <div className="welcome-art" aria-hidden="true">
              <div className="orbit orbit-one" />
              <div className="orbit orbit-two" />
              <div className="orbit-core">
                <Database size={30} />
              </div>
              <div className="orbit-node node-a" />
              <div className="orbit-node node-b" />
              <div className="orbit-node node-c" />
            </div>
          </section>

          <div className="metric-grid overview-metrics">
            <article className="metric-card">
              <div className="metric-top">
                <span>Total customers</span>
                <Database size={16} />
              </div>
              <b>{data.totalCustomers.toLocaleString()}</b>
              <small>Unique customers analyzed</small>
            </article>

            <article className="metric-card">
              <div className="metric-top">
                <span>Total revenue</span>
                <Activity size={16} />
              </div>
              <b>{money(data.totalRevenue)}</b>
              <small>Revenue in the dataset</small>
            </article>

            <article className="metric-card">
              <div className="metric-top">
                <span>Customer clusters</span>
                <RefreshCw size={16} />
              </div>
              <b>{data.numberOfClusters}</b>
              <small>K-Means clustering</small>
            </article>
          </div>

          <div className="data-table-card">
            <div className="table-toolbar">
              <div>
                <b>Latest processed dataset</b>
                <small>Results from your local Python ML API</small>
              </div>
              <Link className="card-link" href="/analytics">
                View analytics <ArrowUpRight size={14} />
              </Link>
            </div>

            <div className="table-scroll">
              <table className="overview-activity-table">
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Transactions</th>
                    <th>Cleaned rows</th>
                    <th>Clusters</th>
                    <th>Silhouette score</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      <span className="dataset-name">
                        <span className="file-icon">
                          <Database size={15} />
                        </span>
                        <span>
                          <b>{data.dataset}</b>
                          <small>Successfully processed</small>
                        </span>
                      </span>
                    </td>
                    <td>{data.originalTransactions.toLocaleString()}</td>
                    <td>{data.cleanedTransactions.toLocaleString()}</td>
                    <td>{data.numberOfClusters}</td>
                    <td>{data.silhouetteScore.toFixed(4)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="overview-shortcuts">
            <Link className="starter-card" href="/analytics">
              <span className="starter-icon blue">
                <Activity size={18} />
              </span>
              <b>Analytics</b>
              <p>Explore customer segments, RFM metrics, and charts.</p>
              <span className="card-link">
                Open dashboard <ArrowUpRight size={14} />
              </span>
            </Link>

            <Link className="starter-card" href="/agent">
              <span className="starter-icon violet">
                <Sparkles size={18} />
              </span>
              <b>AI analyst</b>
              <p>Ask questions about your processed customer data.</p>
              <span className="card-link">
                Open analyst <ArrowUpRight size={14} />
              </span>
            </Link>
          </div>
        </>
      ) : null}
    </div>
  );
}

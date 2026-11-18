
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  UserRound,
  BriefcaseBusiness,
  Database,
  RefreshCw,
  ShieldCheck,
  Info,
  CheckCircle2,
  XCircle,
  LoaderCircle,
  Cpu,
  BarChart3,
} from "lucide-react";

type AnalysisData = {
  project?: string;
  model?: string;
  dataset?: string;
  totalCustomers?: number;
  numberOfClusters?: number;
  silhouetteScore?: number;
};

export default function SettingsPage() {
  const [status, setStatus] = useState<
    "checking" | "connected" | "offline"
  >("checking");

  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [lastChecked, setLastChecked] = useState<string>("Not checked yet");

  const checkConnection = useCallback(async () => {
    setStatus("checking");

    try {
      const response = await fetch(
        "http://127.0.0.1:8002/latest-analysis",
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("API connection failed");
      }

      const data: AnalysisData = await response.json();

      setAnalysis(data);
      setStatus("connected");
      setLastChecked(new Date().toLocaleTimeString());
    } catch {
      setStatus("offline");
      setAnalysis(null);
      setLastChecked(new Date().toLocaleTimeString());
    }
  }, []);

  useEffect(() => {
    checkConnection();
  }, [checkConnection]);

  return (
    <div className="settings-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE CONFIGURATION</div>
          <h1>Settings</h1>
          <p>
            Manage your Meridian workspace and monitor application
            connectivity.
          </p>
        </div>
      </div>

      <section className="settings-card">
        <div className="settings-card-title">
          <UserRound size={19} />
          <div>
            <b>Workspace Profile</b>
            <small>Current workspace information</small>
          </div>
        </div>

        <div className="settings-row">
          <span>Workspace name</span>
          <b>Meridian Analytics</b>
        </div>

        <div className="settings-row">
          <span>Account mode</span>
          <b>Local Academic Demo</b>
        </div>

        <div className="settings-row">
          <span>Workspace access</span>
          <b>Local development environment</b>
        </div>

        <div className="privacy-note">
          <ShieldCheck size={16} />
          This workspace uses local application services.
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-title">
          <Database size={19} />
          <div>
            <b>Python ML API Connection</b>
            <small>Live connection status for the machine learning service</small>
          </div>
        </div>

        <div className="settings-row">
          <span>Connection status</span>

          <b>
            {status === "checking" && (
              <span>
                <LoaderCircle
                  size={15}
                  style={{ display: "inline", marginRight: 6 }}
                />
                Checking...
              </span>
            )}

            {status === "connected" && (
              <span style={{ color: "#16a34a" }}>
                <CheckCircle2
                  size={15}
                  style={{ display: "inline", marginRight: 6 }}
                />
                Connected
              </span>
            )}

            {status === "offline" && (
              <span style={{ color: "#dc2626" }}>
                <XCircle
                  size={15}
                  style={{ display: "inline", marginRight: 6 }}
                />
                Offline
              </span>
            )}
          </b>
        </div>

        <div className="settings-row">
          <span>API address</span>
          <b>127.0.0.1:8002</b>
        </div>

        <div className="settings-row">
          <span>Last connection check</span>
          <b>{lastChecked}</b>
        </div>

        <div className="settings-action">
          <button
            type="button"
            onClick={checkConnection}
            disabled={status === "checking"}
          >
            <RefreshCw size={15} />
            Refresh Connection
          </button>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-title">
          <BarChart3 size={19} />
          <div>
            <b>Machine Learning Configuration</b>
            <small>Information from the latest analysis</small>
          </div>
        </div>

        <div className="settings-row">
          <span>Machine learning model</span>
          <b>{analysis?.model || "Not available"}</b>
        </div>

        <div className="settings-row">
          <span>Latest dataset</span>
          <b>{analysis?.dataset || "No dataset loaded"}</b>
        </div>

        <div className="settings-row">
          <span>Total customers</span>
          <b>
            {analysis?.totalCustomers?.toLocaleString() ?? "—"}
          </b>
        </div>

        <div className="settings-row">
          <span>Number of clusters</span>
          <b>{analysis?.numberOfClusters ?? "—"}</b>
        </div>

        <div className="settings-row">
          <span>Silhouette score</span>
          <b>{analysis?.silhouetteScore ?? "—"}</b>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-title">
          <BriefcaseBusiness size={19} />
          <div>
            <b>Application Information</b>
            <small>Technology and environment details</small>
          </div>
        </div>

        <div className="settings-row">
          <span>Application</span>
          <b>Meridian Analytics</b>
        </div>

        <div className="settings-row">
          <span>Frontend</span>
          <b>Next.js</b>
        </div>

        <div className="settings-row">
          <span>Backend service</span>
          <b>Python FastAPI</b>
        </div>

        <div className="settings-row">
          <span>Clustering algorithm</span>
          <b>K-Means</b>
        </div>

        <div className="settings-row">
          <span>Customer analysis</span>
          <b>RFM Analysis</b>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-title">
          <Info size={19} />
          <div>
            <b>About Meridian</b>
            <small>Project overview</small>
          </div>
        </div>

        <p className="settings-description">
          Meridian is a customer segmentation and analytics platform
          that uses RFM analysis and K-Means clustering to identify
          customer groups from retail transaction data.
        </p>

        <div className="privacy-note">
          <Cpu size={16} />
          Machine learning analysis is processed through the local
          Python service.
        </div>
      </section>
    </div>
  );
}
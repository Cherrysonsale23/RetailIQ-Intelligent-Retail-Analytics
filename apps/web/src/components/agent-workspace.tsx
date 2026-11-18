
"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ArrowUpRight,
  Bot,
  Database,
  Download,
  LoaderCircle,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

type Segment = {
  cluster: number;
  name: string;
  customers: number;
  averageRecency: number;
  averageFrequency: number;
  averageMonetary: number;
};

type AnalysisData = {
  project: string;
  model: string;
  dataset: string;
  originalTransactions: number;
  cleanedTransactions: number;
  totalCustomers: number;
  totalRevenue: number;
  numberOfClusters: number;
  silhouetteScore: number;
  segments: Segment[];
};

type Result = {
  columns: string[];
  rows: (string | number)[][];
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: Result;
};

const API_URL = "http://127.0.0.1:8002/latest-analysis";

const prompts = [
  "Give me an overview of the uploaded dataset",
  "Which customer segment has the highest spending?",
  "Compare all customer clusters",
  "Which segment has the least recent activity?",
  "Explain the K-Means clustering results",
];

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 2,
  }).format(value);
}

function formatCurrency(value: number) {
  return "£" + formatNumber(value);
}

function ResultTable({ result }: { result: Result }) {
  function download() {
    const quote = (value: string | number) =>
      `"${String(value).replaceAll('"', '""')}"`;

    const csv = [
      result.columns.map(quote).join(","),
      ...result.rows.map((row) => row.map(quote).join(",")),
    ].join("\n");

    const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" })
    );

    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "meridian-customer-analysis.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="agent-result">
      <div className="agent-result-head">
        <b>Analysis result · {result.rows.length} rows</b>
        <button type="button" onClick={download}>
          <Download size={14} /> Download CSV
        </button>
      </div>

      <div className="agent-result-scroll">
        <table>
          <thead>
            <tr>
              {result.columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, index) => (
              <tr key={index}>
                {row.map((value, columnIndex) => (
                  <td key={columnIndex}>{value}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function getAnalysisAnswer(
  question: string,
  data: AnalysisData
): Message {
  const q = question.toLowerCase();

  const segments = [...data.segments];
  const highestSpending = [...segments].sort(
    (a, b) => b.averageMonetary - a.averageMonetary
  )[0];

  const mostRecent = [...segments].sort(
    (a, b) => a.averageRecency - b.averageRecency
  )[0];

  const leastRecent = [...segments].sort(
    (a, b) => b.averageRecency - a.averageRecency
  )[0];

  let content = "";
  let result: Result | undefined;

  if (
    q.includes("overview") ||
    q.includes("summary") ||
    q.includes("dataset") ||
    q.includes("total")
  ) {
    content =
      `Here is an overview of your uploaded dataset, ${data.dataset}. ` +
      `The Python ML pipeline identified ${formatNumber(data.totalCustomers)} customers ` +
      `and generated ${data.numberOfClusters} customer clusters. ` +
      `Total revenue is ${formatCurrency(data.totalRevenue)}, based on ` +
      `${formatNumber(data.cleanedTransactions)} cleaned transactions.`;

    result = {
      columns: ["Metric", "Value"],
      rows: [
        ["Dataset", data.dataset],
        ["Total customers", data.totalCustomers],
        ["Customer clusters", data.numberOfClusters],
        ["Total revenue", formatCurrency(data.totalRevenue)],
        ["Original transactions", data.originalTransactions],
        ["Cleaned transactions", data.cleanedTransactions],
        ["Silhouette score", data.silhouetteScore],
      ],
    };
  } else if (
    q.includes("highest spending") ||
    q.includes("highest monetary") ||
    q.includes("most valuable") ||
    q.includes("spend the most") ||
    q.includes("highest value")
  ) {
    content =
      `${highestSpending.name} has the highest average monetary value ` +
      `among the identified clusters, at ${formatCurrency(highestSpending.averageMonetary)} ` +
      `per customer. It contains ${formatNumber(highestSpending.customers)} customers.`;

    result = {
      columns: ["Metric", "Value"],
      rows: [
        ["Highest-spending segment", highestSpending.name],
        ["Customers", highestSpending.customers],
        ["Average recency (days)", highestSpending.averageRecency],
        ["Average frequency", highestSpending.averageFrequency],
        ["Average monetary value", formatCurrency(highestSpending.averageMonetary)],
      ],
    };
  } else if (
    q.includes("least recent") ||
    q.includes("inactive") ||
    q.includes("longest") ||
    q.includes("not purchased") ||
    q.includes("least recently")
  ) {
    content =
      `${leastRecent.name} has the highest average recency, at ` +
      `${formatNumber(leastRecent.averageRecency)} days. A higher recency value ` +
      `means customers in this segment have gone longer since their last purchase.`;

    result = {
      columns: ["Metric", "Value"],
      rows: [
        ["Segment", leastRecent.name],
        ["Customers", leastRecent.customers],
        ["Average recency (days)", leastRecent.averageRecency],
        ["Average frequency", leastRecent.averageFrequency],
        ["Average monetary value", formatCurrency(leastRecent.averageMonetary)],
      ],
    };
  } else if (
    q.includes("most recent") ||
    q.includes("recent purchase") ||
    q.includes("recently active")
  ) {
    content =
      `${mostRecent.name} has the lowest average recency, at ` +
      `${formatNumber(mostRecent.averageRecency)} days. This means its customers ` +
      `have purchased more recently on average than customers in the other clusters.`;

    result = {
      columns: ["Metric", "Value"],
      rows: [
        ["Most recently active segment", mostRecent.name],
        ["Customers", mostRecent.customers],
        ["Average recency (days)", mostRecent.averageRecency],
        ["Average frequency", mostRecent.averageFrequency],
        ["Average monetary value", formatCurrency(mostRecent.averageMonetary)],
      ],
    };
  } else if (
    q.includes("compare") ||
    q.includes("cluster") ||
    q.includes("segment") ||
    q.includes("rfm") ||
    q.includes("k-means") ||
    q.includes("kmeans")
  ) {
    content =
      `Your K-Means model generated ${data.numberOfClusters} customer clusters. ` +
      `The table compares their customer counts and average RFM values. ` +
      `Recency is measured in days, Frequency represents average purchase frequency, ` +
      `and Monetary represents average customer spending.`;

    result = {
      columns: [
        "Cluster",
        "Customers",
        "Average recency (days)",
        "Average frequency",
        "Average monetary (£)",
      ],
      rows: segments.map((segment) => [
        segment.name,
        segment.customers,
        segment.averageRecency,
        segment.averageFrequency,
        formatCurrency(segment.averageMonetary),
      ]),
    };
  } else if (
    q.includes("silhouette") ||
    q.includes("model") ||
    q.includes("performance") ||
    q.includes("evaluation")
  ) {
    content =
      `Your model uses ${data.model}. Its silhouette score is ` +
      `${data.silhouetteScore}. The score describes how well-separated the ` +
      `clusters are. A higher score generally indicates better-defined clusters, ` +
      `but it should be interpreted in context.`;

    result = {
      columns: ["Model metric", "Value"],
      rows: [
        ["Algorithm", data.model],
        ["Number of clusters", data.numberOfClusters],
        ["Silhouette score", data.silhouetteScore],
        ["Total customers", data.totalCustomers],
      ],
    };
  } else if (
    q.includes("revenue") ||
    q.includes("monetary") ||
    q.includes("spending")
  ) {
    content =
      `The total revenue in your cleaned dataset is ${formatCurrency(data.totalRevenue)}. ` +
      `${highestSpending.name} has the highest average monetary value per customer ` +
      `among the clusters.`;

    result = {
      columns: ["Segment", "Customers", "Average monetary (£)"],
      rows: segments.map((segment) => [
        segment.name,
        segment.customers,
        formatCurrency(segment.averageMonetary),
      ]),
    };
  } else if (q.includes("frequency")) {
    content =
      "Frequency represents the average purchase frequency for customers in each cluster. " +
      "Here is the comparison using your uploaded dataset.";

    result = {
      columns: ["Segment", "Customers", "Average frequency"],
      rows: segments.map((segment) => [
        segment.name,
        segment.customers,
        segment.averageFrequency,
      ]),
    };
  } else {
    content =
      "I can answer questions using the uploaded customer segmentation results. " +
      "Try asking about the dataset overview, customer clusters, RFM values, " +
      "highest-spending segment, recency, revenue, or silhouette score.";
  }

  return {
    id: `answer-${Date.now()}`,
    role: "assistant",
    content,
    result,
  };
}

export function AgentWorkspace() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [analysisNumber, setAnalysisNumber] = useState(1);
  const [data, setData] = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadAnalysis() {
      try {
        setLoading(true);
        setError("");

        const response = await fetch(API_URL, {
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error(
            response.status === 404
              ? "No uploaded dataset analysis was found. Please upload and process a CSV file first."
              : `The Python API returned status ${response.status}.`
          );
        }

        const result: AnalysisData = await response.json();

        if (
          !result.dataset ||
          !Array.isArray(result.segments) ||
          result.segments.length === 0
        ) {
          throw new Error("The API response does not contain valid customer segmentation results.");
        }

        if (active) {
          setData(result);
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load the uploaded dataset analysis."
          );
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadAnalysis();

    return () => {
      active = false;
    };
  }, []);

  function newAnalysis() {
    setMessages([]);
    setQuestion("");
    setAnalysisNumber((number) => number + 1);
  }

  function send(event?: FormEvent) {
    event?.preventDefault();

    const text = question.trim();

    if (!text || sending || !data) return;

    setSending(true);
    setQuestion("");

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };

    setMessages((current) => [...current, userMessage]);

    window.setTimeout(() => {
      const answer = getAnalysisAnswer(text, data);
      setMessages((current) => [...current, answer]);
      setSending(false);
    }, 400);
  }

  return (
    <div className="agent-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">DATASET GROUNDED ASSISTANT</div>
          <h1>AI analyst</h1>
          <p>
            Explore customer segmentation insights using your latest uploaded
            dataset and Python machine learning results.
          </p>
        </div>

        <button className="button-secondary" onClick={newAnalysis}>
          <Plus size={16} /> New analysis
        </button>
      </div>

      <div className="agent-toolbar">
        <div className="agent-select-label">
          <Database size={16} />
          <span>Dataset</span>
          <span className="agent-demo-label">
            {loading
              ? "Loading dataset..."
              : data
                ? data.dataset
                : "No dataset loaded"}
          </span>
        </div>

        <div className="agent-status">
          <span className="status-dot" />
          {loading
            ? "Connecting to Python ML API"
            : data
              ? "Connected · Local Python ML API"
              : "Connection unavailable"}
        </div>
      </div>

      <div className="privacy-note">
        <ShieldCheck size={15} />
        Analysis uses your locally processed dataset. No external AI provider
        or external data service is used.
      </div>

      <div className="agent-card">
        <div className="agent-card-head">
          <div className="agent-orb">
            <Bot size={19} />
          </div>

          <div>
            <b>Meridian Data Analyst</b>
            <small>
              Analysis session {analysisNumber} ·{" "}
              {data ? data.dataset : "Customer segmentation"}
            </small>
          </div>

          <div className="agent-head-badge">
            <ShieldCheck size={14} /> Local analysis
          </div>
        </div>

        <div className="agent-transcript" aria-live="polite">
          {loading ? (
            <div className="agent-thinking">
              <LoaderCircle size={15} className="spin" />
              Loading your latest Python ML analysis...
            </div>
          ) : error ? (
            <div className="agent-welcome">
              <Database size={22} />
              <h2>Dataset unavailable</h2>
              <p>{error}</p>
              <p>
                Check that the local Python API is running on port 8002 and
                that a CSV dataset has been uploaded and processed.
              </p>
            </div>
          ) : messages.length === 0 ? (
            <div className="agent-welcome">
              <Sparkles size={22} />
              <h2>What would you like to understand?</h2>
              <p>
                Ask questions about your actual customer segmentation results
                or choose one of the suggestions below.
              </p>

              <div className="prompt-grid">
                {prompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setQuestion(prompt)}
                  >
                    {prompt}
                    <ArrowUpRight size={13} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`agent-message ${message.role}`}
              >
                <div className="agent-message-icon">
                  {message.role === "assistant" ? <Bot size={15} /> : "Y"}
                </div>

                <div className="agent-message-body">
                  <div className="agent-message-role">
                    {message.role === "assistant"
                      ? "MERIDIAN DATA ANALYST"
                      : "YOU"}
                  </div>

                  <p>{message.content}</p>

                  {message.result && (
                    <ResultTable result={message.result} />
                  )}

                  {message.role === "assistant" && (
                    <small className="analytics-note">
                      Calculated from the latest uploaded dataset's Python ML
                      analysis results.
                    </small>
                  )}
                </div>
              </div>
            ))
          )}

          {sending && (
            <div className="agent-thinking">
              <LoaderCircle size={15} className="spin" />
              Analyzing your dataset...
            </div>
          )}
        </div>

        <form className="agent-composer" onSubmit={send}>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={
              data
                ? "Ask about customers, clusters, RFM, revenue..."
                : "Waiting for dataset..."
            }
            disabled={sending || !data}
            rows={2}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
          />

          <button
            type="submit"
            aria-label="Send question"
            className="send-button"
            disabled={!question.trim() || sending || !data}
          >
            {sending ? (
              <LoaderCircle size={17} className="spin" />
            ) : (
              <Send size={17} />
            )}
          </button>
        </form>

        <div className="agent-privacy">
          <small>
            <ShieldCheck size={13} /> Local dataset analysis only. No LLM,
            Supabase, or external AI provider is used.
          </small>
        </div>
      </div>
    </div>
  );
}
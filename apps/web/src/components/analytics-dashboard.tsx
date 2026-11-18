
"use client";

import { Fragment, useEffect, useState } from "react";
import {
  Activity,
  Database,
  Users,
  BarChart3,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Scatter,
  ScatterChart,
} from "recharts";

const COLORS = ["#177356", "#e2ae55", "#6688a4"];

type Segment = {
  cluster: number;
  name: string;
  customers: number;
  averageRecency: number;
  averageFrequency: number;
  averageMonetary: number;
};

type DashboardData = {
  project: string;
  model: string;
  dataset: string;
  originalTransactions: number;
  cleanedTransactions: number;
  totalCustomers: number;
  totalRevenue: number;
  numberOfClusters: number;
  silhouetteScore: number;
  daviesBouldinScore?: number;
  calinskiHarabaszScore?: number;
  inertia?: number;
  segments: Segment[];
};

function formatNumber(value: number) {
  return value.toLocaleString("en-US");
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatEvaluationMetric(value: number | undefined, digits = 2) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "N/A";
}

function ChartCard({
  title,
  description,
  children,
  wide = false,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <section className={`chart-card${wide ? " wide" : ""}`}>
      <div className="chart-heading">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
      </div>
      <div className="chart-body">{children}</div>
    </section>
  );
}

export function AnalyticsDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadDashboard() {
      try {
        let result: DashboardData | null = null;

        try {
          const uploadedResponse = await fetch(
            "http://127.0.0.1:8002/latest-analysis",
            { cache: "no-store" }
          );

          if (uploadedResponse.ok) {
            result = await uploadedResponse.json();
          }
        } catch {
          // Use the original dashboard data if the API is unavailable.
        }

        if (!result) {
          const fallbackResponse = await fetch("/ml-results.json", {
            cache: "no-store",
          });

          if (!fallbackResponse.ok) {
            throw new Error("Could not load the ML results.");
          }

          result = await fallbackResponse.json();
        }

        if (!result) {
          throw new Error("No dashboard data is available.");
        }

        setData(result);
        setError("");
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Could not load ML results."
        );
      } finally {
        setLoading(false);
      }
    }

    loadDashboard();
  }, []);

  if (loading) {
    return (
      <div className="page-heading">
        <h1>Loading ML results...</h1>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="page-heading">
        <h1>Analytics dashboard</h1>
        <p>{error || "ML results are not available."}</p>
        <p>Check that ml-results.json exists inside apps/web/public.</p>
      </div>
    );
  }

  const metrics = [
    {
      label: "Total customers",
      value: formatNumber(data.totalCustomers),
      icon: Users,
    },
    {
      label: "Customer clusters",
      value: String(data.numberOfClusters),
      icon: BarChart3,
    },
    {
      label: "Silhouette score",
      value: formatEvaluationMetric(data.silhouetteScore, 4),
      icon: Activity,
    },
    {
      label: "Davies-Bouldin Index",
      value: formatEvaluationMetric(data.daviesBouldinScore, 3),
      icon: Activity,
    },
    {
      label: "Calinski-Harabasz Score",
      value: formatEvaluationMetric(data.calinskiHarabaszScore),
      icon: BarChart3,
    },
    {
      label: "K-Means Inertia",
      value: formatEvaluationMetric(data.inertia),
      icon: Database,
    },
    {
      label: "Total revenue",
      value: formatCurrency(data.totalRevenue),
      icon: Database,
    },
    {
      label: "Original transactions",
      value: formatNumber(data.originalTransactions),
      icon: Activity,
    },
    {
      label: "Cleaned transactions",
      value: formatNumber(data.cleanedTransactions),
      icon: Database,
    },
  ];

  const customerDistribution = data.segments.map((segment) => ({
    name: segment.name,
    customers: segment.customers,
  }));

  const rfmMetrics = [
    {
      label: "Recency",
      key: "averageRecency" as const,
      format: (value: number) => `${value.toFixed(1)} days`,
    },
    {
      label: "Frequency",
      key: "averageFrequency" as const,
      format: (value: number) => value.toFixed(2),
    },
    {
      label: "Monetary",
      key: "averageMonetary" as const,
      format: (value: number) => formatCurrency(value),
    },
  ];

  return (
    <div>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MACHINE LEARNING WORKSPACE</div>
          <h1>Customer Segmentation Dashboard</h1>
          <p>
            Actual customer analytics generated using RFM analysis and
            K-Means clustering.
          </p>
        </div>
      </div>

      <div className="analytics-source">
        <span className="source-dot" />
        <b>Connected to Python ML results</b>
        <span>Local dataset</span>
      </div>

      <div className="privacy-note">
        <Database size={15} />
        Dashboard metrics are loaded from the latest uploaded dataset using
        the Python ML pipeline.
      </div>

      <div className="metric-grid">
        {metrics.map((metric) => {
          const Icon = metric.icon;

          return (
            <article className="metric-card" key={metric.label}>
              <div className="metric-top">
                <span>{metric.label}</span>
                <Icon size={16} />
              </div>
              <b>{metric.value}</b>
              <small>Python ML result</small>
            </article>
          );
        })}
      </div>

      <div className="analytics-grid">
        <ChartCard
          title="Customer segment distribution"
          description="Number of customers in each K-Means cluster."
        >
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={customerDistribution}
                dataKey="customers"
                nameKey="name"
                innerRadius={64}
                outerRadius={94}
                paddingAngle={3}
              >
                {customerDistribution.map((item, index) => (
                  <Cell
                    key={item.name}
                    fill={COLORS[index % COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>

          <div className="chart-legend">
            {customerDistribution.map((item, index) => (
              <div key={item.name}>
                <i style={{ background: COLORS[index % COLORS.length] }} />
                <span>{item.name}</span>
                <b>{formatNumber(item.customers)}</b>
              </div>
            ))}
          </div>
        </ChartCard>

        <ChartCard
          title="Average monetary value"
          description="Average customer spending in each segment."
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.segments}>
              <CartesianGrid
                strokeDasharray="3 3"
                vertical={false}
                stroke="#edf1ee"
              />
              <XAxis dataKey="name" tick={{ fontSize: 9 }} />
              <YAxis tick={{ fontSize: 9 }} />
              <Tooltip
                formatter={(value) => formatCurrency(Number(value))}
              />
              <Bar
                dataKey="averageMonetary"
                name="Average monetary value"
                fill="#26805d"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Customer segment profiles"
          description="Average RFM values for each customer group."
          wide
        >
          <div className="chart-legend">
            {data.segments.map((segment) => (
              <div
                key={segment.cluster}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "16px",
                  padding: "12px 0",
                  borderBottom: "1px solid #edf1ee",
                  flexWrap: "wrap",
                }}
              >
                <b>{segment.name}</b>
                <span>
                  Customers: {formatNumber(segment.customers)}
                </span>
                <span>
                  Recency: {segment.averageRecency.toFixed(1)} days
                </span>
                <span>
                  Frequency: {segment.averageFrequency.toFixed(2)}
                </span>
                <span>
                  Monetary: {formatCurrency(segment.averageMonetary)}
                </span>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>

      <div className="analytics-grid">
        <ChartCard
          title="Customer Distribution"
          description="Dynamic customer count across the latest uploaded clusters."
          wide
        >
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={customerDistribution}>
              <CartesianGrid
                strokeDasharray="3 3"
                vertical={false}
                stroke="#edf1ee"
              />
              <XAxis dataKey="name" />
              <YAxis tickFormatter={(value) => formatNumber(Number(value))} />
              <Tooltip
                formatter={(value) => [
                  formatNumber(Number(value)),
                  "Customers",
                ]}
              />
              <Bar
                dataKey="customers"
                name="Customers"
                radius={[5, 5, 0, 0]}
              >
                {customerDistribution.map((item, index) => (
                  <Cell
                    key={item.name}
                    fill={COLORS[index % COLORS.length]}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="RFM Heatmap"
          description="Dynamic comparison of average Recency, Frequency and Monetary values across customer segments."
          wide
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
              gap: "10px",
              overflowX: "auto",
            }}
          >
            <div style={{ fontWeight: 600, padding: "12px 4px" }}>
              Segment
            </div>

            {rfmMetrics.map((metric) => (
              <div
                key={metric.label}
                style={{
                  fontWeight: 600,
                  padding: "12px 4px",
                  textAlign: "center",
                }}
              >
                {metric.label}
              </div>
            ))}

            {data.segments.map((segment) => (
              <Fragment key={segment.cluster}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    fontWeight: 600,
                    padding: "12px 4px",
                  }}
                >
                  {segment.name}
                </div>

                {rfmMetrics.map((metric) => {
                  const value = segment[metric.key];
                  const maximum = Math.max(
                    ...data.segments.map((s) => s[metric.key]),
                    1
                  );
                  const intensity = Math.max(0.12, value / maximum);

                  return (
                    <div
                      key={`${segment.cluster}-${metric.key}`}
                      style={{
                        backgroundColor: `rgba(23, 115, 86, ${intensity})`,
                        color: intensity > 0.55 ? "#ffffff" : "#173d31",
                        borderRadius: "8px",
                        padding: "18px 5px",
                        textAlign: "center",
                        fontWeight: 600,
                      }}
                    >
                      {metric.format(value)}
                    </div>
                  );
                })}
              </Fragment>
            ))}
          </div>
          <p style={{ fontSize: "12px", marginTop: "12px", opacity: 0.7 }}>
            Darker cells indicate higher values within each RFM measure.
          </p>
        </ChartCard>

        <ChartCard
          title="Recency vs Monetary Value"
          description="Relationship between average customer recency and average monetary value for each cluster."
          wide
        >
          <ResponsiveContainer width="100%" height={320}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="averageRecency"
                name="Average recency"
                unit=" days"
                tick={{ fontSize: 11 }}
              />
              <YAxis
                type="number"
                dataKey="averageMonetary"
                name="Average monetary"
                tickFormatter={(value) => `£${Number(value).toLocaleString("en-GB")}`}
                tick={{ fontSize: 11 }}
              />
              <Tooltip
                formatter={(value, name) => [
                  name === "averageMonetary"
                    ? formatCurrency(Number(value))
                    : `${Number(value).toFixed(1)} days`,
                  name === "averageMonetary"
                    ? "Average monetary"
                    : "Average recency",
                ]}
                labelFormatter={() => "Customer segment"}
              />
              <Scatter
                name="Customer segments"
                data={data.segments}
                fill="#177356"
              >
                {data.segments.map((segment, index) => (
                  <Cell
                    key={segment.cluster}
                    fill={COLORS[index % COLORS.length]}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <p style={{ fontSize: "12px", marginTop: "8px", opacity: 0.7 }}>
            Each point represents one customer cluster, not an individual customer.
          </p>
        </ChartCard>
      </div>

      <div className="definitions-card">
        <div>
          <b>Machine learning model</b>
          <span>{data.model}</span>
        </div>

        <div>
          <b>Dataset</b>
          <span>{data.dataset}</span>
        </div>

        <div>
          <b>Silhouette Score</b>
          <span>
            {formatEvaluationMetric(data.silhouetteScore, 4)}.
            Measures how well-separated the customer clusters are.
            Higher values generally indicate better separation.
          </span>
        </div>

        <div>
          <b>Davies-Bouldin Index</b>
          <span>
            {formatEvaluationMetric(data.daviesBouldinScore, 3)}.
            Measures cluster similarity. Lower values generally indicate
            better-separated clusters.
          </span>
        </div>

        <div>
          <b>Calinski-Harabasz Score</b>
          <span>
            {formatEvaluationMetric(data.calinskiHarabaszScore)}.
            Compares between-cluster dispersion with within-cluster
            dispersion. Higher values generally indicate better-defined
            clusters.
          </span>
        </div>

        <div>
          <b>K-Means Inertia</b>
          <span>
            {formatEvaluationMetric(data.inertia)}.
            Represents the sum of squared distances between customers
            and their assigned cluster centroids. It is mainly useful
            when comparing models with different cluster counts.
          </span>
        </div>
      </div>
    </div>
  );
}

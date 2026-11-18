
import pandas as pd
import numpy as np
import json

from pathlib import Path
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# Define paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"

OUTPUT_DIR = PROJECT_DIR / "apps" / "web" / "public"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load project data
rfm = pd.read_csv(DATA_DIR / "customer_segments.csv")
cleaned = pd.read_csv(DATA_DIR / "online_retail_cleaned.csv")

# Prepare the same features used during training
features = rfm[["Recency", "Frequency", "Monetary"]].copy()
features["Frequency"] = np.log1p(features["Frequency"])
features["Monetary"] = np.log1p(features["Monetary"])

scaler = StandardScaler()
scaled_features = scaler.fit_transform(features)

# Calculate final silhouette score
score = silhouette_score(scaled_features, rfm["Cluster"])

# Segment descriptions
segment_names = {
    0: "High-Value Active",
    1: "Inactive / At-Risk",
    2: "Regular Customers"
}

# Build segment summaries
segments = []

for cluster_id, group in rfm.groupby("Cluster"):
    segments.append({
        "cluster": int(cluster_id),
        "name": segment_names[int(cluster_id)],
        "customers": int(len(group)),
        "averageRecency": round(float(group["Recency"].mean()), 2),
        "averageFrequency": round(float(group["Frequency"].mean()), 2),
        "averageMonetary": round(float(group["Monetary"].mean()), 2)
    })

# Build dashboard data
dashboard_data = {
    "project": "Customer Segmentation",
    "model": "K-Means Clustering",
    "dataset": "UCI Online Retail",
    "originalTransactions": 541909,
    "cleanedTransactions": int(len(cleaned)),
    "totalCustomers": int(rfm["CustomerID"].nunique()),
    "totalRevenue": round(float(cleaned["TotalPrice"].sum()), 2),
    "numberOfClusters": int(rfm["Cluster"].nunique()),
    "silhouetteScore": round(float(score), 4),
    "segments": segments
}

# Export JSON
output_file = OUTPUT_DIR / "ml-results.json"

with open(output_file, "w", encoding="utf-8") as file:
    json.dump(dashboard_data, file, indent=4)

print("Dashboard data exported successfully!")
print("Total customers:", dashboard_data["totalCustomers"])
print("Number of clusters:", dashboard_data["numberOfClusters"])
print("Silhouette score:", dashboard_data["silhouetteScore"])
print("Output file:", output_file)

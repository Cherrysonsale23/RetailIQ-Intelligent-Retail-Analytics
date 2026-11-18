
import pandas as pd
import numpy as np
import joblib

from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# Define project paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"

MODEL_DIR.mkdir(exist_ok=True)

INPUT_FILE = DATA_DIR / "rfm_features.csv"
OUTPUT_FILE = DATA_DIR / "customer_segments.csv"

# Load RFM data
rfm = pd.read_csv(INPUT_FILE)

# Apply log transformation to reduce skewness
features = rfm[["Recency", "Frequency", "Monetary"]].copy()
features["Frequency"] = np.log1p(features["Frequency"])
features["Monetary"] = np.log1p(features["Monetary"])

# Scale the features
scaler = StandardScaler()
scaled_features = scaler.fit_transform(features)

# Test different cluster counts
results = []

print("Evaluating K-Means cluster counts...\n")

for k in range(2, 9):
    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = model.fit_predict(scaled_features)

    score = silhouette_score(scaled_features, labels)
    results.append((k, score))

    print(f"Clusters: {k}, Silhouette Score: {score:.4f}")

# Select the cluster count with the highest silhouette score
best_k, best_score = max(results, key=lambda item: item[1])

print("\nBest number of clusters:", best_k)
print("Best Silhouette Score:", round(best_score, 4))

# Train final K-Means model
final_model = KMeans(
    n_clusters=best_k,
    random_state=42,
    n_init=10
)

rfm["Cluster"] = final_model.fit_predict(scaled_features)

# Save customer segments
rfm.to_csv(OUTPUT_FILE, index=False)

# Save model and scaler
joblib.dump(final_model, MODEL_DIR / "kmeans_model.pkl")
joblib.dump(scaler, MODEL_DIR / "scaler.pkl")

# Display cluster summary
print("\nCustomer count per cluster:")
print(rfm["Cluster"].value_counts().sort_index())

print("\nAverage RFM values per cluster:")
print(
    rfm.groupby("Cluster")[
        ["Recency", "Frequency", "Monetary"]
    ].mean().round(2)
)

print("\nCustomer segments saved to:", OUTPUT_FILE)
print("Model and scaler saved to:", MODEL_DIR)

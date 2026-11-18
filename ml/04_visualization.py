
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from pathlib import Path

# Define project paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

OUTPUT_DIR.mkdir(exist_ok=True)

# Load customer segmentation results
df = pd.read_csv(DATA_DIR / "customer_segments.csv")

# Assign descriptive cluster names
cluster_names = {
    0: "High-Value Active",
    1: "Inactive / At-Risk",
    2: "Regular Customers"
}

df["Segment"] = df["Cluster"].map(cluster_names)

sns.set_theme(style="whitegrid")

# 1. Customer distribution
plt.figure(figsize=(9, 5))
sns.countplot(data=df, x="Segment", order=[
    "High-Value Active",
    "Inactive / At-Risk",
    "Regular Customers"
])
plt.title("Customer Distribution Across Segments")
plt.xlabel("Customer Segment")
plt.ylabel("Number of Customers")
plt.xticks(rotation=15)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "customer_distribution.png", dpi=300)
plt.close()

# 2. Average RFM values by cluster
profile = df.groupby("Segment")[
    ["Recency", "Frequency", "Monetary"]
].mean()

normalized_profile = (
    profile - profile.min()
) / (profile.max() - profile.min())

plt.figure(figsize=(9, 5))
sns.heatmap(
    normalized_profile,
    annot=True,
    cmap="YlGnBu",
    fmt=".2f"
)
plt.title("Normalized RFM Profile by Customer Segment")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "rfm_heatmap.png", dpi=300)
plt.close()

# 3. Recency versus Monetary value
plt.figure(figsize=(9, 6))
sns.scatterplot(
    data=df,
    x="Recency",
    y="Monetary",
    hue="Segment",
    alpha=0.6
)
plt.yscale("log")
plt.title("Customer Recency vs Monetary Value")
plt.xlabel("Recency (Days)")
plt.ylabel("Monetary Value (£, log scale)")
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "recency_monetary.png", dpi=300)
plt.close()

# Save cluster profile
profile.to_csv(OUTPUT_DIR / "cluster_profile.csv")

print("Visualizations generated successfully!")
print("\nFiles saved in:", OUTPUT_DIR)
print("\nGenerated files:")
print("1. customer_distribution.png")
print("2. rfm_heatmap.png")
print("3. recency_monetary.png")
print("4. cluster_profile.csv")

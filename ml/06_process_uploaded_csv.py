
import pandas as pd
import numpy as np

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    silhouette_score,
    davies_bouldin_score,
    calinski_harabasz_score,
)


def process_uploaded_dataframe(df: pd.DataFrame) -> dict:
    """
    Clean a retail transaction dataset, calculate RFM features,
    perform K-Means clustering, and evaluate the final model.
    """

    required_columns = [
        "InvoiceNo",
        "InvoiceDate",
        "Quantity",
        "UnitPrice",
        "CustomerID",
    ]

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: " + ", ".join(missing_columns)
        )

    original_transactions = len(df)
    data = df.copy()

    # Remove duplicate records.
    data = data.drop_duplicates()

    # Convert columns to suitable data types.
    data["CustomerID"] = pd.to_numeric(
        data["CustomerID"], errors="coerce"
    )
    data["Quantity"] = pd.to_numeric(
        data["Quantity"], errors="coerce"
    )
    data["UnitPrice"] = pd.to_numeric(
        data["UnitPrice"], errors="coerce"
    )
    data["InvoiceDate"] = pd.to_datetime(
        data["InvoiceDate"], errors="coerce"
    )

    # Remove records with missing required values.
    data = data.dropna(
        subset=[
            "CustomerID",
            "Quantity",
            "UnitPrice",
            "InvoiceDate",
            "InvoiceNo",
        ]
    )

    # Remove cancelled invoices.
    cancelled = (
        data["InvoiceNo"]
        .astype(str)
        .str.strip()
        .str.upper()
        .str.startswith("C")
    )
    data = data.loc[~cancelled].copy()

    # Keep valid purchases only.
    data = data[
        (data["Quantity"] > 0)
        & (data["UnitPrice"] > 0)
    ].copy()

    if data.empty:
        raise ValueError(
            "No valid purchase records remain after cleaning."
        )

    # Calculate transaction value.
    data["TotalPrice"] = data["Quantity"] * data["UnitPrice"]

    # Calculate RFM features.
    reference_date = (
        data["InvoiceDate"].max() + pd.Timedelta(days=1)
    )

    rfm = data.groupby("CustomerID").agg(
        Recency=(
            "InvoiceDate",
            lambda dates: (reference_date - dates.max()).days
        ),
        Frequency=("InvoiceNo", "nunique"),
        Monetary=("TotalPrice", "sum"),
    ).reset_index()

    if len(rfm) < 3:
        raise ValueError(
            "At least 3 distinct customers are required for clustering."
        )

    # Transform skewed features and standardize them.
    features = rfm[["Recency", "Frequency", "Monetary"]].copy()
    features["Frequency"] = np.log1p(features["Frequency"])
    features["Monetary"] = np.log1p(features["Monetary"])

    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)

    # Test different K values and select the best silhouette score.
    best_score = -1
    best_k = None

    maximum_k = min(8, len(rfm) - 1)

    for k in range(2, maximum_k + 1):
        model = KMeans(
            n_clusters=k,
            random_state=42,
            n_init=10,
        )

        labels = model.fit_predict(scaled_features)

        score = silhouette_score(
            scaled_features,
            labels,
            sample_size=min(5000, len(rfm)),
            random_state=42,
        )

        if score > best_score:
            best_score = score
            best_k = k

    # Fit the final model using the selected number of clusters.
    final_model = KMeans(
        n_clusters=best_k,
        random_state=42,
        n_init=10,
    )

    final_labels = final_model.fit_predict(scaled_features)
    rfm["Cluster"] = final_labels

    # Evaluate the final clustering model.
    final_silhouette = silhouette_score(
        scaled_features,
        final_labels,
        sample_size=min(5000, len(rfm)),
        random_state=42,
    )

    db_index = davies_bouldin_score(
        scaled_features,
        final_labels,
    )

    ch_score = calinski_harabasz_score(
        scaled_features,
        final_labels,
    )

    # Create a summary for each customer segment.
    segment_summary = (
        rfm.groupby("Cluster")
        .agg(
            customers=("CustomerID", "count"),
            averageRecency=("Recency", "mean"),
            averageFrequency=("Frequency", "mean"),
            averageMonetary=("Monetary", "mean"),
        )
        .reset_index()
    )

    segments = []

    for _, row in segment_summary.iterrows():
        segments.append({
            "cluster": int(row["Cluster"]),
            "name": f"Cluster {int(row['Cluster'])}",
            "customers": int(row["customers"]),
            "averageRecency": round(
                float(row["averageRecency"]), 2
            ),
            "averageFrequency": round(
                float(row["averageFrequency"]), 2
            ),
            "averageMonetary": round(
                float(row["averageMonetary"]), 2
            ),
        })

    return {
        "originalTransactions": int(original_transactions),
        "cleanedTransactions": int(len(data)),
        "totalCustomers": int(rfm["CustomerID"].nunique()),
        "totalRevenue": round(float(data["TotalPrice"].sum()), 2),
        "numberOfClusters": int(best_k),
        "silhouetteScore": round(float(final_silhouette), 4),
        "daviesBouldinScore": round(float(db_index), 4),
        "calinskiHarabaszScore": round(float(ch_score), 2),
        "inertia": round(float(final_model.inertia_), 2),
        "segments": segments,
    }

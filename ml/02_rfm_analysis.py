
import pandas as pd
from pathlib import Path

# Define project paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "online_retail_cleaned.csv"
OUTPUT_FILE = DATA_DIR / "rfm_features.csv"

# Load cleaned transaction data
df = pd.read_csv(INPUT_FILE, parse_dates=["InvoiceDate"])

# Set reference date as one day after the latest transaction
reference_date = df["InvoiceDate"].max() + pd.Timedelta(days=1)

# Calculate RFM metrics for each customer
rfm = df.groupby("CustomerID").agg(
    Recency=("InvoiceDate", lambda x: (reference_date - x.max()).days),
    Frequency=("InvoiceNo", "nunique"),
    Monetary=("TotalPrice", "sum")
).reset_index()

# Save RFM features
rfm.to_csv(OUTPUT_FILE, index=False)

# Display results
print("RFM analysis completed!")
print("Number of customers:", len(rfm))
print("\nFirst 10 customer records:")
print(rfm.head(10))

print("\nRFM statistical summary:")
print(rfm[["Recency", "Frequency", "Monetary"]].describe())

print("\nSaved RFM dataset to:", OUTPUT_FILE)

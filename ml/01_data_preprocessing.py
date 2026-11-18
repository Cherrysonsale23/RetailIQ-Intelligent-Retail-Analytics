
import pandas as pd
from pathlib import Path

# Define project paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "Online Retail.xlsx"
OUTPUT_FILE = DATA_DIR / "online_retail_cleaned.csv"

# Load original dataset
df = pd.read_excel(INPUT_FILE)

print("Original dataset shape:", df.shape)

# Remove exact duplicate records
df = df.drop_duplicates()

# Remove transactions with missing customer IDs
df = df.dropna(subset=["CustomerID"])

# Remove cancelled invoices
df = df[~df["InvoiceNo"].astype(str).str.startswith("C")]

# Retain only positive quantities and prices
df = df[(df["Quantity"] > 0) & (df["UnitPrice"] > 0)]

# Convert customer IDs to integers
df["CustomerID"] = df["CustomerID"].astype(int)

# Calculate transaction revenue
df["TotalPrice"] = df["Quantity"] * df["UnitPrice"]

# Save cleaned dataset
df.to_csv(OUTPUT_FILE, index=False)

print("\nData cleaning completed!")
print("Cleaned dataset shape:", df.shape)
print("Unique customers:", df["CustomerID"].nunique())
print("Remaining missing values:", df.isnull().sum().sum())
print("Remaining duplicate rows:", df.duplicated().sum())
print("Total revenue:", round(df["TotalPrice"].sum(), 2))
print("\nSaved cleaned dataset to:", OUTPUT_FILE)

# datamart_build.py
# Build DataMart (fact and dimension tables) from Superstore Excel data

from pathlib import Path
import pandas as pd
import numpy as np
import sqlite3

# Configuration for file paths
INPUT_PATH = Path("/home/ducanhhh/superstore/data/superstore.xlsx")
SHEET_NAME = 0
ARTIFACTS_DIR = Path("artifacts")
SQLITE_PATH = ARTIFACTS_DIR / "salesmart.db"

# Ensure artifacts directory exists
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def load_and_clean_data() -> pd.DataFrame:
    """Load and clean Superstore Excel data.

    Returns:
        pd.DataFrame: Cleaned DataFrame with standardized columns and types.
    """
    # Load Excel data
    df = pd.read_excel(INPUT_PATH, sheet_name=SHEET_NAME)

    # Standardize column names by stripping spaces
    df.columns = [col.strip() for col in df.columns]

    # Validate required columns
    expected_columns = {
        "Order ID", "Order Date", "Ship Date", "Ship Mode",
        "Customer ID", "Customer Name", "Segment",
        "Country", "City", "State", "Postal Code", "Region",
        "Product ID", "Category", "Sub-Category", "Product Name",
        "Sales", "Quantity", "Discount", "Profit"
    }
    missing_columns = [col for col in expected_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    # Ensure correct data types
    df["Order Date"] = pd.to_datetime(df["Order Date"])
    df["Ship Date"] = pd.to_datetime(df["Ship Date"])
    numeric_columns = ["Sales", "Quantity", "Discount", "Profit", "Postal Code"]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Remove duplicates and critical NA values
    df = df.drop_duplicates().dropna(subset=["Order ID", "Order Date", "Product ID", "Sales", "Profit"])

    # Add utility columns
    df["order_year"] = df["Order Date"].dt.year
    df["order_month"] = df["Order Date"].dt.month
    df["month_key"] = df["Order Date"].dt.to_period("M").astype(str)
    df["cost_est"] = df["Sales"] - df["Profit"]  # Estimate COGS

    return df


def create_dimension_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create dimension tables from the cleaned DataFrame.

    Args:
        df (pd.DataFrame): Cleaned input DataFrame.

    Returns:
        tuple: Dimension tables (dim_date, dim_product, dim_customer, dim_geo).
    """
    # Dimension: Date
    dim_date = (
        df[["Order Date"]]
        .drop_duplicates()
        .rename(columns={"Order Date": "date"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    dim_date["date_key"] = dim_date["date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["yyyy"] = dim_date["date"].dt.year
    dim_date["mm"] = dim_date["date"].dt.month
    dim_date["dd"] = dim_date["date"].dt.day
    dim_date["qtr"] = dim_date["date"].dt.quarter
    dim_date["week"] = dim_date["date"].dt.isocalendar().week.astype(int)
    dim_date["month_key"] = dim_date["date"].dt.to_period("M").astype(str)

    # Dimension: Product
    dim_product = (
        df[["Product ID", "Product Name", "Sub-Category", "Category"]]
        .drop_duplicates()
        .rename(columns={
            "Product ID": "product_id",
            "Product Name": "product_name",
            "Sub-Category": "subcategory",
            "Category": "category"
        })
        .reset_index(drop=True)
    )

    # Dimension: Customer
    dim_customer = (
        df[["Customer ID", "Customer Name", "Segment"]]
        .drop_duplicates()
        .rename(columns={
            "Customer ID": "customer_id",
            "Customer Name": "customer_name",
            "Segment": "segment"
        })
        .reset_index(drop=True)
    )

    # Dimension: Geography
    dim_geo = (
        df[["Country", "Region", "State", "City", "Postal Code"]]
        .drop_duplicates()
        .rename(columns={"Postal Code": "postal_code"})
        .reset_index(drop=True)
    )

    return dim_date, dim_product, dim_customer, dim_geo


def create_fact_table(df: pd.DataFrame) -> pd.DataFrame:
    """Create fact_sales table from the cleaned DataFrame.

    Args:
        df (pd.DataFrame): Cleaned input DataFrame.

    Returns:
        pd.DataFrame: Fact table with selected and renamed columns.
    """
    fact = df.rename(columns={
        "Order ID": "order_id",
        "Order Date": "order_date",
        "Ship Date": "ship_date",
        "Product ID": "product_id",
        "Customer ID": "customer_id",
        "Region": "region",
        "State": "state",
        "City": "city",
        "Quantity": "qty",
        "Sales": "sales",
        "Discount": "discount",
        "Profit": "profit",
        "Ship Mode": "ship_mode"
    })
    fact["date_key"] = fact["order_date"].dt.strftime("%Y%m%d").astype(int)

    return fact[[
        "order_id", "date_key", "order_date", "ship_date",
        "product_id", "customer_id", "Country", "region", "state", "city",
        "qty", "sales", "discount", "profit", "cost_est", "month_key", "ship_mode"
    ]]


def save_to_sqlite(
    dim_date: pd.DataFrame,
    dim_product: pd.DataFrame,
    dim_customer: pd.DataFrame,
    dim_geo: pd.DataFrame,
    fact_sales: pd.DataFrame
) -> None:
    """Save dimension and fact tables to SQLite and create views.

    Args:
        dim_date (pd.DataFrame): Date dimension table.
        dim_product (pd.DataFrame): Product dimension table.
        dim_customer (pd.DataFrame): Customer dimension table.
        dim_geo (pd.DataFrame): Geography dimension table.
        fact_sales (pd.DataFrame): Sales fact table.
    """
    with sqlite3.connect(SQLITE_PATH) as conn:
        # Save tables
        dim_date.to_sql("dim_date", conn, if_exists="replace", index=False)
        dim_product.to_sql("dim_product", conn, if_exists="replace", index=False)
        dim_customer.to_sql("dim_customer", conn, if_exists="replace", index=False)
        dim_geo.to_sql("dim_geo", conn, if_exists="replace", index=False)
        fact_sales.to_sql("fact_sales", conn, if_exists="replace", index=False)

        # Create summary views
        conn.executescript("""
            DROP VIEW IF EXISTS v_monthly_sales;
            CREATE VIEW v_monthly_sales AS
            SELECT
                strftime('%Y-%m', order_date) AS month_key,
                SUM(sales) AS sales_m,
                SUM(profit) AS profit_m,
                COUNT(DISTINCT order_id) AS orders_m
            FROM fact_sales
            GROUP BY 1;

            DROP VIEW IF EXISTS v_product_monthly;
            CREATE VIEW v_product_monthly AS
            SELECT
                strftime('%Y-%m', order_date) AS month_key,
                product_id,
                SUM(sales) AS sales_m,
                SUM(profit) AS profit_m,
                SUM(qty) AS qty_m
            FROM fact_sales
            GROUP BY 1, 2;
        """)


def main():
    """Build DataMart by processing Superstore data and saving to Parquet and SQLite."""
    # Load and clean data
    df = load_and_clean_data()

    # Create dimension tables
    dim_date, dim_product, dim_customer, dim_geo = create_dimension_tables(df)

    # Create fact table
    fact_sales = create_fact_table(df)

    # Save to Parquet
    dim_date.to_parquet(ARTIFACTS_DIR / "dim_date.parquet", index=False)
    dim_product.to_parquet(ARTIFACTS_DIR / "dim_product.parquet", index=False)
    dim_customer.to_parquet(ARTIFACTS_DIR / "dim_customer.parquet", index=False)
    dim_geo.to_parquet(ARTIFACTS_DIR / "dim_geo.parquet", index=False)
    fact_sales.to_parquet(ARTIFACTS_DIR / "fact_sales.parquet", index=False)

    # Save to SQLite and create views
    save_to_sqlite(dim_date, dim_product, dim_customer, dim_geo, fact_sales)

    # Print summary
    print(f"DataMart built successfully at: {ARTIFACTS_DIR.resolve()}")
    print("  - fact_sales.parquet, dim_date.parquet, dim_product.parquet, dim_customer.parquet, dim_geo.parquet")
    print(f"  - SQLite: {SQLITE_PATH.resolve()}")


if __name__ == "__main__":
    main()
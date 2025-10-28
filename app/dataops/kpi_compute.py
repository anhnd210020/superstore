# kpi_compute.py
# Compute monthly KPIs with MoM/YoY metrics from DataMart and store results

from pathlib import Path
import pandas as pd
import numpy as np
import sqlite3

# Constants for file paths
ARTIFACTS_DIR = Path("artifacts")
SQLITE_PATH = ARTIFACTS_DIR / "salesmart.db"

FACT_PATH = ARTIFACTS_DIR / "fact_sales.parquet"
DIM_PRODUCT_PATH = ARTIFACTS_DIR / "dim_product.parquet"
DIM_CUSTOMER_PATH = ARTIFACTS_DIR / "dim_customer.parquet"

OUT_MONTHLY = ARTIFACTS_DIR / "kpi_monthly.parquet"
OUT_PROD_MONTHLY = ARTIFACTS_DIR / "kpi_prod_m.parquet"
OUT_CAT_MONTHLY = ARTIFACTS_DIR / "kpi_cat_m.parquet"
OUT_GEO_MONTHLY = ARTIFACTS_DIR / "kpi_geo_m.parquet"
OUT_SEGMENT_MONTHLY = ARTIFACTS_DIR / "kpi_segment_m.parquet"
OUT_SHIPMODE_MONTHLY = ARTIFACTS_DIR / "kpi_shipmode_m.parquet"

# Ensure artifacts directory exists
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def safe_pct_change(current: float, previous: float) -> float:
    """Calculate percentage change, handling zero or NaN cases to avoid infinity.

    Args:
        current (float): Current period value.
        previous (float): Previous period value.

    Returns:
        float: Percentage change or NaN if previous is zero or NaN.
    """
    if pd.isna(previous) or previous == 0:  
        return np.nan
    return (current - previous) / previous


def add_mom_yoy(
    df: pd.DataFrame,
    key_cols: list,
    value_cols: list,
    date_col: str = "month_key"
) -> pd.DataFrame:
    """Add Month-over-Month (MoM) and Year-over-Year (YoY) metrics to DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame, sorted by date_col within key_cols.
        key_cols (list): Columns to group by (e.g., product_id, category).
        value_cols (list): Columns to compute MoM/YoY for (e.g., sales_m).
        date_col (str): Column with date key (default: 'month_key').

    Returns:
        pd.DataFrame: DataFrame with MoM/YoY columns added.
    """
    df = df.sort_values(key_cols + [date_col]).copy()

    # Ensure month_dt exists for date operations
    if "month_dt" not in df.columns:
        df["month_dt"] = pd.to_datetime(df[date_col] + "-01")

    def compute_metrics(group: pd.DataFrame) -> pd.DataFrame:
        """Compute MoM and YoY metrics for a group."""
        group = group.sort_values("month_dt")
        for col in value_cols:
            # Month-over-Month differences
            group[f"{col}_mom"] = group[col].diff(1)
            group[f"{col}_mom_pct"] = [
                safe_pct_change(cur, prev)
                for cur, prev in zip(group[col], group[col].shift(1))
            ]
            # Year-over-Year differences (12-month lag)
            group[f"{col}_yoy"] = group[col].diff(12)
            group[f"{col}_yoy_pct"] = [
                safe_pct_change(cur, prev)
                for cur, prev in zip(group[col], group[col].shift(12))
            ]
        return group

    # Apply metrics calculation to groups or entire DataFrame
    if key_cols:
        df = df.groupby(key_cols, group_keys=False).apply(compute_metrics).reset_index(drop=True)
    else:
        df = compute_metrics(df)

    return df


def main():
    """Compute KPIs and store results in Parquet and SQLite."""
    # Load fact table
    if not FACT_PATH.exists():
        raise FileNotFoundError(f"Missing {FACT_PATH}. Run datamart_build.py first.")
    fact = pd.read_parquet(FACT_PATH)

    # Ensure correct data types
    fact["order_date"] = pd.to_datetime(fact["order_date"])
    if "month_key" not in fact.columns:
        fact["month_key"] = fact["order_date"].dt.to_period("M").astype(str)

    # Compute global monthly KPIs
    kpi_monthly = (
        fact.groupby("month_key", as_index=False)
        .agg(
            sales_m=("sales", "sum"),
            profit_m=("profit", "sum"),
            qty_m=("qty", "sum"),
            orders_m=("order_id", "nunique"),
        )
        .sort_values("month_key")
    )
    kpi_monthly["month_dt"] = pd.to_datetime(kpi_monthly["month_key"] + "-01")
    kpi_monthly = add_mom_yoy(
        kpi_monthly,
        key_cols=[],
        value_cols=["sales_m", "profit_m", "qty_m", "orders_m"],
    )
    kpi_monthly.to_parquet(OUT_MONTHLY, index=False)

    # Load dimension tables with fallback
    dim_product = (
        pd.read_parquet(DIM_PRODUCT_PATH)
        if DIM_PRODUCT_PATH.exists()
        else fact[["product_id"]]
        .drop_duplicates()
        .assign(product_name=None, subcategory=None, category=None)
    )

    dim_customer = (
        pd.read_parquet(DIM_CUSTOMER_PATH)
        if DIM_CUSTOMER_PATH.exists()
        else fact[["customer_id"]].drop_duplicates().assign(segment=None)
    )

    # Compute KPIs by Product × Month
    prod_monthly = (
        fact.groupby(["month_key", "product_id"], as_index=False)
        .agg(
            sales_m=("sales", "sum"),
            profit_m=("profit", "sum"),
            qty_m=("qty", "sum"),
            orders_m=("order_id", "nunique"),
        )
        .merge(
            dim_product[["product_id", "product_name", "subcategory", "category"]],
            on="product_id",
            how="left",
        )
    )
    prod_monthly["month_dt"] = pd.to_datetime(prod_monthly["month_key"] + "-01")
    prod_monthly = add_mom_yoy(
        prod_monthly,
        key_cols=["product_id"],
        value_cols=["sales_m", "profit_m", "qty_m", "orders_m"],
    )
    prod_monthly.to_parquet(OUT_PROD_MONTHLY, index=False)

    # Compute KPIs by Category × Month
    cat_monthly = (
        fact.merge(
            dim_product[["product_id", "subcategory", "category"]],
            on="product_id",
            how="left",
        )
        .groupby(["month_key", "category", "subcategory"], as_index=False)
        .agg(
            sales_m=("sales", "sum"),
            profit_m=("profit", "sum"),
            qty_m=("qty", "sum"),
            orders_m=("order_id", "nunique"),
        )
    )
    cat_monthly["month_dt"] = pd.to_datetime(cat_monthly["month_key"] + "-01")
    cat_monthly = add_mom_yoy(
        cat_monthly,
        key_cols=["category", "subcategory"],
        value_cols=["sales_m", "profit_m", "qty_m", "orders_m"],
    )
    cat_monthly.to_parquet(OUT_CAT_MONTHLY, index=False)

    # Compute KPIs by Geo × Month
    geo_monthly = (
        fact.groupby(["month_key", "region", "state"], as_index=False)
        .agg(
            sales_m=("sales", "sum"),
            profit_m=("profit", "sum"),
            qty_m=("qty", "sum"),
            orders_m=("order_id", "nunique"),
        )
    )
    geo_monthly["month_dt"] = pd.to_datetime(geo_monthly["month_key"] + "-01")
    geo_monthly = add_mom_yoy(
        geo_monthly,
        key_cols=["region", "state"],
        value_cols=["sales_m", "profit_m", "qty_m", "orders_m"],
    )
    geo_monthly.to_parquet(OUT_GEO_MONTHLY, index=False)

    # Compute KPIs by Segment × Month
    segment_monthly = (
        fact.merge(dim_customer[["customer_id", "segment"]], on="customer_id", how="left")
        .groupby(["month_key", "segment"], as_index=False)
        .agg(
            sales_m=("sales", "sum"),
            profit_m=("profit", "sum"),
            qty_m=("qty", "sum"),
            orders_m=("order_id", "nunique"),
        )
    )
    segment_monthly["month_dt"] = pd.to_datetime(segment_monthly["month_key"] + "-01")
    segment_monthly = add_mom_yoy(
        segment_monthly,
        key_cols=["segment"],
        value_cols=["sales_m", "profit_m", "qty_m", "orders_m"],
    )
    segment_monthly.to_parquet(OUT_SEGMENT_MONTHLY, index=False)

    # Compute KPIs by Ship Mode × Month
    shipmode_monthly = (
        fact.groupby(["month_key", "ship_mode"], as_index=False)
        .agg(
            sales_m=("sales", "sum"),
            profit_m=("profit", "sum"),
            qty_m=("qty", "sum"),
            orders_m=("order_id", "nunique"),
        )
    )
    shipmode_monthly["month_dt"] = pd.to_datetime(shipmode_monthly["month_key"] + "-01")
    shipmode_monthly = add_mom_yoy(
        shipmode_monthly,
        key_cols=["ship_mode"],
        value_cols=["sales_m", "profit_m", "qty_m", "orders_m"],
    )
    shipmode_monthly.to_parquet(OUT_SHIPMODE_MONTHLY, index=False)

    # Write to SQLite database
    with sqlite3.connect(SQLITE_PATH) as conn:
        kpi_monthly.to_sql("kpi_monthly", conn, if_exists="replace", index=False)
        prod_monthly.to_sql("kpi_prod_m", conn, if_exists="replace", index=False)
        cat_monthly.to_sql("kpi_cat_m", conn, if_exists="replace", index=False)
        geo_monthly.to_sql("kpi_geo_m", conn, if_exists="replace", index=False)
        segment_monthly.to_sql("kpi_segment_m", conn, if_exists="replace", index=False)
        shipmode_monthly.to_sql("kpi_shipmode_m", conn, if_exists="replace", index=False)

        # Create indexes for query performance
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_kpi_monthly_dt ON kpi_monthly(month_dt);
            CREATE INDEX IF NOT EXISTS idx_kpi_prod_m ON kpi_prod_m(product_id, month_dt);
            CREATE INDEX IF NOT EXISTS idx_kpi_cat_m ON kpi_cat_m(category, subcategory, month_dt);
            CREATE INDEX IF NOT EXISTS idx_kpi_geo_m ON kpi_geo_m(region, state, month_dt);
            CREATE INDEX IF NOT EXISTS idx_kpi_segment_m ON kpi_segment_m(segment, month_dt);
            CREATE INDEX IF NOT EXISTS idx_kpi_shipmode_m ON kpi_shipmode_m(ship_mode, month_dt);
        """)

        # Create views for simplified querying
        conn.executescript("""
            DROP VIEW IF EXISTS v_latest_month;
            CREATE VIEW v_latest_month AS
            SELECT month_key
            FROM kpi_monthly
            ORDER BY month_dt DESC
            LIMIT 1;

            DROP VIEW IF EXISTS v_top_products_latest;
            CREATE VIEW v_top_products_latest AS
            SELECT p.*
            FROM kpi_prod_m p
            WHERE p.month_key = (SELECT month_key FROM v_latest_month)
            ORDER BY p.sales_m DESC;

            DROP VIEW IF EXISTS v_category_summary_latest;
            CREATE VIEW v_category_summary_latest AS
            SELECT c.category, c.subcategory, c.sales_m, c.profit_m
            FROM kpi_cat_m c
            WHERE c.month_key = (SELECT month_key FROM v_latest_month)
            ORDER BY c.sales_m DESC;

            DROP VIEW IF EXISTS v_geo_profit_latest;
            CREATE VIEW v_geo_profit_latest AS
            SELECT region, state, sales_m, profit_m
            FROM kpi_geo_m
            WHERE month_key = (SELECT month_key FROM v_latest_month)
            ORDER BY profit_m ASC;
        """)

    # Print summary
    latest_month = kpi_monthly["month_key"].iloc[-1]
    print(f"   Latest month: {latest_month}")
    print("   Parquet outputs:")
    print(
        f"   - {OUT_MONTHLY.name}\n"
        f"   - {OUT_PROD_MONTHLY.name}\n"
        f"   - {OUT_CAT_MONTHLY.name}\n"
        f"   - {OUT_GEO_MONTHLY.name}\n"
        f"   - {OUT_SEGMENT_MONTHLY.name}\n"
        f"   - {OUT_SHIPMODE_MONTHLY.name}"
    )
    print(f"   SQLite updated: {SQLITE_PATH.resolve()}")


if __name__ == "__main__":
    main()
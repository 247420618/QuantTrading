"""输入参数和行情数据质量检查。"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd


TS_CODE_PATTERN = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
ADJ_VALUES = {"qfq", "hfq", None}


def validate_ts_code(ts_code: str) -> None:
    """检查 Tushare 股票代码格式。"""

    if not TS_CODE_PATTERN.match(ts_code):
        raise ValueError(f"Invalid ts_code {ts_code!r}; expected like 600000.SH or 000001.SZ")


def format_date(value: str) -> str:
    """把 YYYYMMDD 或 YYYY-MM-DD 转成 Tushare 所需的 YYYYMMDD。"""

    cleaned = value.replace("-", "")
    try:
        datetime.strptime(cleaned, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"Invalid date {value!r}; expected YYYYMMDD or YYYY-MM-DD") from exc
    return cleaned


def validate_adj(adj: str | None) -> None:
    """检查复权参数。"""

    if adj not in ADJ_VALUES:
        raise ValueError("adj must be one of None, 'qfq' or 'hfq'")


def assert_daily_bar_quality(df: pd.DataFrame, *, ts_code: str) -> None:
    """检查日线数据的最低质量要求。"""

    if df.empty:
        raise ValueError(f"No daily data returned for {ts_code}")
    required = {"ts_code", "trade_date", "open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Daily data missing columns: {sorted(missing)}")
    if df["trade_date"].duplicated().any():
        raise ValueError("Daily data contains duplicated trade_date")
    if "date" in df.columns and df["date"].isna().any():
        raise ValueError("Daily data contains invalid dates")

    prices = df[["open", "high", "low", "close"]]
    if prices.isna().any().any():
        raise ValueError("Daily prices contain missing values")
    if (prices <= 0).any().any():
        raise ValueError("Daily prices contain non-positive values")
    if (df["high"] < prices.max(axis=1)).any():
        raise ValueError("Daily OHLC check failed: high is below another price")
    if (df["low"] > prices.min(axis=1)).any():
        raise ValueError("Daily OHLC check failed: low is above another price")

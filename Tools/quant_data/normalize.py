"""Tushare 返回数据的 DataFrame 标准化。"""

from __future__ import annotations

import pandas as pd


def normalize_tushare_dates(df: pd.DataFrame) -> pd.DataFrame:
    """补充便于研究使用的 `date` 列，并按时间升序排列。"""

    if df.empty:
        return df.copy()

    normalized = df.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]

    if "trade_date" in normalized.columns:
        normalized["trade_date"] = normalized["trade_date"].astype(str)
        normalized["date"] = pd.to_datetime(normalized["trade_date"], format="%Y%m%d", errors="coerce")
        normalized = normalized.sort_values(["date", "ts_code"] if "ts_code" in normalized.columns else ["date"])
        normalized = normalized.reset_index(drop=True)
    elif "cal_date" in normalized.columns:
        normalized["cal_date"] = normalized["cal_date"].astype(str)
        normalized["date"] = pd.to_datetime(normalized["cal_date"], format="%Y%m%d", errors="coerce")
        normalized = normalized.sort_values("date").reset_index(drop=True)
    elif "list_date" in normalized.columns:
        normalized["list_date"] = normalized["list_date"].astype(str)
        normalized["list_dt"] = pd.to_datetime(normalized["list_date"], format="%Y%m%d", errors="coerce")

    return normalized

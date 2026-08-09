"""Tushare Pro SDK 的薄封装。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .normalize import normalize_tushare_dates
from .validators import format_date, validate_adj, validate_ts_code


class TushareError(RuntimeError):
    """Tushare SDK 安装、token 或查询失败时抛出的统一异常。"""


@dataclass
class TushareClient:
    """Tushare Pro 数据客户端。"""

    token: str | None

    def __post_init__(self) -> None:
        self._ts: Any | None = None
        self._pro: Any | None = None

    def pro(self) -> Any:
        """返回 Tushare Pro API 对象。"""

        if self._pro is not None:
            return self._pro
        if not self.token:
            raise TushareError(
                "Tushare token is missing. Set TUSHARE_TOKEN in Tools/env.local.sh or current shell."
        )
        ts = self._load_module()
        try:
            self._pro = ts.pro_api(token=self.token)
        except Exception as exc:
            raise TushareError("Tushare pro_api initialization failed. Check token and network.") from exc
        return self._pro

    def daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取单只股票非复权日线。"""

        validate_ts_code(ts_code)
        start = format_date(start_date)
        end = format_date(end_date)
        return normalize_tushare_dates(
            self._call("daily", ts_code=ts_code, start_date=start, end_date=end)
        )

    def daily_by_trade_date(self, trade_date: str) -> pd.DataFrame:
        """获取某个交易日全市场非复权日线。"""

        day = format_date(trade_date)
        return normalize_tushare_dates(self._call("daily", trade_date=day))

    def pro_bar(self, ts_code: str, start_date: str, end_date: str, *, adj: str | None = None) -> pd.DataFrame:
        """获取通用行情，支持前复权/后复权。

        `adj=None` 为未复权，`adj="qfq"` 为前复权，`adj="hfq"` 为后复权。
        该接口在 SDK 层实现，权限要求可能高于基础 `daily`。
        """

        validate_ts_code(ts_code)
        validate_adj(adj)
        ts = self._load_module()
        if not self.token:
            raise TushareError("Tushare token is missing. Set TUSHARE_TOKEN first.")
        api = self.pro()
        try:
            df = ts.pro_bar(
                ts_code=ts_code,
                api=api,
                start_date=format_date(start_date),
                end_date=format_date(end_date),
                adj=adj,
                freq="D",
            )
        except Exception as exc:
            raise TushareError("Tushare pro_bar query failed.") from exc
        return normalize_tushare_dates(df if df is not None else pd.DataFrame())

    def daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取每日指标。通常需要 2000 积分起。"""

        validate_ts_code(ts_code)
        return normalize_tushare_dates(
            self._call(
                "daily_basic",
                ts_code=ts_code,
                start_date=format_date(start_date),
                end_date=format_date(end_date),
            )
        )

    def adj_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取复权因子。"""

        validate_ts_code(ts_code)
        return normalize_tushare_dates(
            self._call(
                "adj_factor",
                ts_code=ts_code,
                start_date=format_date(start_date),
                end_date=format_date(end_date),
            )
        )

    def stock_basic(self, *, list_status: str = "L") -> pd.DataFrame:
        """获取股票基础信息。"""

        fields = "ts_code,symbol,name,area,industry,market,list_date"
        return normalize_tushare_dates(
            self._call("stock_basic", exchange="", list_status=list_status, fields=fields)
        )

    def trade_cal(self, start_date: str, end_date: str, *, exchange: str = "SSE") -> pd.DataFrame:
        """获取交易日历。"""

        return normalize_tushare_dates(
            self._call(
                "trade_cal",
                exchange=exchange,
                start_date=format_date(start_date),
                end_date=format_date(end_date),
            )
        )

    def _call(self, api_name: str, **kwargs: object) -> pd.DataFrame:
        pro = self.pro()
        method = getattr(pro, api_name, None)
        if method is None:
            raise TushareError(f"Tushare API not found: {api_name}")
        try:
            df = method(**kwargs)
        except Exception as exc:
            raise TushareError(f"Tushare API {api_name} failed.") from exc
        return df if df is not None else pd.DataFrame()

    def _load_module(self) -> Any:
        if self._ts is not None:
            return self._ts
        try:
            import tushare as ts  # type: ignore[import-not-found]
        except ImportError as exc:
            raise TushareError(
                "tushare is not installed. Run: python -m pip install -r Tools/requirements.txt"
            ) from exc
        self._ts = ts
        return ts

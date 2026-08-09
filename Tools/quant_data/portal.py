"""策略和 Notebook 使用的高层数据入口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from .cache import ParquetCache
from .config import DataConfig
from .mysql_storage import MysqlStorage
from .normalize import normalize_tushare_dates
from .tushare_client import TushareClient
from .validators import assert_daily_bar_quality, format_date, validate_adj, validate_ts_code


@dataclass(frozen=True)
class TradeWindow:
    """用户日期经过交易日历校准后的真实交易窗口。"""

    requested_start: str
    requested_end: str
    start: str
    end: str


class DataPortal:
    """项目内稳定数据接口。"""

    CALENDAR_PADDING_DAYS = 31

    def __init__(self, config: DataConfig | None = None) -> None:
        self.config = config or DataConfig()
        self.cache = ParquetCache(self.config.raw_dir)
        self.mysql = MysqlStorage(self.config.mysql_url) if self.config.mysql_url else None

    def _client(self) -> TushareClient:
        return TushareClient(token=self.config.tushare_token)

    def init_mysql_schema(self) -> None:
        """创建 MySQL 表结构。"""

        if self.mysql is None:
            raise RuntimeError("MYSQL_URL is not configured.")
        self.mysql.init_schema()

    def daily_bars(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        *,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """获取单只股票非复权日线。

        本地文件按“一只股票一个 Parquet”保存。读取时先用交易日历把用户输入
        的起止日期校准到真实交易日，再只检查校准后的首尾交易日是否都在文件中。
        在默认日粒度连续的前提下，首尾都命中就认为中间窗口已经完整。
        """

        validate_ts_code(ts_code)
        requested_start = format_date(start_date)
        requested_end = format_date(end_date)
        window = self._trade_window(requested_start, requested_end)
        params = {"api": "daily", "ts_code": ts_code}
        cache_parts = self._stock_cache_parts("daily", ts_code)

        cached, full_cache = self._read_window_cache(
            cache_parts,
            "trade_date",
            window.start,
            window.end,
            refresh=refresh,
        )
        if cached is not None:
            return cached

        fetch_start, fetch_end = self._contiguous_fetch_window(
            full_cache,
            "trade_date",
            window.start,
            window.end,
        )
        if self.mysql is not None and not refresh:
            if self.mysql.has_fetch("daily", ts_code, fetch_start, fetch_end, params):
                df = self.mysql.read_daily(ts_code, fetch_start, fetch_end)
                merged = self._write_merged_cache(cache_parts, full_cache, df, ["ts_code", "trade_date"])
                return self._slice_date_window(merged, "trade_date", window.start, window.end)

        df = self._client().daily(ts_code, fetch_start, fetch_end)
        assert_daily_bar_quality(df, ts_code=ts_code)
        merged = self._write_merged_cache(cache_parts, full_cache, df, ["ts_code", "trade_date"])
        if self.mysql is not None:
            self.mysql.upsert_daily(df)
            self.mysql.record_fetch("daily", ts_code, fetch_start, fetch_end, rows=len(df), params=params)
        return self._slice_date_window(merged, "trade_date", window.start, window.end)

    def daily_by_trade_date(self, trade_date: str, *, refresh: bool = False) -> pd.DataFrame:
        """获取某个交易日全市场非复权日线。"""

        day = format_date(trade_date)
        params = {"api": "daily", "trade_date": day}
        cache_parts = ("daily_by_trade_date", f"{day}.parquet")

        if not refresh:
            cached = self.cache.read(*cache_parts)
            if cached is not None:
                return normalize_tushare_dates(cached)

        if self.mysql is not None and not refresh:
            if self.mysql.has_fetch("daily_by_trade_date", "ALL", day, day, params):
                df = self.mysql.read_daily_by_trade_date(day)
                self.cache.write(df, *cache_parts)
                return df

        df = self._client().daily_by_trade_date(day)
        self.cache.write(df, *cache_parts)
        if self.mysql is not None:
            self.mysql.upsert_daily(df)
            self.mysql.record_fetch("daily_by_trade_date", "ALL", day, day, rows=len(df), params=params)
        return df

    def pro_bar(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        *,
        adj: str | None = None,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """获取通用行情，可选择前复权/后复权。"""

        validate_ts_code(ts_code)
        validate_adj(adj)
        requested_start = format_date(start_date)
        requested_end = format_date(end_date)
        window = self._trade_window(requested_start, requested_end)
        adj_name = adj or "none"
        params = {"api": "pro_bar", "ts_code": ts_code, "adj": adj_name}
        cache_parts = self._stock_cache_parts("pro_bar", ts_code, adj_name)

        cached, full_cache = self._read_window_cache(
            cache_parts,
            "trade_date",
            window.start,
            window.end,
            refresh=refresh,
        )
        if cached is not None:
            return cached

        fetch_start, fetch_end = self._contiguous_fetch_window(
            full_cache,
            "trade_date",
            window.start,
            window.end,
        )
        if self.mysql is not None and not refresh:
            if self.mysql.has_fetch("pro_bar", ts_code, fetch_start, fetch_end, params):
                df = self.mysql.read_pro_bar(ts_code, fetch_start, fetch_end, adj=adj_name)
                merged = self._write_merged_cache(cache_parts, full_cache, df, ["ts_code", "trade_date"])
                return self._slice_date_window(merged, "trade_date", window.start, window.end)

        df = self._client().pro_bar(ts_code, fetch_start, fetch_end, adj=adj)
        merged = self._write_merged_cache(cache_parts, full_cache, df, ["ts_code", "trade_date"])
        if self.mysql is not None:
            self.mysql.upsert_pro_bar(df, adj=adj_name)
            self.mysql.record_fetch("pro_bar", ts_code, fetch_start, fetch_end, rows=len(df), params=params)
        return self._slice_date_window(merged, "trade_date", window.start, window.end)

    def daily_basic(self, ts_code: str, start_date: str, end_date: str, *, refresh: bool = False) -> pd.DataFrame:
        """获取每日指标。"""

        validate_ts_code(ts_code)
        requested_start = format_date(start_date)
        requested_end = format_date(end_date)
        window = self._trade_window(requested_start, requested_end)
        params = {"api": "daily_basic", "ts_code": ts_code}
        cache_parts = self._stock_cache_parts("daily_basic", ts_code)

        cached, full_cache = self._read_window_cache(
            cache_parts,
            "trade_date",
            window.start,
            window.end,
            refresh=refresh,
        )
        if cached is not None:
            return cached

        fetch_start, fetch_end = self._contiguous_fetch_window(
            full_cache,
            "trade_date",
            window.start,
            window.end,
        )
        if self.mysql is not None and not refresh:
            if self.mysql.has_fetch("daily_basic", ts_code, fetch_start, fetch_end, params):
                df = self.mysql.read_daily_basic(ts_code, fetch_start, fetch_end)
                merged = self._write_merged_cache(cache_parts, full_cache, df, ["ts_code", "trade_date"])
                return self._slice_date_window(merged, "trade_date", window.start, window.end)

        df = self._client().daily_basic(ts_code, fetch_start, fetch_end)
        merged = self._write_merged_cache(cache_parts, full_cache, df, ["ts_code", "trade_date"])
        if self.mysql is not None:
            self.mysql.upsert_daily_basic(df)
            self.mysql.record_fetch("daily_basic", ts_code, fetch_start, fetch_end, rows=len(df), params=params)
        return self._slice_date_window(merged, "trade_date", window.start, window.end)

    def adj_factor(self, ts_code: str, start_date: str, end_date: str, *, refresh: bool = False) -> pd.DataFrame:
        """获取复权因子。"""

        validate_ts_code(ts_code)
        requested_start = format_date(start_date)
        requested_end = format_date(end_date)
        window = self._trade_window(requested_start, requested_end)
        params = {"api": "adj_factor", "ts_code": ts_code}
        cache_parts = self._stock_cache_parts("adj_factor", ts_code)

        cached, full_cache = self._read_window_cache(
            cache_parts,
            "trade_date",
            window.start,
            window.end,
            refresh=refresh,
        )
        if cached is not None:
            return cached

        fetch_start, fetch_end = self._contiguous_fetch_window(
            full_cache,
            "trade_date",
            window.start,
            window.end,
        )
        if self.mysql is not None and not refresh:
            if self.mysql.has_fetch("adj_factor", ts_code, fetch_start, fetch_end, params):
                df = self.mysql.read_adj_factor(ts_code, fetch_start, fetch_end)
                merged = self._write_merged_cache(cache_parts, full_cache, df, ["ts_code", "trade_date"])
                return self._slice_date_window(merged, "trade_date", window.start, window.end)

        df = self._client().adj_factor(ts_code, fetch_start, fetch_end)
        merged = self._write_merged_cache(cache_parts, full_cache, df, ["ts_code", "trade_date"])
        if self.mysql is not None:
            self.mysql.upsert_adj_factor(df)
            self.mysql.record_fetch("adj_factor", ts_code, fetch_start, fetch_end, rows=len(df), params=params)
        return self._slice_date_window(merged, "trade_date", window.start, window.end)

    def stock_basic(self, *, list_status: str = "L", refresh: bool = False) -> pd.DataFrame:
        """获取股票基础信息。"""

        params = {"api": "stock_basic", "list_status": list_status}
        cache_parts = ("stock_basic", f"{list_status}.parquet")
        if not refresh:
            cached = self.cache.read(*cache_parts)
            if cached is not None:
                return normalize_tushare_dates(cached)

        if self.mysql is not None and not refresh:
            if self.mysql.has_fetch("stock_basic", list_status, "", "", params):
                df = self.mysql.read_stock_basic(list_status)
                self.cache.write(df, *cache_parts)
                return df

        df = self._client().stock_basic(list_status=list_status)
        self.cache.write(df, *cache_parts)
        if self.mysql is not None:
            self.mysql.upsert_stock_basic(df, list_status=list_status)
            self.mysql.record_fetch("stock_basic", list_status, "", "", rows=len(df), params=params)
        return df

    def trade_calendar(
        self,
        start_date: str,
        end_date: str,
        *,
        exchange: str = "SSE",
        refresh: bool = False,
    ) -> pd.DataFrame:
        """获取交易日历。"""

        start = format_date(start_date)
        end = format_date(end_date)
        calendar = self._calendar_frame(start, end, exchange=exchange, refresh=refresh)
        return self._slice_date_window(calendar, "cal_date", start, end)

    def _trade_window(self, requested_start: str, requested_end: str, *, exchange: str = "SSE") -> TradeWindow:
        """把自然日窗口校准成真实交易日窗口。"""

        if requested_start > requested_end:
            raise ValueError("start_date must be earlier than or equal to end_date")

        calendar = self._calendar_frame(requested_start, requested_end, exchange=exchange)
        if calendar.empty:
            raise ValueError(f"No calendar data returned for {requested_start}-{requested_end}")

        open_days = calendar.loc[calendar["is_open"].astype(str) == "1", "cal_date"].astype(str).sort_values()
        start_candidates = open_days[open_days >= requested_start]
        end_candidates = open_days[open_days <= requested_end]
        if start_candidates.empty or end_candidates.empty:
            raise ValueError(f"No trading days in requested window {requested_start}-{requested_end}")

        start = str(start_candidates.iloc[0])
        end = str(end_candidates.iloc[-1])
        if start > end:
            raise ValueError(f"No trading days in requested window {requested_start}-{requested_end}")
        return TradeWindow(requested_start=requested_start, requested_end=requested_end, start=start, end=end)

    def _calendar_frame(
        self,
        start_date: str,
        end_date: str,
        *,
        exchange: str,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """读取或补全交易日历。

        交易日历是所有行情窗口判断的基础，所以按交易所保存为一个长期 Parquet 文件。
        读取时会在用户窗口两端各多取一段缓冲，确保周末和节假日能找到邻近交易日。
        """

        start = self._shift_date(start_date, -self.CALENDAR_PADDING_DAYS)
        end = self._shift_date(end_date, self.CALENDAR_PADDING_DAYS)
        cache_parts = ("trade_calendar", f"{exchange}.parquet")

        cached = self.cache.read(*cache_parts)
        cached = self._prepare_calendar(cached, exchange=exchange)
        if not refresh and cached is not None and self._covers_date_window(cached, "cal_date", start, end):
            return self._slice_date_window(cached, "cal_date", start, end)

        fetch_start, fetch_end = self._contiguous_fetch_window(cached, "cal_date", start, end)
        params = {"api": "trade_cal", "exchange": exchange}
        if self.mysql is not None and not refresh:
            if self.mysql.has_fetch("trade_calendar", exchange, fetch_start, fetch_end, params):
                fetched = self.mysql.read_trade_calendar(exchange, fetch_start, fetch_end)
            else:
                fetched = self._client().trade_cal(fetch_start, fetch_end, exchange=exchange)
        else:
            fetched = self._client().trade_cal(fetch_start, fetch_end, exchange=exchange)

        fetched = self._prepare_calendar(fetched, exchange=exchange)
        merged = self._write_merged_cache(cache_parts, cached, fetched, ["exchange", "cal_date"])
        if self.mysql is not None and fetched is not None:
            self.mysql.upsert_trade_calendar(fetched, exchange=exchange)
            self.mysql.record_fetch("trade_calendar", exchange, fetch_start, fetch_end, rows=len(fetched), params=params)
        return self._slice_date_window(merged, "cal_date", start, end)

    def _read_window_cache(
        self,
        cache_parts: tuple[str, ...],
        date_column: str,
        start_date: str,
        end_date: str,
        *,
        refresh: bool,
    ) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
        """读取窗口缓存。

        返回值第一项是“可直接使用的窗口数据”，第二项是完整缓存文件。
        对单股票日线，只检查首尾交易日是否存在，不逐日扫描。
        """

        cached = self.cache.read(*cache_parts)
        if cached is None:
            return None, None

        normalized = normalize_tushare_dates(cached)
        if not refresh and self._covers_date_window(normalized, date_column, start_date, end_date):
            return self._slice_date_window(normalized, date_column, start_date, end_date), normalized
        return None, normalized

    def _contiguous_fetch_window(
        self,
        existing: pd.DataFrame | None,
        date_column: str,
        start_date: str,
        end_date: str,
    ) -> tuple[str, str]:
        """计算为了保持本地文件连续而应向远端请求的日期窗口。

        本地文件默认从最早交易日到最晚交易日是连续的。若新请求在本地窗口外，
        远端请求会从本地边界开始补齐到新边界，而不是只拉用户显式输入的片段。
        """

        if existing is None or existing.empty or date_column not in existing.columns:
            return start_date, end_date

        dates = existing[date_column].dropna().astype(str)
        if dates.empty:
            return start_date, end_date

        local_start = str(dates.min())
        local_end = str(dates.max())
        if start_date < local_start and end_date > local_end:
            return start_date, end_date
        if end_date < local_start:
            return start_date, local_start
        if start_date > local_end:
            return local_end, end_date
        if start_date < local_start:
            return start_date, local_start
        if end_date > local_end:
            return local_end, end_date
        return start_date, end_date

    def _write_merged_cache(
        self,
        cache_parts: tuple[str, ...],
        existing: pd.DataFrame | None,
        incoming: pd.DataFrame | None,
        keys: list[str],
    ) -> pd.DataFrame:
        """把新数据和原 Parquet 数据按主键合并后写回。"""

        frames = []
        if existing is not None and not existing.empty:
            frames.append(normalize_tushare_dates(existing))
        if incoming is not None and not incoming.empty:
            frames.append(normalize_tushare_dates(incoming))
        if not frames:
            return pd.DataFrame()

        merged = pd.concat(frames, ignore_index=True)
        present_keys = [key for key in keys if key in merged.columns]
        if present_keys:
            merged = merged.drop_duplicates(subset=present_keys, keep="last")
        merged = normalize_tushare_dates(merged)
        self.cache.write(merged, *cache_parts)
        return merged

    def _slice_date_window(
        self,
        df: pd.DataFrame,
        date_column: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """按 YYYYMMDD 字符串窗口切片。"""

        if df.empty or date_column not in df.columns:
            return df.copy()
        normalized = normalize_tushare_dates(df)
        dates = normalized[date_column].astype(str)
        return normalized.loc[(dates >= start_date) & (dates <= end_date)].reset_index(drop=True)

    def _covers_date_window(self, df: pd.DataFrame, date_column: str, start_date: str, end_date: str) -> bool:
        """判断缓存是否覆盖窗口首尾日期。"""

        if df.empty or date_column not in df.columns:
            return False
        dates = set(df[date_column].dropna().astype(str))
        return start_date in dates and end_date in dates

    def _prepare_calendar(self, df: pd.DataFrame | None, *, exchange: str) -> pd.DataFrame | None:
        """补齐交易日历的 exchange 字段并做日期标准化。"""

        if df is None:
            return None
        calendar = normalize_tushare_dates(df)
        if not calendar.empty and "exchange" not in calendar.columns:
            calendar["exchange"] = exchange
        return calendar

    @staticmethod
    def _stock_cache_parts(dataset: str, ts_code: str, *prefixes: str) -> tuple[str, ...]:
        """返回单股票 Parquet 缓存路径组件。"""

        return (dataset, *prefixes, f"{ts_code}.parquet")

    @staticmethod
    def _shift_date(value: str, days: int) -> str:
        """按自然日平移 YYYYMMDD 字符串。"""

        dt = datetime.strptime(value, "%Y%m%d") + timedelta(days=days)
        return dt.strftime("%Y%m%d")

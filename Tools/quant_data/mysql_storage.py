"""Tushare 结构化数据的 MySQL 存储层。

SQLAlchemy 只在真正启用 MySQL 时才导入。这样没有安装 MySQL 依赖的用户，
仍然可以继续使用默认 Parquet 缓存，不会因为导入模块就报错。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from .normalize import normalize_tushare_dates


class MysqlStorageError(RuntimeError):
    """启用 MySQL 存储但依赖或连接不可用时抛出。"""


@dataclass
class MysqlStorage:
    """带主键 upsert 和请求日志的结构化 MySQL 缓存。"""

    url: str

    def __post_init__(self) -> None:
        sqla = self._load_sqlalchemy()
        self._sqla = sqla
        self.engine = sqla["create_engine"](self.url, future=True, pool_pre_ping=True)
        self.metadata = sqla["MetaData"]()
        self.tables = self._build_tables()

    def init_schema(self) -> None:
        """创建全部表；已存在的表不会被删除或重建。"""

        self.metadata.create_all(self.engine)

    def has_fetch(
        self,
        endpoint: str,
        resource_key: str,
        start_date: str,
        end_date: str,
        params: dict[str, object] | None = None,
    ) -> bool:
        """检查完全相同的远端请求是否已经成功落库。

        这里先做“精确请求缓存”：接口、标的、起止日期和额外参数全部一致时，
        才直接复用 MySQL 数据。后续如果需要，可以再扩展成区间覆盖判断。
        """

        self.init_schema()
        fetch_log = self.tables["fetch_log"]
        select = self._sqla["select"]
        params_hash = self._params_hash(params)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(fetch_log.c.endpoint).where(
                    fetch_log.c.endpoint == endpoint,
                    fetch_log.c.resource_key == resource_key,
                    fetch_log.c.start_date == start_date,
                    fetch_log.c.end_date == end_date,
                    fetch_log.c.params_hash == params_hash,
                )
            ).first()
        return row is not None

    def record_fetch(
        self,
        endpoint: str,
        resource_key: str,
        start_date: str,
        end_date: str,
        *,
        rows: int,
        params: dict[str, object] | None = None,
    ) -> None:
        """记录一次已经完成的远端请求，用于后续避免重复拉取。"""

        self.init_schema()
        self._upsert_records(
            "fetch_log",
            [
                {
                    "endpoint": endpoint,
                    "resource_key": resource_key,
                    "start_date": start_date,
                    "end_date": end_date,
                    "params_hash": self._params_hash(params),
                    "params_json": json.dumps(params or {}, ensure_ascii=False, sort_keys=True),
                    "rows_count": rows,
                    "fetched_at": datetime.now(),
                }
            ],
        )

    def read_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        query = (
            "select * from tushare_daily "
            "where ts_code = :ts_code and trade_date between :start_date and :end_date "
            "order by trade_date"
        )
        return normalize_tushare_dates(
            self._read_sql(
                query,
                params={"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
            )
        )

    def read_daily_by_trade_date(self, trade_date: str) -> pd.DataFrame:
        query = "select * from tushare_daily where trade_date = :trade_date order by ts_code"
        return normalize_tushare_dates(self._read_sql(query, params={"trade_date": trade_date}))

    def upsert_daily(self, df: pd.DataFrame) -> None:
        self.init_schema()
        self._upsert_dataframe("daily", df)

    def read_pro_bar(self, ts_code: str, start_date: str, end_date: str, *, adj: str) -> pd.DataFrame:
        query = (
            "select * from tushare_pro_bar "
            "where ts_code = :ts_code and adj = :adj "
            "and trade_date between :start_date and :end_date "
            "order by trade_date"
        )
        return normalize_tushare_dates(
            self._read_sql(
                query,
                params={"ts_code": ts_code, "adj": adj, "start_date": start_date, "end_date": end_date},
            )
        )

    def upsert_pro_bar(self, df: pd.DataFrame, *, adj: str) -> None:
        self.init_schema()
        data = df.copy()
        data["adj"] = adj
        self._upsert_dataframe("pro_bar", data)

    def read_stock_basic(self, list_status: str) -> pd.DataFrame:
        query = "select * from tushare_stock_basic where list_status = :list_status order by ts_code"
        return normalize_tushare_dates(self._read_sql(query, params={"list_status": list_status}))

    def upsert_stock_basic(self, df: pd.DataFrame, *, list_status: str) -> None:
        self.init_schema()
        data = df.copy()
        data["list_status"] = list_status
        self._upsert_dataframe("stock_basic", data)

    def read_trade_calendar(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame:
        query = (
            "select * from tushare_trade_calendar "
            "where exchange = :exchange and cal_date between :start_date and :end_date "
            "order by cal_date"
        )
        return normalize_tushare_dates(
            self._read_sql(
                query,
                params={"exchange": exchange, "start_date": start_date, "end_date": end_date},
            )
        )

    def upsert_trade_calendar(self, df: pd.DataFrame, *, exchange: str) -> None:
        self.init_schema()
        data = df.copy()
        data["exchange"] = exchange
        self._upsert_dataframe("trade_calendar", data)

    def read_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        query = (
            "select * from tushare_daily_basic "
            "where ts_code = :ts_code and trade_date between :start_date and :end_date "
            "order by trade_date"
        )
        return normalize_tushare_dates(
            self._read_sql(
                query,
                params={"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
            )
        )

    def upsert_daily_basic(self, df: pd.DataFrame) -> None:
        self.init_schema()
        self._upsert_dataframe("daily_basic", df)

    def read_adj_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        query = (
            "select * from tushare_adj_factor "
            "where ts_code = :ts_code and trade_date between :start_date and :end_date "
            "order by trade_date"
        )
        return normalize_tushare_dates(
            self._read_sql(
                query,
                params={"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
            )
        )

    def upsert_adj_factor(self, df: pd.DataFrame) -> None:
        self.init_schema()
        self._upsert_dataframe("adj_factor", df)

    def _build_tables(self) -> dict[str, Any]:
        s = self._sqla
        table = s["Table"]
        column = s["Column"]
        string = s["String"]
        float_type = s["Float"]
        integer = s["Integer"]
        datetime_type = s["DateTime"]
        text = s["Text"]

        return {
            "daily": table(
                "tushare_daily",
                self.metadata,
                column("ts_code", string(16), primary_key=True),
                column("trade_date", string(8), primary_key=True),
                column("date", datetime_type),
                column("open", float_type),
                column("high", float_type),
                column("low", float_type),
                column("close", float_type),
                column("pre_close", float_type),
                column("change", float_type),
                column("pct_chg", float_type),
                column("vol", float_type),
                column("amount", float_type),
            ),
            "stock_basic": table(
                "tushare_stock_basic",
                self.metadata,
                column("ts_code", string(16), primary_key=True),
                column("list_status", string(1), primary_key=True),
                column("symbol", string(16)),
                column("name", string(64)),
                column("area", string(64)),
                column("industry", string(128)),
                column("market", string(32)),
                column("list_date", string(8)),
                column("list_dt", datetime_type),
            ),
            "pro_bar": table(
                "tushare_pro_bar",
                self.metadata,
                column("ts_code", string(16), primary_key=True),
                column("trade_date", string(8), primary_key=True),
                column("adj", string(8), primary_key=True),
                column("date", datetime_type),
                column("open", float_type),
                column("high", float_type),
                column("low", float_type),
                column("close", float_type),
                column("pre_close", float_type),
                column("change", float_type),
                column("pct_chg", float_type),
                column("vol", float_type),
                column("amount", float_type),
            ),
            "trade_calendar": table(
                "tushare_trade_calendar",
                self.metadata,
                column("exchange", string(16), primary_key=True),
                column("cal_date", string(8), primary_key=True),
                column("date", datetime_type),
                column("is_open", integer),
                column("pretrade_date", string(8)),
            ),
            "daily_basic": table(
                "tushare_daily_basic",
                self.metadata,
                column("ts_code", string(16), primary_key=True),
                column("trade_date", string(8), primary_key=True),
                column("date", datetime_type),
                column("close", float_type),
                column("turnover_rate", float_type),
                column("turnover_rate_f", float_type),
                column("volume_ratio", float_type),
                column("pe", float_type),
                column("pe_ttm", float_type),
                column("pb", float_type),
                column("ps", float_type),
                column("ps_ttm", float_type),
                column("dv_ratio", float_type),
                column("dv_ttm", float_type),
                column("total_share", float_type),
                column("float_share", float_type),
                column("free_share", float_type),
                column("total_mv", float_type),
                column("circ_mv", float_type),
            ),
            "adj_factor": table(
                "tushare_adj_factor",
                self.metadata,
                column("ts_code", string(16), primary_key=True),
                column("trade_date", string(8), primary_key=True),
                column("date", datetime_type),
                column("adj_factor", float_type),
            ),
            "fetch_log": table(
                "tushare_fetch_log",
                self.metadata,
                column("endpoint", string(64), primary_key=True),
                column("resource_key", string(128), primary_key=True),
                column("start_date", string(16), primary_key=True),
                column("end_date", string(16), primary_key=True),
                column("params_hash", string(40), primary_key=True),
                column("params_json", text),
                column("rows_count", integer),
                column("fetched_at", datetime_type),
            ),
        }

    def _upsert_dataframe(self, table_name: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        table = self.tables[table_name]
        columns = {column.name for column in table.columns}
        data = df[[column for column in df.columns if column in columns]].copy()
        records = self._records(data)
        if records:
            self._upsert_records(table_name, records)

    def _upsert_records(self, table_name: str, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        table = self.tables[table_name]
        insert = self._sqla["mysql_insert"]
        non_pk_columns = [column.name for column in table.columns if not column.primary_key]
        with self.engine.begin() as conn:
            for batch in self._chunked(records, 1000):
                stmt = insert(table).values(batch)
                update_values = {column: stmt.inserted[column] for column in non_pk_columns}
                conn.execute(stmt.on_duplicate_key_update(**update_values))

    def _read_sql(self, query: str, *, params: dict[str, Any]) -> pd.DataFrame:
        """用 SQLAlchemy 2.x 的命名参数读取 DataFrame。"""

        return pd.read_sql_query(self._sqla["text"](query), self.engine, params=params)

    @staticmethod
    def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for record in df.to_dict(orient="records"):
            cleaned: dict[str, Any] = {}
            for key, value in record.items():
                if pd.isna(value):
                    cleaned[key] = None
                elif isinstance(value, pd.Timestamp):
                    cleaned[key] = value.to_pydatetime()
                else:
                    cleaned[key] = value
            records.append(cleaned)
        return records

    @staticmethod
    def _params_hash(params: dict[str, object] | None) -> str:
        payload = json.dumps(params or {}, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _chunked(records: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
        return [records[index : index + size] for index in range(0, len(records), size)]

    @staticmethod
    def _load_sqlalchemy() -> dict[str, Any]:
        try:
            from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, Text
            from sqlalchemy import create_engine, select, text
            from sqlalchemy.dialects.mysql import insert as mysql_insert
        except ImportError as exc:
            raise MysqlStorageError(
                "MySQL storage dependencies are missing. Run: python -m pip install -r Tools/requirements.txt"
            ) from exc
        return {
            "Column": Column,
            "DateTime": DateTime,
            "Float": Float,
            "Integer": Integer,
            "MetaData": MetaData,
            "String": String,
            "Table": Table,
            "Text": Text,
            "create_engine": create_engine,
            "mysql_insert": mysql_insert,
            "select": select,
            "text": text,
        }

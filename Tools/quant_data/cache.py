"""本地 Parquet 缓存。

Parquet 比 CSV 更适合后续研究：类型信息保存得更好，读取速度更快，
也更适合逐步迁移到 MySQL、DuckDB 或其他分析数据库。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class ParquetCache:
    """以目录为根的简单 Parquet 缓存。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path(self, *parts: str) -> Path:
        """拼出缓存文件路径。"""

        if not parts:
            raise ValueError("Cache path requires at least one part")
        return self.root.joinpath(*parts)

    def stock_path(self, dataset: str, ts_code: str) -> Path:
        """单只股票一个文件，例如 `daily/600000.SH.parquet`。"""

        return self.path(dataset, f"{ts_code}.parquet")

    def read(self, *parts: str) -> pd.DataFrame | None:
        """读取 Parquet；文件不存在时返回 None。"""

        path = self.path(*parts)
        if not path.exists():
            return None
        try:
            return pd.read_parquet(path)
        except ImportError as exc:
            raise RuntimeError(
                "Parquet support is missing. Run: python -m pip install -r Tools/requirements.txt"
            ) from exc

    def write(self, df: pd.DataFrame, *parts: str) -> Path:
        """写入 Parquet，并自动创建父目录。"""

        path = self.path(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            df.to_parquet(path, index=False)
        except ImportError as exc:
            raise RuntimeError(
                "Parquet support is missing. Run: python -m pip install -r Tools/requirements.txt"
            ) from exc
        return path

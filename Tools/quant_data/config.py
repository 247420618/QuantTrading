"""数据目录和 Tushare token 配置。"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path


TUSHARE_TOKEN_ENV = "TUSHARE_TOKEN"
TS_TOKEN_ENV = "TS_TOKEN"
MYSQL_URL_ENV = "MYSQL_URL"


def load_local_env_file(path: Path) -> dict[str, str]:
    """读取本地脚本里的数据源配置。

    这里只解析白名单里的 `TUSHARE_TOKEN`、`TS_TOKEN` 和 `MYSQL_URL`，不执行
    shell 脚本。这样既能让 Python 自动使用 `Tools/env.local.sh`，又不会运行用户
    本地脚本里的其他命令。
    """

    if not path.exists():
        return {}

    allowed_keys = {TUSHARE_TOKEN_ENV, TS_TOKEN_ENV, MYSQL_URL_ENV}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if not any(line.startswith(f"{key}=") for key in allowed_keys):
            continue
        try:
            parts = shlex.split(line, comments=True, posix=True)
        except ValueError as exc:
            raise ValueError(f"Invalid local env line in {path}: {raw_line!r}") from exc
        if not parts or "=" not in parts[0]:
            continue
        key, value = parts[0].split("=", 1)
        if key in allowed_keys:
            values[key] = value

    return values


@dataclass(frozen=True)
class DataConfig:
    """数据访问配置。"""

    data_root: Path = Path("data")
    source_name: str = "tushare"
    local_env_path: Path = Path("Tools/env.local.sh")
    tushare_token: str | None = None
    mysql_url: str | None = None

    def __post_init__(self) -> None:
        local_values = load_local_env_file(self.local_env_path)
        token = (
            self.tushare_token
            or local_values.get(TUSHARE_TOKEN_ENV)
            or local_values.get(TS_TOKEN_ENV)
            or os.getenv(TUSHARE_TOKEN_ENV)
            or os.getenv(TS_TOKEN_ENV)
            or None
        )
        mysql_url = (
            self.mysql_url
            or local_values.get(MYSQL_URL_ENV)
            or os.getenv(MYSQL_URL_ENV)
            or None
        )
        object.__setattr__(self, "tushare_token", token)
        object.__setattr__(self, "mysql_url", mysql_url)

    @property
    def raw_dir(self) -> Path:
        return self.data_root / "raw" / self.source_name

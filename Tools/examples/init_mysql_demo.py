"""初始化 Tushare MySQL 表结构。"""

from __future__ import annotations

from Tools.quant_data import DataPortal


def main() -> None:
    portal = DataPortal()
    portal.init_mysql_schema()
    print("mysql schema initialized")


if __name__ == "__main__":
    main()

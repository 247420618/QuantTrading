"""下载股票基础信息。"""

from __future__ import annotations

import argparse

from Tools.quant_data import DataPortal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Tushare stock_basic data.")
    parser.add_argument("--list-status", default="L", help="L 上市, D 退市, P 停牌, G 未交易")
    parser.add_argument("--refresh", action="store_true", help="Ignore local cache and download again")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    portal = DataPortal()
    df = portal.stock_basic(list_status=args.list_status, refresh=args.refresh)
    print(df.head())
    print(f"rows={len(df)}")


if __name__ == "__main__":
    main()

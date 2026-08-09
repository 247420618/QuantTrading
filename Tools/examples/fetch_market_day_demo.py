"""下载某个交易日全市场股票非复权日线。"""

from __future__ import annotations

import argparse

from Tools.quant_data import DataPortal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch one trading day's full-market daily bars.")
    parser.add_argument("--trade-date", default="20240102", help="Trading date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--refresh", action="store_true", help="Ignore local cache and download again")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    portal = DataPortal()
    df = portal.daily_by_trade_date(args.trade_date, refresh=args.refresh)
    print(df.head())
    print(f"rows={len(df)}")


if __name__ == "__main__":
    main()

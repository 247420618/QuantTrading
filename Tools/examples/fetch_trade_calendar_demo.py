"""下载交易日历。"""

from __future__ import annotations

import argparse

from Tools.quant_data import DataPortal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Tushare trade calendar.")
    parser.add_argument("--start", default="20240101", help="Start date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", default="20240131", help="End date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--exchange", default="SSE", help="Exchange code, default SSE")
    parser.add_argument("--refresh", action="store_true", help="Ignore local cache and download again")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    portal = DataPortal()
    df = portal.trade_calendar(args.start, args.end, exchange=args.exchange, refresh=args.refresh)
    print(df.head())
    print(f"rows={len(df)}")


if __name__ == "__main__":
    main()

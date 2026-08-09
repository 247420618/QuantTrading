"""下载单只股票非复权日线的最小示例。"""

from __future__ import annotations

import argparse

from Tools.quant_data import DataPortal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch A-share daily bars from Tushare.")
    parser.add_argument("--ts-code", default="600000.SH", help="Tushare code, e.g. 600000.SH")
    parser.add_argument("--start", default="20200101", help="Start date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", default="20201231", help="End date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--refresh", action="store_true", help="Ignore local cache and download again")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    portal = DataPortal()
    df = portal.daily_bars(args.ts_code, args.start, args.end, refresh=args.refresh)
    print(df.tail())
    print(f"rows={len(df)}")


if __name__ == "__main__":
    main()

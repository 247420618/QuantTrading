#!/usr/bin/env bash
#
# Tushare Pro 本地 token 与下载脚本模板。
#
# 使用方式：
# 1. cp Tools/env.example.sh Tools/env.local.sh
# 2. 把 TUSHARE_TOKEN 改成你的 Tushare Pro token
# 3. bash Tools/env.local.sh
#
# 注意：Tools/env.local.sh 已加入 .gitignore，不会同步到 GitHub。

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

source .venv/bin/activate

export TUSHARE_TOKEN='your_tushare_pro_token'

# 设置后会同步写入 MySQL；不设置时只使用本地 Parquet 缓存。
# 先在 MySQL 中创建数据库，再把 user/password 改成你的本机配置。
# export MYSQL_URL='mysql+pymysql://user:password@127.0.0.1:3306/quant_trading?charset=utf8mb4'

python -m Tools.examples.fetch_daily_demo \
  --ts-code 600000.SH \
  --start 20200101 \
  --end 20201231

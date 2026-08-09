# Tools：Tushare 数据接口层

本目录用于存放后续策略、回测和研究会反复调用的数据接口代码。当前数据源切换为 Tushare Pro。目标不是做完整数据平台，而是先建立一个稳定、可缓存、便于替换的数据入口。

## 是否能本地下载

可以。Tushare Pro 的典型流程是：

1. 注册 Tushare Pro 账号；
2. 登录官网，在个人主页复制 token；
3. 在 Python 中设置 token 并创建 `pro_api()`；
4. 调用 `daily()`、`trade_cal()`、`stock_basic()`、`daily_basic()` 等接口；
5. 把返回的 pandas DataFrame 保存到本地。

官方入门文档见 [Tushare Pro 数据接口](https://tushare.pro/document/1?doc_id=131)。当前工具层支持两种本地存储：

- 默认文件缓存：缓存到 `data/raw/tushare/` 下的 Parquet 文件。单只股票数据是一只股票一个 `.parquet` 文件。
- 可选 MySQL：配置 `MYSQL_URL` 后，同步写入 MySQL 表，并记录每次成功请求，便于后续结构化查询。

## 数据范围与费用概览

下面是按官方文档整理的入门相关结论，实际权限以 Tushare 官网权限中心为准：

- **A 股非复权日线 `daily`**：官方权限页写明为“全部历史”，交易日每日盘后更新；基础 120 积分即可调用，120 积分档每分钟 50 次、每天 8000 次，价格 0 元/年。
- **A 股日线接口文档**：`daily` 支持按 `ts_code`、`trade_date`、`start_date`、`end_date` 查询，单次最多约 6000 行；文档说明“一次请求相当于提取一个股票 23 年历史”。
- **每日指标 `daily_basic`**：通常需要 2000 积分起，适合后续做估值、换手率、市值等因子。
- **复权行情 `pro_bar`**：官方说明可提供未复权、前复权、后复权，但股票复权行情通常按更高权限口径管理，入门阶段先用 `daily` 非复权数据更稳。
- **分钟数据**：官方说明需要单独开权限，不属于普通积分权限；历史分钟价格约 2000 元/年，实时分钟约 1000 元/月。
- **积分价格**：官方积分频次表显示 2000 积分约 200 元/年，5000 积分约 500 元/年，10000 积分约 1000 元/年，15000 积分约 1500 元/年。公司机构一般按个人价格 10 倍。

对初学者来说，最合理的路线是：先用 120 积分档的 `daily` 日线数据学习数据落盘、清洗、单股票回测；等需要 `daily_basic`、指数数据、复权行情或更高频次时，再考虑 2000 积分以上。

参考入口：

- [Tushare Pro 调取数据教程](https://tushare.pro/document/1?doc_id=131)
- [Tushare Pro A 股日线行情 daily](https://tushare.pro/document/2?doc_id=27)
- [Tushare Pro 每日指标 daily_basic](https://tushare.pro/document/2?doc_id=32)
- [Tushare Pro 复权行情 pro_bar](https://tushare.pro/document/2?doc_id=109)
- [Tushare PyPI 包](https://pypi.org/project/tushare/)

## 目录结构

```text
Tools/
  README.md
  requirements.txt
  env.example.sh
  examples/
    fetch_daily_demo.py
    fetch_market_day_demo.py
    fetch_stock_basic_demo.py
    fetch_trade_calendar_demo.py
    init_mysql_demo.py
  quant_data/
    tushare_client.py # Tushare 薄封装：token、查询、错误处理
    cache.py          # Parquet 本地缓存
    config.py         # 数据目录和 token 配置
    mysql_storage.py  # MySQL 表结构、upsert 写入和请求日志
    normalize.py      # DataFrame 标准化
    portal.py         # 面向策略代码的数据入口
    validators.py     # 代码、日期、行情质量检查
```

## 安装

在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r Tools/requirements.txt
```

本仓库固定 `tushare==1.4.29`，这是 PyPI 当前显示的版本。后续如果 SDK 有兼容性变化，再明确升级。

## 本地 token 脚本

创建本地脚本：

```bash
cp Tools/env.example.sh Tools/env.local.sh
```

然后编辑 `Tools/env.local.sh`：

```bash
export TUSHARE_TOKEN='你的 Tushare Pro token'
```

`Tools/env.local.sh` 已被 `.gitignore` 忽略，不会同步到 GitHub。

运行默认下载示例：

```bash
bash Tools/env.local.sh
```

也可以不使用本地脚本，直接在当前 Shell 中设置：

```bash
export TUSHARE_TOKEN='你的 Tushare Pro token'
python -m Tools.examples.fetch_daily_demo --ts-code 600000.SH --start 20200101 --end 20201231
```

## MySQL 存储

当你开始反复跑策略和回测时，只靠时间窗口命名的文件会遇到两个问题：同一只股票不同窗口会产生很多重复文件，多个策略之间也不方便高效筛选、连接和复用。当前工具层采用 Parquet 作为默认文件缓存，并支持 MySQL 作为结构化存储：

1. `daily_bars()` 默认先查本地 Parquet 文件。
2. 如果配置了 `MYSQL_URL`，远端拉取后的数据会同步写入 MySQL。
3. 每个 MySQL 数据表都有主键，重复写入时使用 upsert，不会插入重复行情行。
4. `tushare_fetch_log` 会记录已经成功拉取过的“接口 + 标的 + 起止日期 + 参数”。完全相同的请求再次出现时，会直接从 MySQL 读取，不再请求 Tushare。
5. 如果没有配置 `MYSQL_URL`，代码只使用本地 Parquet 缓存。

先在 MySQL 中创建数据库：

```sql
CREATE DATABASE quant_trading
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

然后在 `Tools/env.local.sh` 中加入连接串：

```bash
export MYSQL_URL='mysql+pymysql://user:password@127.0.0.1:3306/quant_trading?charset=utf8mb4'
```

连接串里的 `user`、`password`、端口和数据库名要按你的本机 MySQL 配置修改。如果密码里有 `!`、`@`、`#` 这类特殊字符，建议把整个连接串放在单引号里；如果密码本身包含 `@`、`/`、`:` 等 URL 特殊字符，最好先做 URL 编码。

初始化表结构：

```bash
source .venv/bin/activate
python -m Tools.examples.init_mysql_demo
```

当前会创建这些表：

| 表名 | 用途 |
| --- | --- |
| `tushare_daily` | A 股未复权日线，来自 `daily` |
| `tushare_pro_bar` | 通用行情，包含前复权/后复权参数 |
| `tushare_daily_basic` | 每日指标，如换手率、市值、估值 |
| `tushare_adj_factor` | 复权因子 |
| `tushare_stock_basic` | 股票基础信息 |
| `tushare_trade_calendar` | 交易日历 |
| `tushare_fetch_log` | 成功请求日志，用于避免重复拉取 |

需要注意：MySQL 请求日志当前仍然只做“完全相同请求”的去重；Parquet 文件缓存则按单股票文件做首尾交易日覆盖判断。

## 快速示例

下载浦发银行非复权日线：

```bash
python -m Tools.examples.fetch_daily_demo \
  --ts-code 600000.SH \
  --start 20200101 \
  --end 20201231
```

下载某个交易日全市场日线：

```bash
python -m Tools.examples.fetch_market_day_demo --trade-date 20240102
```

下载当前上市股票基础信息：

```bash
python -m Tools.examples.fetch_stock_basic_demo --list-status L
```

在自己的研究代码里调用：

```python
from Tools.quant_data import DataPortal

portal = DataPortal()
bars = portal.daily_bars("600000.SH", "20200101", "20201231")
one_day = portal.daily_by_trade_date("20240102")
stocks = portal.stock_basic()
calendar = portal.trade_calendar("20240101", "20240131")
```

## 代码格式

Tushare 股票代码格式为：

| 市场 | 示例 |
| --- | --- |
| 上海证券交易所 | `600000.SH` |
| 深圳证券交易所 | `000001.SZ` |
| 北京证券交易所 | `430047.BJ` |

当前工具层不再兼容 BaoStock 或聚宽代码格式。请使用 Tushare 标准 `ts_code`。

## 复权说明

默认 `daily_bars()` 使用 Tushare `daily` 接口，返回**未复权**日线。未复权数据适合模拟真实历史成交价、涨跌停和停牌状态。

如果需要前复权或后复权，可调用：

```python
portal.pro_bar("600000.SH", "20200101", "20201231", adj="qfq")
```

但 `pro_bar` 的复权行情权限通常高于基础 `daily`，初学阶段建议先用未复权日线，把数据获取和回测流程跑通。

## Parquet 缓存

默认 Parquet 缓存路径示例：

```text
data/raw/tushare/daily/600000.SH.parquet
data/raw/tushare/daily_by_trade_date/20240102.parquet
data/raw/tushare/stock_basic/L.parquet
data/raw/tushare/trade_calendar/SSE.parquet
```

`fetch_daily_demo.py` 调用的是 `DataPortal.daily_bars()`，它的本地缓存判断流程是：

1. 先读取 `data/raw/tushare/trade_calendar/SSE.parquet`。如果本地万年历覆盖不足，会自动向 Tushare 补一段带缓冲的交易日历。
2. 如果用户输入的开始日期不是交易日，就向后调整到最近交易日。
3. 如果用户输入的结束日期不是交易日，就向前调整到最近交易日。
4. 再读取 `data/raw/tushare/daily/{ts_code}.parquet`。
5. 只检查校准后的首个交易日和最后一个交易日是否都存在于这个 Parquet 文件。默认该股票文件在日粒度上连续，所以不逐日扫描中间日期。
6. 如果首尾都存在，直接从 Parquet 切片返回。
7. 如果首尾任一不在本地，就计算一个“补齐窗口”后请求 Tushare：缺左边时从新开始日拉到本地最早日；缺右边时从本地最晚日拉到新结束日；如果新请求完全在已有窗口右侧，也会从本地最晚日开始拉，填满中间交易日。
8. 新数据和原文件按 `ts_code + trade_date` 去重合并，再写回同一个股票文件，使本地文件覆盖本次请求窗口，并尽量保持从本地最早日到最晚日连续。

传入 `refresh=True` 会跳过本地缓存命中检查，强制重新请求 Tushare，再和原 Parquet 合并写回，不会把已有的更宽历史窗口截断。

## 当前边界

- Parquet 的单股票文件假设日粒度连续，因此只检查首尾交易日；正常使用 `DataPortal` 会按本地边界向外补齐，但如果未来手工改坏了 Parquet 文件，中间缺口不会在当前版本被逐日发现。
- MySQL 请求日志当前只避免“完全相同请求”的重复拉取；区间级补缺口还没有实现。
- `stock_basic()` 是当前基础证券列表，不等价于严格历史股票池。严肃回测还需要处理退市股票、上市日期和历史成分。
- 财务字段、公告日可得性、复权因子、指数成分、分钟线等问题，后续课程中再逐步补齐。
- Tushare 数据授权、积分、独立权限和频次以官方规则为准，工具层只负责本地调用与缓存。

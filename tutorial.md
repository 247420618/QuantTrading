# 沪深股票量化交易入门到进阶教程

> 更新日期：2026-08-05  
> 适用对象：有应用数学、机器学习、深度学习和强化学习基础，但金融与会计基础较少；有 ETF 投资经验。  
> 目标：建立一套可复现、可证伪、尊重 A 股交易制度的低频量化研究流程。本文不是投资建议，示例策略只用于学习。

## 0. 先建立正确的研究对象

量化交易不是“用模型预测明天涨跌”，而是把一个投资假设完整地写成六个可检验模块：

1. **股票池（universe）**：在当时真正可以买到哪些股票？
2. **信号（signal）**：只使用当时已经公开的信息，如何给股票打分？
3. **组合（portfolio）**：买多少只、每只多大仓位、行业和风格暴露如何约束？
4. **执行（execution）**：信号何时产生，订单何时成交，买不到或卖不掉怎么办？
5. **风险（risk）**：单票、行业、市场和流动性风险如何限制？
6. **评价（evaluation）**：扣除费用后，样本外是否优于一个可投资的基准？

数学和 AI 背景会让你很快掌握第 2、3、6 项，但量化研究最常见的错误往往来自第 1、4 项，以及财务数据的“当时是否可知”。因此，本教程刻意先用简单模型训练研究纪律，再进入机器学习。

## 1. 建议学习路线

不必严格按周执行，但不要跳过前一阶段的验收条件。

| 阶段 | 主题 | 建议产物 | 进入下一阶段的条件 |
| --- | --- | --- | --- |
| 1 | 市场规则、收益率、复权、基准 | 一只股票和一个指数的数据检查报告 | 能解释 T+1、复权、未来函数和幸存者偏差 |
| 2 | 买入持有、均线、突破 | 单资产日频回测 | 信号在收盘生成、次日成交，成本可配置 |
| 3 | 选股与分层回测 | 沪深 300 月频因子报告 | 能画五分组收益、IC、换手率和行业暴露 |
| 4 | 多因子与组合风控 | 20--50 只股票的月频组合 | 有样本外、滚动检验和压力测试 |
| 5 | 统计套利与时变性 | 配对/残差反转实验 | 能估计半衰期并检测参数漂移 |
| 6 | 机器学习排序 | walk-forward 模型报告 | 模型净收益稳定优于线性基线，而不只看预测指标 |
| 7 | 模拟盘和小资金验证 | 每日信号、订单和偏差日志 | 回测、模拟和真实可成交价格的偏差可解释 |

第一阶段的好结果不是“赚得多”，而是得到一个你相信没有穿越、没有漏算成本、可以重复运行的负结果或弱结果。

## 2. 够用的金融基础

### 2.1 收益率而不是价格

简单收益率和对数收益率分别为

$$
r_t=\frac{P_t}{P_{t-1}}-1,\qquad
\ell_t=\log P_t-\log P_{t-1}.
$$

对数收益率便于时间相加；组合收益和真实资金曲线通常使用简单收益率。不要直接在不同股票的绝对价格上比较“高低”。

### 2.2 复权

分红、送股、配股会让原始价格出现机械跳变：

- **不复权**：最接近历史成交价，适合模拟委托价格和涨跌停；计算长期收益时必须另外处理公司行动。
- **前复权**：把历史价格调整到当前价格尺度，适合画图和计算连续收益，但历史价格会随新分红而改变。
- **后复权**：保持早期价格尺度，适合研究累计增长。

BaoStock 的 `adjustflag="2"` 表示前复权，`"1"` 表示后复权，`"3"` 表示不复权。研究信号可用复权序列，执行和涨跌停判断最好保留不复权序列。正式回测应同时保存两套价格并核对总收益口径。

### 2.3 三张财务报表的最小知识集

你不需要先学完整会计学，但做基本面选股前至少要理解：

- **利润表**：收入、毛利、营业利润、净利润；利润可能包含非经常性项目。
- **资产负债表**：资产、负债、股东权益；`资产 = 负债 + 权益`。
- **现金流量表**：经营、投资、融资现金流；利润不等于现金。
- **常用估值**：PE、PB、PS、自由现金流收益率。负利润时 PE 没有通常含义。
- **常用质量**：ROE、ROA、毛利率、经营现金流/净利润、杠杆率、应计项。
- **行业差异**：银行、保险、地产、周期制造和轻资产科技不能只用同一组绝对阈值比较。

最重要的回测规则是：季度结束日不是财报可用日。因子只能从实际公告日之后开始使用，最好再留一个交易日的执行延迟。

### 2.4 风险不是一个标准差

波动率只描述常见波动。你还需要关注最大回撤、尾部损失、流动性、集中度、隔夜跳空、连续跌停无法卖出，以及策略与市场/行业因子的共同暴露。

## 3. 沪深股票的制度约束

截至本文更新日，现行沪深交易规则的共同核心是：投资者买入的普通股票在交收前不得卖出，实行回转交易的品种除外，即通常所说的股票 **T+1**。所以日频回测的最低要求是：在交易日 `t` 收盘后计算信号，最早在 `t+1` 交易；在 `t+1` 买入的股票，不能在同日卖出。

还应建模以下约束：

- 主板股票通常为 10% 涨跌幅，创业板和科创板通常为 20%；首次上市后的特定交易日等存在例外。
- 2026 年 7 月起，沪市主板风险警示股票涨跌幅由此前 5% 调整为 10%。不要把旧规则写死到全历史。
- 停牌时不能成交；一字涨停通常买不到，一字跌停通常卖不出。
- 买入数量有申报单位约束，科创板与主板规则并不完全相同。
- 手续费取决于券商与账户；卖出还涉及证券交易印花税。财政部、税务总局自 2023-08-28 起将证券交易印花税减半。回测参数必须按交易发生时的制度分段，而非用今天的费率覆盖全部历史。
- 自动下单前要确认券商接口、适当性和程序化交易报告等要求。证监会《证券市场程序化交易管理规定（试行）》自 2024-10-08 起施行。

权威入口：

- [上海证券交易所交易规则（2026 年修订）](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml)
- [深圳证券交易所交易规则（2026 年修订）](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)
- [证券市场程序化交易管理规定（试行）](https://www.csrc.gov.cn/csrc/c101954/c7480579/content.shtml)
- [关于减半征收证券交易印花税的公告](https://xj.mof.gov.cn/zcfagui/202311/t20231108_3915476.htm)

## 4. 数据源：从 BaoStock 开始

### 4.1 为什么适合入门

BaoStock 免费、无须注册，接口简单，包含日/周/月 K 线、部分估值和财务字段、交易日、指数成分等，足以完成本教程前半段。截至 2026-08，[PyPI 上的 BaoStock](https://pypi.org/project/baostock/) 最新版为 `0.9.3`。

它适合学习，但不要把“免费”误解为“研究级无缺陷”。正式研究前要审计：

- 数据是否在历史日期可获得，而不是今天回填后的最终值；
- 退市股票和历史指数成分是否完整；
- 分红、复权、停牌和异常值如何编码；
- 财务数据使用的是报告期、公告日还是更新后的值；
- 接口版本、数据授权和服务可用性是否满足你的用途。

可把 AkShare 作为交叉核验源，把交易所公告/上市公司定期报告作为权威源；需要更稳定的逐点历史财务数据时，再评估付费数据。两个免费源数值一致并不能证明它们彼此独立。

### 4.2 环境安装

在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install baostock==0.9.3 pandas numpy scipy statsmodels matplotlib pyarrow jupyterlab
```

建议把原始数据写入 `data/raw/`，清洗后写入 `data/processed/`，研究结果写入 `reports/`。本仓库已忽略 `data/` 和 `reports/`，大文件不会误提交 Git。

### 4.3 最小可运行的数据下载器

下面的例子下载浦发银行 `sh.600000` 的前复权日线。沪市代码前缀为 `sh.`，深市为 `sz.`。

```python
from pathlib import Path

import baostock as bs
import pandas as pd


FIELDS = (
    "date,code,open,high,low,close,preclose,volume,amount,"
    "adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,"
    "psTTM,pcfNcfTTM,isST"
)


def fetch_daily(code: str, start: str, end: str, adjustflag: str = "2") -> pd.DataFrame:
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"BaoStock login failed: {login.error_msg}")

    try:
        rs = bs.query_history_k_data_plus(
            code,
            FIELDS,
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag=adjustflag,
        )
        if rs.error_code != "0":
            raise RuntimeError(f"BaoStock query failed: {rs.error_msg}")

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        df = pd.DataFrame(rows, columns=rs.fields)
    finally:
        bs.logout()

    if df.empty:
        raise ValueError(f"No data returned for {code}")

    df["date"] = pd.to_datetime(df["date"])
    numeric = [c for c in df.columns if c not in {"date", "code"}]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
    df = df.sort_values("date").set_index("date")

    if not df.index.is_unique:
        raise ValueError("Duplicate trading dates found")
    if not df.index.is_monotonic_increasing:
        raise ValueError("Dates are not sorted")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Non-positive prices found")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("OHLC consistency check failed")
    if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("OHLC consistency check failed")

    return df


df = fetch_daily("sh.600000", "2010-01-01", "2025-12-31")
path = Path("data/raw/sh.600000_daily_forward.parquet")
path.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(path)
print(df.tail())
```

第一次运行后，至少人工检查：日期范围、缺失率、重复行、停牌日、价格数量级、成交量为零的日期、复权前后收益差异，以及随机抽取若干日与交易所或券商行情核对。

## 5. 第一个完整实验：双均线趋势策略

### 5.1 假设

如果中期趋势具有延续性，则短期均线高于长期均线时持有股票，否则持有现金。它并不复杂，但能教会你最重要的时间对齐。

- 股票池：单只高流动性股票，仅作教学。
- 买入：交易日 `t` 收盘后，20 日均线高于 60 日均线。
- 成交：`t+1` 开盘，若可成交则买入。
- 卖出：收盘信号反转后的下一个交易日开盘。
- 仓位：0% 或 100%。
- 限制：同一天最多调整一次；这样买入后最早下一交易日卖出，满足 T+1。

这不是一个推荐实盘的仓位方案；单只股票满仓只是为了让时序和成本清晰。

### 5.2 一个透明的向量化原型

```python
import numpy as np
import pandas as pd


def performance_metrics(returns: pd.Series) -> pd.Series:
    returns = returns.dropna()
    if returns.empty:
        raise ValueError("No returns to evaluate")

    equity = (1.0 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    years = len(returns) / 252.0
    cagr = equity.iloc[-1] ** (1.0 / years) - 1.0
    ann_vol = returns.std(ddof=1) * np.sqrt(252.0)
    sharpe = np.nan if ann_vol == 0 else returns.mean() * 252.0 / ann_vol
    max_dd = drawdown.min()

    return pd.Series(
        {
            "CAGR": cagr,
            "annual_volatility": ann_vol,
            "Sharpe_rf0": sharpe,
            "max_drawdown": max_dd,
            "Calmar": np.nan if max_dd == 0 else cagr / abs(max_dd),
            "daily_win_rate": (returns > 0).mean(),
        }
    )


def backtest_dual_ma(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 60,
    buy_cost: float = 0.0008,
    sell_cost: float = 0.0013,
) -> tuple[pd.DataFrame, pd.Series]:
    if fast >= slow:
        raise ValueError("fast must be smaller than slow")

    out = df.copy()
    out["ma_fast"] = out["close"].rolling(fast).mean()
    out["ma_slow"] = out["close"].rolling(slow).mean()

    # t 日收盘产生信号，shift(1) 后才成为 t+1 日开盘持仓。
    close_signal = (out["ma_fast"] > out["ma_slow"]).astype(float)
    out["position_at_open"] = close_signal.shift(1).fillna(0.0)

    # 该持仓赚取从本日开盘到下一交易日开盘的收益。
    out["next_open_return"] = out["open"].shift(-1) / out["open"] - 1.0
    delta = out["position_at_open"].diff().fillna(out["position_at_open"])
    out["buy_turnover"] = delta.clip(lower=0.0)
    out["sell_turnover"] = (-delta.clip(upper=0.0))
    out["cost"] = (
        out["buy_turnover"] * buy_cost
        + out["sell_turnover"] * sell_cost
    )
    out["strategy_return"] = (
        out["position_at_open"] * out["next_open_return"] - out["cost"]
    )
    out["benchmark_return"] = out["next_open_return"]

    valid = out["strategy_return"].notna()
    stats = performance_metrics(out.loc[valid, "strategy_return"])
    stats["annual_turnover"] = (
        out.loc[valid, ["buy_turnover", "sell_turnover"]].sum(axis=1).mean() * 252
    )
    stats["average_exposure"] = out.loc[valid, "position_at_open"].mean()
    return out, stats


df = pd.read_parquet("data/raw/sh.600000_daily_forward.parquet")
result, strategy_stats = backtest_dual_ma(df)
benchmark_stats = performance_metrics(result["benchmark_return"])
print(pd.concat({"dual_ma": strategy_stats, "buy_hold": benchmark_stats}, axis=1))
```

`buy_cost` 和 `sell_cost` 是包含佣金、税费和滑点的**教学假设**，不是统一费率。卖出成本设得更高，是为了容纳卖出侧印花税。你需要用自己的券商费率替换，并做至少 `0.5x/1x/2x` 成本压力测试。

这个原型仍然没有处理涨跌停无法成交、停牌、100 股整数手、最低佣金、现金余额和部分成交。因此它适合验证信号，不足以给出实盘收益结论。下一步应把完全相同的订单逻辑移入事件驱动回测器，并逐笔对账。

### 5.3 必做实验

1. 比较 `5/20`、`20/60`、`60/120`，但记录你一共尝试了多少组参数。
2. 把成交时间错误地改成信号当日收盘，观察“未来函数”能美化多少结果，然后删掉错误版本。
3. 分别使用前复权、不复权价格，查清差异来自哪里。
4. 分牛市、熊市、震荡市报告结果，而不是只报告全样本。
5. 用沪深 300 的可投资 ETF 做基准实验；先确认数据源确实支持该代码和复权口径。

## 6. 市面上常见的公开策略地图

下面列的是研究模板，不是收益承诺。海外经典结果只能作为假设；A 股的交易限制、投资者结构和样本期不同，必须重新检验。例如，一项覆盖 2000--2019 年 A 股的 32 类异常研究发现，价值、风险和交易类异常较明显，而规模、质量和普通过去收益类证据更弱，残差动量和反转是例外。

| 难度 | 策略族 | 典型选股/信号 | 常见买入时机 | 常见卖出时机 | 主要风险 |
| --- | --- | --- | --- | --- | --- |
| 0 | 买入持有 | 宽基 ETF 或固定股票池 | 固定日期 | 长期持有/再平衡 | 市场风险，不能区分 alpha 与 beta |
| 1 | 趋势/动量 | 均线、过去 6--12 月收益、52 周高点、突破 | 收盘确认后次日 | 趋势反转、持有期到期 | 震荡期反复交易，A 股个股动量不一定稳定 |
| 1 | 均值回归 | RSI、布林带、短期超跌、行业内残差 | 超跌后次日 | 回归均值、时间止损 | “便宜”可能是基本面恶化，跌停无法止损 |
| 2 | 价值 | 低 PB、低 PE、低 EV/EBITDA、高股息 | 月/季调仓 | 排名跌出、估值修复 | 价值陷阱、行业结构偏差、财报滞后 |
| 2 | 质量 | 高 ROE、稳定毛利、低应计、现金流好 | 财报公开后再平衡 | 质量恶化或排名跌出 | 会计口径、修正公告、行业不可比 |
| 2 | 低波/低风险 | 低波动、低 beta、低特质波动 | 月度调仓 | 风险排名上升 | 拥挤、利率敏感、上涨期落后 |
| 3 | 多因子 | 价值+质量+动量+低波的横截面排名 | 固定再平衡日 | 下期重新排名 | 因子共线、风格漂移、多重检验 |
| 3 | 配对/统计套利 | 同行业价差、协整残差、ETF 相对价值 | spread 偏离若干标准差 | 回归均值或时间止损 | 做空受限、关系断裂、半衰期漂移 |
| 4 | 事件驱动 | 业绩预告、回购、分红、指数调整 | 公告可见后的下一可交易时点 | 固定事件窗结束 | 公告时间戳、抢跑、涨停买不到 |
| 4 | 机器学习排序 | 量价+基本面+分析师/文本特征 | 按预测横截面排名调仓 | 下个再平衡期 | 泄漏、非平稳、成本、解释困难 |
| 5 | 深度学习/RL | 时序表征、组合策略、执行策略 | 由策略模型输出 | 由策略模型输出 | 状态/奖励错配、样本效率、模拟器偏差 |

公开研究入口：

- 技术规则的经典出发点是均线和区间突破；后续研究也发现公开后预测能力可能衰减，正好说明策略会适应和失效：[moving-average rule 的后续证据](https://www.sciencedirect.com/science/article/pii/S1042443115000724)。
- 海外横截面动量经典论文：[Jegadeesh and Titman (1993)](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x)。
- 价值和规模因子的经典框架：[Fama and French (1993)](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library/f-f_factors.html)。
- 配对交易经典研究：[Gatev, Goetzmann and Rouwenhorst](https://www.nber.org/papers/w7032)。
- A 股异常的直接证据：[Jansen, Swinkels and Zhou (2021)](https://www.sciencedirect.com/science/article/pii/S0927538X21001141)。

## 7. 从单因子到多因子选股

### 7.1 定义 point-in-time 股票池

最容易犯的错误是拿“今天的沪深 300 成分股”回测十年前。正确做法是在每个调仓日查询或还原当时成分股，并保留后来退市的股票。入门时可调用 BaoStock 的 `query_hs300_stocks(date=...)`，但要抽样核对它返回的历史成分是否完整。

初始股票池建议：

- 当时的沪深 300 成分股；
- 排除上市不足 120 个交易日的股票；
- 排除停牌、不可交易和数据不完整股票；
- 初期排除 ST/*ST，等回测器能正确处理后再纳入；
- 过滤过去 20 日成交额过低的股票；
- 不使用未来才知道的退市标签过滤历史股票。

### 7.2 单因子分层回测

假设研究“低波动”因子：

$$
\sigma_{i,t}=\mathrm{Std}(r_{i,t-59:t}).
$$

每月末：

1. 用截至当日的数据计算 60 日波动率；
2. 在行业内 winsorize，再转成 z-score，避免行业结构主导结果；
3. 按因子从低到高分成五组；
4. 下一个交易日开盘建仓，持有到下月调仓；
5. 比较五组的净值、Q1-Q5 差、多空差（仅作研究）和换手率；
6. A 股个股做空受限，实盘方案通常是只买最优组，并用宽基 ETF 或股指工具管理 beta；工具适当性和规则需另行确认。

因子有效性的最低证据不是“最高组涨了”，而是：分组大致单调、Rank IC 有正确方向、跨年份稳定、扣除成本仍存在、不是某个行业或少数股票贡献。

### 7.3 常见因子定义

- **价值**：`-log(PB)`、盈利收益率 `E/P`、现金流/市值。负分母和极端值要单独处理。
- **质量**：ROE、毛利率稳定性、经营现金流/资产、低应计、低杠杆。
- **动量**：过去 12 个月收益跳过最近 1 个月，即 `R(t-252, t-21)`；A 股普通个股动量证据有争议，应同时测试短期反转和残差动量。
- **低风险**：过去 60/120 日波动率、市场 beta、特质波动率。
- **流动性**：成交额、换手率、Amihud 非流动性指标；小盘与低流动性溢价可能被交易成本吞掉。

### 7.4 多因子组合

先使用可解释的线性组合：

$$
s_{i,t}=w_v z^{value}_{i,t}+w_q z^{quality}_{i,t}
+w_m z^{momentum}_{i,t}+w_l z^{lowvol}_{i,t}.
$$

第一版令权重相等，不要立即优化。每月买入前 20--50 只，等权或按风险倒数加权，并设置：

- 单票上限 5%；
- 单行业相对基准偏离上限；
- 组合 beta 范围；
- 单次调仓换手上限；
- 过去成交额的一小部分作为最大订单规模；
- 排名缓冲区，例如持仓跌出前 30% 才卖，降低边界抖动。

只有等权线性基线在样本外成立后，才值得研究协方差收缩、风险预算或带成本的凸优化。

## 8. 回测：把策略变成因果实验

### 8.1 四个时间必须分开

对每条数据记录以下时间：

1. `period_end`：指标属于哪个报告期；
2. `published_at`：市场何时看到它；
3. `signal_at`：策略何时计算信号；
4. `fill_at`：订单何时以及以什么价格成交。

必须满足 `period_end <= published_at <= signal_at < fill_at`。对于收盘价因子，最朴素的设定是 `signal_at=t close`、`fill_at=t+1 open`。

### 8.2 必须防止的偏差

- **前视偏差**：使用未来价格、未来指数成分或后来修订的财报。
- **幸存者偏差**：只保留今天还上市的公司。
- **选择偏差**：试了 500 个策略，只报告最好一个。
- **数据窥探**：反复看测试集再改特征和参数。
- **不可成交偏差**：假设涨停能买、跌停能卖、停牌能换仓。
- **成本偏差**：忽略佣金最低收费、印花税、滑点和市场冲击。
- **容量偏差**：小盘股历史收益高，但你的订单占成交量比例过大。
- **基准偏差**：拿高风险小盘组合与低风险宽基收益直接比较。

### 8.3 数据集切分

金融时间序列不能随机打乱。建议：

- **训练集**：估计模型和候选参数；
- **验证集**：选择少量超参数；
- **测试集**：冻结策略后只看一次；
- **walk-forward**：例如用过去 5 年训练，下一年测试，然后向前滚动；
- 标签跨越多个日期时，对训练/测试边界做 purge/embargo，避免重叠标签泄漏。

每次实验写入一个 registry：策略版本、数据快照哈希、特征、参数、成本假设、测试次数和结果。多重测试次数本身就是评价数据。

### 8.4 评价指标

**收益和风险**

- 年化收益 CAGR、年化波动率、Sharpe、Sortino、Calmar；
- 最大回撤、回撤持续时间、VaR/CVaR（仅作尾部摘要，不当作完整风险模型）；
- 月度胜率、最差日/周/月、偏度和峰度。

**相对基准**

- 超额收益、信息比率；
- 对市场、规模、价值、行业等因子回归后的 alpha；
- 上涨/下跌市场捕获率；
- beta 和行业暴露稳定性。

**信号质量**

- Pearson IC 与 Spearman Rank IC；
- IC 均值、标准差和 `ICIR = mean(IC)/std(IC)`；
- 因子五分组单调性；
- 1/5/10/20/60 日 IC decay；
- 分行业、分市值、分市场状态的条件表现。

**可交易性**

- 单边和双边换手率、持仓数量、集中度；
- 成本占毛收益比例；
- 订单占日成交额比例、未成交比例；
- 对成本、成交延迟和容量假设的敏感性。

不要使用固定的“Sharpe > 1 就有效”作为判据。日频收益有自相关、非正态和多重选择问题。至少使用 block bootstrap 给指标区间估计，并记录所有试验。Deflated Sharpe Ratio 专门校正非正态与多重选择造成的绩效膨胀，见 [Bailey and Lopez de Prado (2014)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)。

### 8.5 压力测试清单

一个候选策略至少应通过：

- 参数从单点改为邻域，绩效不能出现针尖峰值；
- 成本和滑点提高到基准的 2 倍；
- 成交延迟 1--2 个交易日；
- 去掉收益贡献最大的 5--10 个交易或股票；
- 分年份、行业、市值和波动状态检验；
- 调仓日平移若干天；
- 更换相近但独立的数据源抽样复核；
- 与等风险、等换手或随机排序的 placebo 策略比较；
- 样本外和纸面交易结果方向一致。

## 9. 半衰期、信号期限与可延续性

### 9.1 均值回归过程的半衰期

若价差或残差近似 AR(1)：

$$
x_t=\alpha+\phi x_{t-1}+\epsilon_t,
$$

在 $0 < \phi < 1$ 时，冲击衰减一半所需期数为

$$
h_{1/2}=-\frac{\ln 2}{\ln \phi}.
$$

```python
import numpy as np
import statsmodels.api as sm


def ar1_half_life(spread):
    x = spread.dropna()
    y = x.iloc[1:].to_numpy()
    x_lag = sm.add_constant(x.iloc[:-1].to_numpy())
    phi = sm.OLS(y, x_lag).fit().params[1]

    if not 0 < phi < 1:
        return {"phi": phi, "half_life": np.nan}
    return {"phi": phi, "half_life": -np.log(2.0) / np.log(phi)}
```

半衰期不是策略保质期。AR(1) 设定可能错误，`phi` 也会随市场状态变化。要滚动估计、报告置信区间，并做单位根/协整和结构突变检验。若半衰期接近或超过你的训练窗，估计通常没有多少操作意义。

### 9.2 选股信号的“寿命”

对横截面因子，更实用的是 IC decay：在 $t$ 的因子分数与未来 $h \in \{1,5,10,20,60\}$ 日收益分别计算 Rank IC。IC 何时衰减到初始值一半，可以称为经验信号半衰期，但它只是描述统计，不应强行套指数衰减。

信号持有期应综合三件事：预测衰减、调仓成本、风险暴露漂移。最强预测点不一定是净收益最优点。

### 9.3 策略是否正在失效

维护滚动监控：

- 12/24 个月滚动净 Sharpe、Rank IC 和 alpha；
- 实际滑点与回测滑点；
- 因子分布、缺失率、行业和 beta 暴露；
- 模型参数或特征重要性稳定性；
- 预测排序与实际收益排序的一致性；
- 组合换手、容量和拥挤代理变量。

失效判定必须在上线前写好。例如：连续若干再平衡期 IC 低于历史置信带、实际成本超过毛 alpha 的某个比例、数据分布严重漂移时降仓或暂停。不要看到回撤后临时改变标准。

## 10. 机器学习路线：发挥你的优势但延后复杂度

### 10.1 把问题设为横截面排序

对 A 股低频选股，通常比“预测单只股票明天涨跌”更清晰的任务是：在每个调仓日预测未来 20 个交易日相对行业或基准的收益排序。

$$
y_{i,t}=R_{i,t\rightarrow t+20}-R_{benchmark,t\rightarrow t+20}.
$$

输入可包括：

- 量价：过去收益、波动、换手、量价相关、距离高点；
- 基本面：估值、盈利、质量、成长、杠杆，但必须按公告日滞后；
- 横截面：行业内排名、市值中性化残差；
- 市场状态：指数趋势、横截面离散度、市场波动和流动性。

先比较线性回归/Logistic、Ridge/Elastic Net，再用 LightGBM/CatBoost。评价 Rank IC、分层收益和扣费后的组合结果，不要只看 MSE、AUC 或训练 loss。

### 10.2 时间和横截面的泄漏

- 标准化、缺失值填充和特征选择必须只在训练窗拟合；
- 同一日期的股票属于一个横截面组，不应随机拆到训练和测试两边；
- 未来 20 日标签彼此重叠，普通 K-fold 会泄漏；
- 公司基本面发布频率低，不要把同一份季度数据复制成几百个“独立日样本”；
- 任何使用全样本行业均值、全样本 PCA 或全样本 winsorize 的步骤都会泄漏。

### 10.3 深度学习与强化学习放在哪里

深度模型适合有大量横截面和序列样本、明确 inductive bias 的场景，但金融数据的有效独立样本远少于行数。先证明它稳定超过线性/树模型，再谈复杂结构。

强化学习更适合：

- 在已有 alpha 下优化换手和仓位路径；
- 在较高频数据与可信成交模拟器下研究执行；
- 处理带约束的动态资产配置。

它不适合作为第一个策略，因为环境非平稳、反事实不可观测、奖励高度噪声，且一个乐观的成交模拟器足以让策略学会利用模拟漏洞。

当进入 AI 阶段，可评估 [Microsoft Qlib](https://qlib.org.cn/en/latest/) 的数据、模型、工作流和组合评估框架；进入事件驱动回测时，可考察 [RQAlpha](https://github.com/ricequant/rqalpha) 或 [Backtrader](https://www.backtrader.com/docu/)。框架能提供订单、费用和滑点机制，但不会自动修复错误的数据时间戳和市场规则。

## 11. 一个推荐的首个多股票项目

项目题目：**沪深 300 月频价值-质量-低波组合**。

### 11.1 明确规范

- 股票池：每个调仓日当时的沪深 300 成分股；
- 因子：`-PB` 排名、ROE/现金流质量排名、60 日低波排名；
- 处理：行业内 winsorize 和 z-score，再等权相加；
- 调仓：每月最后一个交易日收盘计算，下一交易日开盘成交；
- 持仓：前 30 只等权，单票不超过 5%，行业相对基准设上限；
- 卖出：跌出前 60 名，使用缓冲带降低换手；
- 基准：沪深 300 可投资 ETF 或全收益指数，口径必须一致；
- 成本：按历史分段的佣金/税费，加至少三档滑点；
- 验证：扩展窗 walk-forward，每年输出一次真正样本外结果。

### 11.2 研究问题

1. 每个单因子是否有分组单调性？
2. 合成后提升来自信息互补，还是只是更偏向某个行业/市值？
3. 行业中性化前后，毛收益、风险和换手如何变化？
4. 财报公告延迟 1、5、20 个交易日后结果是否仍存在？
5. 成本翻倍、成交延迟一天后是否仍优于基准？
6. 去掉小市值 20% 股票后是否仍成立？
7. 最佳年份和最差年份分别由什么暴露贡献？

### 11.3 验收产物

- `data_manifest.json`：来源、版本、下载时间、字段和哈希；
- `factor_definition.md`：公式、方向、缺失值和可用时间；
- `backtest_config.yaml`：股票池、调仓、成本和约束；
- `trades.parquet`：每一笔目标订单、实际成交/拒绝原因；
- `report.html`：净值、回撤、分层、IC、换手、暴露、压力测试；
- `experiment_registry.csv`：包括失败实验和总试验数。

## 12. 从研究到模拟盘

在投入真实资金前按顺序通过：

1. **代码回放**：固定数据快照，多次运行结果完全一致。
2. **事件回测**：能处理 T+1、停牌、涨跌停、整数股和资金不足。
3. **影子运行**：每天收盘生成次日订单，但不下单；次日记录真实可成交价格。
4. **模拟盘**：验证券商接口、订单状态、撤单、重试和日终对账。
5. **极小资金**：只验证执行偏差和运维，不因为短期盈利就扩大仓位。
6. **逐步放大**：仅当实际滑点、未成交率、暴露和风险都落在预设范围内。

上线系统还需有：数据陈旧检测、重复下单保护、最大订单/仓位限制、异常价格保护、断线恢复、人工停止开关、订单与持仓对账、不可篡改日志。不要把研究 notebook 直接连接券商下单。

## 13. 研究纪律模板

每个策略在写代码前先填一张卡：

```text
策略名称：
经济/行为假设：为什么可能存在，而不是发现了什么相关性？
股票池：当时可知吗？包含退市股吗？
信号公式：
信息可用时间：
下单和成交时间：
持有/退出规则：
成本与不可成交假设：
主要风险暴露：
训练/验证/测试划分：
最多允许尝试的参数组：
预先定义的成功标准：
预先定义的暂停/失效标准：
最可能推翻该策略的实验：
```

数学博士最有价值的优势不是能构造更复杂的模型，而是能把“为什么有效”“什么条件下无效”“观察到这个结果的概率有多大”写成可证伪问题。量化研究的成熟标志，也不是曲线更漂亮，而是你能准确说明曲线里哪些是风险补偿、哪些可能是数据偏差、哪些在真实交易中拿不到。

## 14. 推荐阅读顺序

1. 先通读沪深交易规则中交易时间、回转交易、申报、涨跌幅和异常交易部分。
2. 用 BaoStock 完成第 4、5 节，并逐行解释时间对齐。
3. 阅读经典动量、Fama-French 和配对交易论文，只把它们当作待复现假设。
4. 阅读 A 股异常研究，比较海外事实为什么不能直接迁移。
5. 学习 backtest overfitting、Deflated Sharpe Ratio、block bootstrap 和 walk-forward。
6. 完成第 11 节项目后，再进入 Qlib、梯度提升树、深度模型和强化学习。

最合适的下一步不是再找一个“更赚钱”的策略，而是把第一个双均线实验做成可重复的基线，然后用同一套数据、成本和评估协议逐个替换信号。这样每一次复杂化才有可解释的增量。

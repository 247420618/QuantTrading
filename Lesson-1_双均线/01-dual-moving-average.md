# 1.1 双均线趋势策略：从信号到现金账户回测

本课目标不是证明双均线能稳定赚钱，而是把一个最常见的技术规则写成可复现、可检查、可扩展的量化实验。完成本课后，你应该能回答四个问题：

1. 双均线的“预测”到底预测了什么；
2. 如何把均线信号转成明确的买入、卖出、持有规则；
3. 如何在 A 股 T+1 语境下避免未来函数；
4. 如何用现金、持股、交易成本和组合市值评价策略，而不是只看抽象收益率。

配套代码：

```bash
python Lessons-1/dual_moving_average.py \
  --ts-code SH.600000 \
  --start 20200101 \
  --end 20260731 \
  --fast-window 20 \
  --slow-window 60 \
  --ma-type sma \
  --initial-capital 100000 \
  --plot
```

## 问题导入

初学者常听到一句话：“短期均线上穿长期均线，说明趋势转强；短期均线下穿长期均线，说明趋势转弱。” 这句话很容易被误解成“均线能预测明天涨跌”。更严谨的理解是：

- 均线不是价格的因果变量，它只是历史价格的平滑摘要；
- 双均线不是预测价格点位，而是在做趋势状态分类；
- 快线高于慢线表示近期价格相对长期均值更强；
- 快线低于慢线表示近期价格相对长期均值更弱；
- 这个状态可能延续，也可能快速反转，所以必须通过回测和样本外检验评估。

对你这样的数学背景来说，可以把双均线看作一种极简单的低通滤波和状态切换模型。它牺牲反应速度，换取对噪声的抑制。

但仅有信号还不够。真实策略至少还要回答：

- 初始本金是多少；
- 起始是否持仓；
- 每次买入用多少资金；
- 每次卖出卖多少仓位；
- 用哪一个价格成交；
- 是否扣交易成本、滑点、印花税；
- 今天收盘得到的信号，什么时候才能执行；
- 策略最后的本金涨跌幅是否跑赢这只股票自身涨跌幅。

本课代码就围绕这些问题组织。

## 合理假设

我们先把口语规则改写成可证伪假设：

**假设 1：价格存在局部趋势。**

如果市场短期内存在趋势延续，那么近期均价高于长期均价时，下一段时间继续上涨的概率可能更高。

**假设 2：快慢均线差可以刻画趋势状态。**

快线使用较短窗口，慢线使用较长窗口。快线高于慢线时，认为处于多头状态；否则空仓。

**假设 3：信号不能当天立即吃到同一根 K 线收益。**

日线数据中，今天收盘后才知道今天的收盘价和均线，因此今天产生的信号默认下一交易日才执行。代码里默认 `--execution-lag 1`，含义是用第 $t-1$ 日收盘后的信号，在第 $t$ 日成交。

**假设 4：从现金和空仓开始。**

脚本默认初始本金为 `100000` 元，初始股数为 0。只有出现买入条件后才建仓。这比“假设一开始已经按信号持仓”更贴近新手手工理解。

**假设 5：成交约束先用简化版。**

默认按下一交易日开盘价成交，买入按 `100` 股整数手取整，卖出时允许清掉全部剩余股数。代码暂时没有模拟涨跌停无法成交、停牌、最低佣金、盘口冲击和部分成交，这些会放到后续课程逐步补。

**假设 6：单只股票 Parquet 文件在交易日粒度上连续。**

`DataPortal` 会先用交易日历校准用户输入日期，再判断本地 Parquet 是否覆盖校准后的首尾交易日。如果不覆盖，会从本地边界向外补齐，尽量保持本地文件连续。

## 相关理论与知识

### Step 1：计算双均线

简单移动平均是固定窗口的算术平均。若收盘价为 $C_t$ ，窗口长度为 $L$ ，则：

```math
\mathrm{SMA}_{t,L}=\frac{1}{L}\sum_{j=0}^{L-1}C_{t-j}.
```

SMA 的优点是直观，缺点是窗口内所有价格权重相同，窗口外价格权重突然变成 0。因此它对窗口边界比较敏感。

指数移动平均给最近价格更高权重。常见递推形式是：

```math
\alpha_L=\frac{2}{L+1},
```

```math
\mathrm{EMA}_{t,L}=\alpha_L C_t+(1-\alpha_L)\mathrm{EMA}_{t-1,L}.
```

EMA 相比 SMA 更快响应新价格，但也更容易被短期波动扰动。短线策略常用 EMA，较慢的趋势跟随常用 SMA 或更长窗口 EMA。

代码中对应函数是：

```python
moving_average(series, window=20, ma_type="sma", min_periods=None)
calculate_dual_moving_average(...)
```

`moving_average` 负责计算单条均线；`calculate_dual_moving_average` 负责同时生成快线、慢线、均线差、趋势状态、金叉和死叉。

### Step 2：把均线变成交易策略

设快线窗口为 $F$ ，慢线窗口为 $S$ ，并要求 $F<S$ 。令 $M_{t,F}$ 为快线， $M_{t,S}$ 为慢线。最基础状态信号为：

```math
s_t=
\begin{cases}
1, & M_{t,F}>M_{t,S};\\
0, & M_{t,F}\le M_{t,S}.
\end{cases}
```

这里 $s_t=1$ 表示趋势多头， $s_t=0$ 表示趋势非多头。在 A 股普通股票不能裸卖空的学习设定下，我们先只做多或空仓，不做做空。

主流双均线交易规则有两种写法。

第一种是 **金叉/死叉规则**，也是本课默认规则：

- 买入：昨天收盘后观察到快线从慢线下方上穿慢线；
- 卖出：昨天收盘后观察到快线从慢线上方下穿慢线；
- 其他时间：保持原仓位。

第二种是 **趋势状态规则**：

- 如果当前空仓，且上一交易日收盘后快线高于慢线，则买入；
- 如果当前持仓，且上一交易日收盘后快线不高于慢线，则卖出；
- 其他时间：保持原仓位。

两者差别在于：金叉/死叉规则更强调“状态切换事件”，趋势状态规则更强调“当前是否处于多头区间”。如果你的回测从样本中途开始，而样本第一段已经处于多头趋势，趋势状态规则会更快入场；金叉/死叉规则会等到下一次金叉才入场。

代码中对应函数是：

```python
decide_trade_action(signal_row, shares=shares, entry_rule="crossover", exit_rule="crossover")
```

你可以用参数切换：

```bash
--entry-rule crossover --exit-rule crossover
--entry-rule trend --exit-rule trend
```

### Step 3：账户级回测

很多入门资料会直接写：

```math
r^{\mathrm{strategy}}_t=s_{t-1}r_t.
```

这适合快速看信号方向，但它忽略了现金、整手买入、买卖成本和实际成交价。本课改成账户级回测：

- 起始现金为 $X$ ，起始股数为 0；
- 第 $t-1$ 日收盘后得到信号；
- 第 $t$ 日按指定成交价买入或卖出；
- 收盘后用收盘价估值组合；
- 用组合市值和买入持有基准比较。

买入时，如果计划投入现金为 $B_t$ ，买入成交价为 $P_t^{\mathrm{buy}}$ ，买入成本率为 $c_b$ ，则可买股数近似为：

```math
q_t=
\left\lfloor
\frac{B_t}{P_t^{\mathrm{buy}}(1+c_b)\cdot 100}
\right\rfloor
\cdot 100.
```

这里的 `100` 是默认整手约束。若设置 `--lot-size 1`，就等价于允许按 1 股取整。

买入后现金更新为：

```math
\mathrm{cash}_t=\mathrm{cash}_{t-1}-q_tP_t^{\mathrm{buy}}-q_tP_t^{\mathrm{buy}}c_b.
```

卖出时，如果卖出股数为 $q_t^{\mathrm{sell}}$ ，卖出成交价为 $P_t^{\mathrm{sell}}$ ，卖出综合成本率为 $c_s$ ，则：

```math
\mathrm{cash}_t=\mathrm{cash}_{t-1}+q_t^{\mathrm{sell}}P_t^{\mathrm{sell}}-q_t^{\mathrm{sell}}P_t^{\mathrm{sell}}c_s.
```

每日收盘后的组合市值为：

```math
V_t=\mathrm{cash}_t+\mathrm{shares}_t C_t.
```

买入并持有基准为：

```math
B_t=X\cdot\frac{C_t}{C_0}.
```

最终比较的两个核心量是：

```math
R^{\mathrm{strategy}}=\frac{V_T}{X}-1,
```

```math
R^{\mathrm{stock}}=\frac{C_T}{C_0}-1.
```

如果 $R^{\mathrm{strategy}}>R^{\mathrm{stock}}$ ，说明这个参数组合在这段样本里跑赢了直接买入并持有；反之则跑输。注意，这仍然不能证明未来有效。

代码中对应函数是：

```python
run_cash_backtest(...)
summarize(...)
```

## 典型案例

当前本地已有 `600000.SH` 从 `20200102` 到 `20260731` 的日线 Parquet 数据。用户输入 `20200101` 时，交易日历会把开始日自动校准到 `20200102`。

### 案例 1：20 日 / 60 日 SMA，默认本金和默认成本

```bash
python Lessons-1/dual_moving_average.py \
  --ts-code SH.600000 \
  --start 20200101 \
  --end 20260731 \
  --fast-window 20 \
  --slow-window 60 \
  --ma-type sma \
  --initial-capital 100000
```

默认设置含义：

- 初始本金 `100000`；
- 起始空仓；
- 金叉买入，死叉卖出；
- 每次买入使用全部可用现金；
- 每次卖出全部持仓；
- 买入成本 `5 bps`，卖出成本 `5 bps`；
- 不额外设置印花税和滑点；
- 今天收盘后的信号，下一交易日开盘执行。

### 案例 2：12 日 / 26 日 EMA

```bash
python Lessons-1/dual_moving_average.py \
  --ts-code 600000.SH \
  --start 20200101 \
  --end 20260731 \
  --fast-window 12 \
  --slow-window 26 \
  --ma-type ema \
  --initial-capital 100000
```

这组参数更敏感，通常会更早买入、更早卖出，也可能产生更多交易。它适合观察“响应速度”和“噪声交易”的权衡。

### 案例 3：固定每次只投入一半现金

```bash
python Lessons-1/dual_moving_average.py \
  --ts-code 600000 \
  --start 20200101 \
  --end 20260731 \
  --fast-window 20 \
  --slow-window 60 \
  --ma-type sma \
  --initial-capital 100000 \
  --buy-fraction 0.5
```

这会降低仓位暴露。收益可能下降，回撤也可能下降。对于初学阶段，这个实验能帮助你理解“择时信号”和“仓位管理”是两件不同的事。

### 案例 4：加入滑点和卖出端额外成本

```bash
python Lessons-1/dual_moving_average.py \
  --ts-code SH.600000 \
  --start 20200101 \
  --end 20260731 \
  --fast-window 20 \
  --slow-window 60 \
  --ma-type sma \
  --buy-cost-bps 5 \
  --sell-cost-bps 5 \
  --stamp-tax-bps 5 \
  --slippage-bps 5
```

交易成本越高，频繁交易的参数组合越容易失效。双均线这类趋势策略尤其要关注成本，因为它在震荡市会反复买卖。

### 案例 5：只看结果，不保存派生数据

```bash
python Lessons-1/dual_moving_average.py \
  --ts-code 600000 \
  --start 20200101 \
  --end 20260731 \
  --fast-window 20 \
  --slow-window 60 \
  --ma-type sma \
  --no-save
```

默认输出文件位于：

```text
data/derived/dual_ma/
```

`data/` 已被 `.gitignore` 忽略，不会同步到 GitHub。

### 案例 6：生成两张回测图

```bash
python Lessons-1/dual_moving_average.py \
  --ts-code SH.600000 \
  --start 20200101 \
  --end 20260731 \
  --fast-window 20 \
  --slow-window 60 \
  --ma-type sma \
  --initial-capital 100000 \
  --plot
```

这会生成两张图：

| 图片 | 含义 |
| --- | --- |
| `*_signals.png` | 股票价格、快均线、慢均线、真实买入日期和卖出日期 |
| `*_strategy_vs_stock.png` | 策略本金曲线、买入持有基准曲线、股票价格走势 |

默认图片保存到：

```text
Lessons-1/
```

默认图片尺寸为 `28 x 7` 英寸，并使用 `600 dpi` 输出 PNG。高度保持可读，宽度加长以便观察多年日线细节。

如果只想看图、不保存 Parquet 派生数据，可以同时使用：

```bash
python Lessons-1/dual_moving_average.py \
  --ts-code SH.600000 \
  --start 20200101 \
  --end 20260731 \
  --fast-window 20 \
  --slow-window 60 \
  --ma-type sma \
  --initial-capital 100000 \
  --plot \
  --no-save
```

本课使用 `600000.SH`、`20200101` 到 `20260731`、`20/60` 日 SMA 生成的示例图如下。

![双均线买卖点图](600000_SH_20200101_20260731_sma_fast20_slow60_entry-crossover_exit-crossover_signals.png)

![策略本金与股票走势对比图](600000_SH_20200101_20260731_sma_fast20_slow60_entry-crossover_exit-crossover_strategy_vs_stock.png)

## 代码参数

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--ts-code` | `600000.SH` | 股票代码，支持 `600000.SH`、`SH.600000`、`600000` |
| `--start` | `20200101` | 开始日期 |
| `--end` | `20260731` | 结束日期 |
| `--refresh` | 关闭 | 强制刷新原始行情数据 |
| `--fast-window` | `20` | 快均线窗口 |
| `--slow-window` | `60` | 慢均线窗口 |
| `--ma-type` | `sma` | 均线类型，可选 `sma` 或 `ema` |
| `--price-col` | `close` | 用哪个价格列计算均线 |
| `--min-periods` | 窗口长度 | 均线最少观测数 |
| `--entry-rule` | `crossover` | 买入规则，可选 `crossover` 或 `trend` |
| `--exit-rule` | `crossover` | 卖出规则，可选 `crossover` 或 `trend` |
| `--initial-capital` | `100000` | 初始本金 |
| `--buy-fraction` | `1.0` | 每次买入使用当前现金的比例 |
| `--buy-cash` | 空 | 每次买入固定金额；设置后覆盖 `--buy-fraction` |
| `--sell-fraction` | `1.0` | 每次卖出当前持仓的比例 |
| `--lot-size` | `100` | 买入取整单位 |
| `--buy-cost-bps` | `5` | 买入成本，单位为基点 |
| `--sell-cost-bps` | `5` | 卖出成本，单位为基点 |
| `--stamp-tax-bps` | `0` | 卖出端额外成本，单位为基点 |
| `--slippage-bps` | `0` | 不利滑点，单位为基点 |
| `--execution-lag` | `1` | 信号延后几根 K 线执行 |
| `--execution-price-col` | `open` | 成交价格列，可选 `open` 或 `close` |
| `--output` | 自动生成 | 派生 Parquet 输出路径 |
| `--no-save` | 关闭 | 只打印结果，不保存派生数据 |
| `--plot` | 关闭 | 生成双均线买卖点图和策略对比图 |
| `--plot-dir` | `Lessons-1/` | 图片输出目录 |
| `--plot-format` | `png` | 图片格式，可选 `png`、`pdf`、`svg` |
| `--plot-dpi` | `600` | 图片分辨率 |
| `--plot-width` | `28` | 图片宽度，单位为英寸 |
| `--plot-height` | `7` | 图片高度，单位为英寸 |
| `--no-plot-annotations` | 关闭 | 不在买卖点旁边标注日期 |

## 绘图接口

绘图代码放在公共目录 `DrawingToolkit/`，Lesson 1 只是调用它。以后其他课程如果要画类似图，不应该复制 Matplotlib 代码，而应该复用或扩展这里的函数。

当前有两个公共函数：

```python
from DrawingToolkit import plot_dual_moving_average, plot_strategy_vs_stock
```

`plot_dual_moving_average` 用于画价格、快慢均线和买卖日期：

```python
plot_dual_moving_average(
    result,
    output_path="Lessons-1/dual_ma_signals.png",
    figsize=(28, 7),
    dpi=600,
)
```

`plot_strategy_vs_stock` 用于画策略本金曲线、买入持有基准曲线和股票价格走势：

```python
plot_strategy_vs_stock(
    result,
    output_path="Lessons-1/strategy_vs_stock.png",
    figsize=(28, 7),
    dpi=600,
)
```

这两个函数默认使用 Lesson 1 的输出列名。如果后续策略的列名不同，可以通过参数覆盖，例如 `date_col`、`price_col`、`portfolio_col`、`benchmark_col`。

## 输出列如何理解

| 列名 | 含义 |
| --- | --- |
| `fast_ma` | 快均线 |
| `slow_ma` | 慢均线 |
| `ma_spread` | 快线减慢线 |
| `trend_signal_t` | 当天收盘后根据双均线得到的趋势状态 |
| `buy_signal` | 金叉事件 |
| `sell_signal` | 死叉事件 |
| `action_for_next_day` | 当天收盘后给下一交易日的参考动作 |
| `signal_date` | 今天成交参考的是哪一天的信号 |
| `raw_action` | 策略规则今天想执行的动作 |
| `executed_action` | 账户约束后今天真实执行的动作 |
| `execution_price` | 今天使用的成交价格列 |
| `buy_quantity` | 今天买入股数 |
| `sell_quantity` | 今天卖出股数 |
| `trade_amount` | 今天成交金额 |
| `trade_cost` | 今天交易成本 |
| `cash` | 今天收盘后的现金 |
| `shares` | 今天收盘后的持股数量 |
| `stock_market_value` | 今天收盘后的股票市值 |
| `portfolio_value` | 今天收盘后的总资产 |
| `benchmark_value` | 同期买入并持有的资产曲线 |
| `strategy_total_return` | 策略从起点到今天的累计收益率 |
| `stock_total_return` | 股票自身从起点到今天的累计涨跌幅 |
| `excess_total_return` | 策略累计收益率减股票累计涨跌幅 |

## 如何评价结果

脚本会打印以下指标：

| 指标 | 含义 |
| --- | --- |
| `initial_capital` | 初始本金 |
| `final_portfolio_value` | 期末组合市值 |
| `final_cash` | 期末现金 |
| `final_shares` | 期末持股 |
| `strategy_total_return` | 策略累计收益 |
| `stock_total_return` | 股票买入并持有累计收益 |
| `excess_total_return` | 策略相对股票自身涨跌幅的超额收益 |
| `strategy_annual_return` | 策略年化收益 |
| `stock_annual_return` | 股票年化收益 |
| `strategy_annual_vol` | 策略年化波动率 |
| `stock_annual_vol` | 股票年化波动率 |
| `strategy_sharpe` | 策略简化夏普比率，未扣无风险利率 |
| `strategy_max_drawdown` | 策略最大回撤 |
| `stock_max_drawdown` | 买入持有最大回撤 |
| `trade_count` | 实际成交次数 |
| `buy_count` | 买入次数 |
| `sell_count` | 卖出次数 |
| `total_trade_amount` | 全部成交金额 |
| `total_trade_cost` | 全部交易成本 |

这些指标只能说明这个参数组合在这个样本中的表现，不能证明未来有效。双均线尤其容易出现参数挖掘：你试得越多，越容易找到一个历史上看起来漂亮、未来却失效的窗口组合。

## 常见错误

**错误 1：当天信号当天成交。**

如果使用当天收盘价生成均线，又用当天开盘价或当天收益验证策略，就使用了未来信息。代码默认 `--execution-lag 1`，避免今天信号影响今天成交。

**错误 2：只看收益率曲线，不看账户约束。**

账户里现金不够、买不到整手、成本扣完后股数变化，都会改变结果。入门时就把现金和股数记清楚，会减少很多错误。

**错误 3：只看最后收益，不看交易次数。**

快窗口太短会频繁交易。即使毛收益不错，交易成本和滑点也可能吃掉收益。

**错误 4：把单股票结果推广到全市场。**

一只银行股的趋势特征不能代表成长股、周期股、小盘股。后续要做横截面实验和行业分组。

**错误 5：把双均线当成因果模型。**

均线只是历史价格变换，不是基本面、订单流或宏观变量。它可以描述趋势，但不能解释趋势为什么出现。

## 练习

1. 用 `600000.SH` 比较 `5/20`、`10/30`、`20/60`、`60/120` 四组 SMA，记录收益、回撤、交易次数。
2. 固定 `20/60`，比较 SMA 和 EMA。观察 EMA 是否更早买入、更早卖出，以及交易次数是否增加。
3. 把 `--buy-cost-bps` 和 `--sell-cost-bps` 都从 `0`、`5`、`10`、`20` 逐步提高，观察策略什么时候被成本吃掉。
4. 固定 `20/60`，分别设置 `--buy-fraction 1.0`、`0.5`、`0.2`，观察收益和回撤如何变化。
5. 把样本切成 `2020-2022` 和 `2023-2026` 两段，比较同一参数是否稳定。
6. 找一只创业板股票和一只周期股重复实验，比较趋势信号是否有明显差异。
7. 把 `--entry-rule trend --exit-rule trend` 与默认金叉/死叉规则对比，观察从样本中途开始时入场时间是否不同。

完成练习后，写一页实验记录：哪个参数表现最好，哪个参数最不稳定，结果是否可能只是偶然。

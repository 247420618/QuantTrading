"""Lesson 1：双均线策略的账户级回测示例。

这个脚本把“双均线趋势规则”拆成三个独立步骤，方便初学者逐层 review：

1. 计算指标：根据日线价格计算快慢两条均线；
2. 生成策略：根据金叉/死叉或趋势状态决定买入、卖出、持有；
3. 账户回测：从给定本金和空仓状态开始，逐日记录现金、股数、成本和组合市值。

默认设定贴近 A 股日线学习场景：今天收盘后得到信号，下一交易日开盘成交，
即默认 `--execution-lag 1`。这不是为了追求真实交易系统的所有细节，而是为了
先把“信号不能使用未来数据”和“策略必须落到账户资产变化”两件事讲清楚。

运行示例：

    python Lessons-1/dual_moving_average.py \
      --ts-code SH.600000 \
      --start 20200101 \
      --end 20260731 \
      --fast-window 20 \
      --slow-window 60 \
      --ma-type sma \
      --initial-capital 100000

脚本通过 `Tools.quant_data.DataPortal` 读取数据。若本地 Parquet 已覆盖窗口，
不会访问远端；若本地缺失，则按 DataPortal 的缓存策略补齐。
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


# 允许直接用 `python Lessons-1/dual_moving_average.py` 从仓库根目录运行。
# 如果不补充 `sys.path`，脚本直接执行时可能找不到顶层 `Tools` 包。
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.quant_data import DataPortal  # noqa: E402
from Tools.quant_data.validators import format_date  # noqa: E402
from DrawingToolkit.config import DEFAULT_PLOT_DPI, DEFAULT_PLOT_FIGSIZE  # noqa: E402


# 兼容三类常见股票代码写法：
# 1. Tushare 标准格式：600000.SH
# 2. 用户常见前缀格式：SH.600000
# 3. 纯六位代码：600000
TS_CODE_TUSHARE_PATTERN = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.IGNORECASE)
TS_CODE_PREFIX_PATTERN = re.compile(r"^(SH|SZ|BJ)[\._-]?(\d{6})$", re.IGNORECASE)
TS_CODE_PLAIN_PATTERN = re.compile(r"^(\d{6})$")


@dataclass(frozen=True)
class BacktestConfig:
    """账户回测参数。

    字段设计尽量贴近真实交易时会关心的变量：

    - `initial_capital`：初始本金；
    - `buy_fraction` / `buy_cash`：每次买入使用多少现金；
    - `sell_fraction`：每次卖出多少持仓；
    - `lot_size`：A 股普通买入通常按 100 股整数手约束；
    - 成本参数：佣金、印花税、滑点都用基点 bps 表示；
    - `execution_lag`：信号延后几根 K 线执行，日线 T+1 学习默认是 1。
    """

    initial_capital: float = 100000.0
    buy_fraction: float = 1.0
    buy_cash: float | None = None
    sell_fraction: float = 1.0
    lot_size: int = 100
    buy_cost_bps: float = 5.0
    sell_cost_bps: float = 5.0
    stamp_tax_bps: float = 0.0
    slippage_bps: float = 0.0
    execution_lag: int = 1
    execution_price_col: str = "open"

    @property
    def buy_cost_rate(self) -> float:
        """买入端综合成本率，`5 bps` 等于 `0.0005`。"""

        return self.buy_cost_bps / 10000.0

    @property
    def sell_cost_rate(self) -> float:
        """卖出端综合成本率；卖出时额外叠加印花税。"""

        return (self.sell_cost_bps + self.stamp_tax_bps) / 10000.0

    @property
    def slippage_rate(self) -> float:
        """滑点率；买入把成交价抬高，卖出把成交价压低。"""

        return self.slippage_bps / 10000.0


def normalize_ts_code(value: str) -> str:
    """把不同写法的股票代码统一成 Tushare 的 `600000.SH` 格式。

    对纯六位代码做一个入门级推断：`0/3` 开头默认深市，`4/8` 开头默认北交所，
    其他默认沪市。严肃系统中应使用证券基础表做精确映射。
    """

    code = value.strip().upper()

    # 已经是 Tushare 标准格式时，统一大小写后直接返回。
    tushare_match = TS_CODE_TUSHARE_PATTERN.match(code)
    if tushare_match:
        symbol, exchange = tushare_match.groups()
        return f"{symbol}.{exchange}"

    # 把 `SH.600000`、`SH600000`、`SH-600000` 这类写法转成 `600000.SH`。
    prefix_match = TS_CODE_PREFIX_PATTERN.match(code)
    if prefix_match:
        exchange, symbol = prefix_match.groups()
        return f"{symbol}.{exchange}"

    # 纯六位代码没有交易所信息，只能按 A 股常见编码规则做保守推断。
    plain_match = TS_CODE_PLAIN_PATTERN.match(code)
    if plain_match:
        symbol = plain_match.group(1)
        if symbol.startswith(("4", "8")):
            return f"{symbol}.BJ"
        if symbol.startswith(("0", "3")):
            return f"{symbol}.SZ"
        return f"{symbol}.SH"

    raise ValueError("ts-code must look like 600000.SH, SH.600000 or 600000")


def moving_average(series: pd.Series, *, window: int, ma_type: str, min_periods: int | None) -> pd.Series:
    """计算单条移动平均线。

    参数说明：

    - `series`：通常是收盘价，也可以换成开盘价、复权价等价格序列；
    - `window`：均线窗口，例如 20 表示 20 个交易日；
    - `ma_type`：`sma` 是简单移动平均，`ema` 是指数移动平均；
    - `min_periods`：窗口内至少需要多少个样本才输出均线。

    默认 `min_periods=None` 时要求样本数达到完整窗口才输出均线，这样前
    `window-1` 行会是空值，可以避免样本不足阶段产生不稳定信号。
    """

    if window <= 0:
        raise ValueError("window must be positive")

    periods = window if min_periods is None else min_periods
    if periods <= 0:
        raise ValueError("min_periods must be positive")

    if ma_type == "sma":
        # SMA 是固定长度滚动窗口的算术平均，反应更慢但更直观。
        return series.rolling(window=window, min_periods=periods).mean()
    if ma_type == "ema":
        # EMA 给近期价格更高权重，`adjust=False` 使用常见递推形式。
        return series.ewm(span=window, adjust=False, min_periods=periods).mean()
    raise ValueError("ma_type must be 'sma' or 'ema'")


def calculate_dual_moving_average(
    bars: pd.DataFrame,
    *,
    price_col: str,
    fast_window: int,
    slow_window: int,
    ma_type: str,
    min_periods: int | None,
) -> pd.DataFrame:
    """计算快慢均线，并给出最基础的趋势状态。

    这一层只负责“指标计算”和“信号标记”，不处理本金、交易成本和成交价格。
    把它独立出来的好处是：以后你可以直接复用这层特征，接入其他策略或模型。

    输出新增列：

    - `fast_ma` / `slow_ma`：快慢均线；
    - `ma_spread` / `ma_spread_pct`：快慢线差值和百分比差；
    - `trend_signal_t`：当天收盘后看到的趋势状态，1 表示多头，0 表示空仓；
    - `buy_signal` / `sell_signal`：金叉和死叉事件；
    - `action_for_next_day`：按金叉/死叉规则给下一交易日的参考动作。
    """

    if fast_window <= 0 or slow_window <= 0:
        raise ValueError("fast_window and slow_window must be positive")
    if fast_window >= slow_window:
        raise ValueError("fast_window must be smaller than slow_window")
    if "trade_date" not in bars.columns:
        raise ValueError("daily bars must contain trade_date")
    if price_col not in bars.columns:
        raise ValueError(f"price column {price_col!r} not found in data")

    # 按交易日升序排列，确保均线、信号变化和后续收益都沿时间正向计算。
    df = bars.sort_values("trade_date").reset_index(drop=True).copy()

    # 明确把价格列转成数值，避免源数据中混入字符串导致计算结果异常。
    price = pd.to_numeric(df[price_col], errors="coerce")
    if price.isna().any():
        raise ValueError(f"price column {price_col!r} contains missing or non-numeric values")
    df[price_col] = price

    # 为了后续账户回测方便，这里顺手把常用 OHLC 列也转成数值。
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Step 1：计算快线和慢线。快线反映短期价格，慢线反映长期价格基准。
    df["fast_ma"] = moving_average(price, window=fast_window, ma_type=ma_type, min_periods=min_periods)
    df["slow_ma"] = moving_average(price, window=slow_window, ma_type=ma_type, min_periods=min_periods)

    # 均线差是趋势强弱的连续刻画；百分比差方便跨股票、跨价格区间比较。
    df["ma_spread"] = df["fast_ma"] - df["slow_ma"]
    df["ma_spread_pct"] = df["ma_spread"] / df["slow_ma"].where(df["slow_ma"] != 0)

    # Step 2 的原始材料：当天收盘后能观察到的趋势状态。
    # 均线样本不足时不交易；快线高于慢线时才进入多头状态。
    valid_ma = df["fast_ma"].notna() & df["slow_ma"].notna()
    df["trend_signal_t"] = 0
    df.loc[valid_ma & (df["fast_ma"] > df["slow_ma"]), "trend_signal_t"] = 1

    # 金叉：状态从 0 变成 1；死叉：状态从 1 变成 0。
    previous_signal = df["trend_signal_t"].shift(1).fillna(0)
    df["buy_signal"] = df["trend_signal_t"].eq(1) & previous_signal.eq(0)
    df["sell_signal"] = df["trend_signal_t"].eq(0) & previous_signal.eq(1)

    # 这是“信号层”的参考动作，表示今天收盘后产生、下一交易日可以执行。
    df["action_for_next_day"] = "hold"
    df.loc[df["buy_signal"], "action_for_next_day"] = "buy"
    df.loc[df["sell_signal"], "action_for_next_day"] = "sell"

    # 这些列只用于事后分析，不参与当日成交决策。
    df["price_return_1d"] = price.pct_change().fillna(0)
    df["next_price_return_1d"] = price.shift(-1) / price - 1
    df["realized_next_up"] = df["next_price_return_1d"] > 0

    return df


def decide_trade_action(
    signal_row: pd.Series,
    *,
    shares: int,
    entry_rule: str,
    exit_rule: str,
) -> str:
    """根据上一根 K 线的信号和当前持仓，决定今天执行什么动作。

    支持两类常见规则：

    - `crossover`：只在金叉买入、死叉卖出；
    - `trend`：只要快线高于慢线且当前空仓就买入，只要快线不高于慢线且当前有仓就卖出。

    默认使用 `crossover`，因为它最符合“金叉买、死叉卖”的主流双均线讲法。
    `trend` 更适合从样本中途开始回测时使用：如果一开始已经处于多头趋势，
    它不会非要等下一次金叉才入场。
    """

    if shares > 0:
        if exit_rule == "crossover" and bool(signal_row["sell_signal"]):
            return "sell"
        if exit_rule == "trend" and int(signal_row["trend_signal_t"]) == 0:
            return "sell"
        return "hold"

    if entry_rule == "crossover" and bool(signal_row["buy_signal"]):
        return "buy"
    if entry_rule == "trend" and int(signal_row["trend_signal_t"]) == 1:
        return "buy"
    return "hold"


def calc_buy_quantity(*, cash: float, target_cash: float, price: float, cost_rate: float, lot_size: int) -> int:
    """计算本次可以买入多少股。

    买入数量需要同时满足三件事：

    1. 不超过当前现金；
    2. 买入金额加交易成本不超过本次计划投入；
    3. 按 `lot_size` 取整，默认 100 股一手。
    """

    if cash <= 0 or target_cash <= 0 or price <= 0:
        return 0

    usable_cash = min(cash, target_cash)
    raw_quantity = usable_cash / (price * (1 + cost_rate))
    if lot_size <= 1:
        return int(math.floor(raw_quantity))
    return int(math.floor(raw_quantity / lot_size) * lot_size)


def calc_sell_quantity(*, shares: int, sell_fraction: float, lot_size: int) -> int:
    """计算本次卖出多少股。

    教学代码默认 `sell_fraction=1`，即死叉时全部卖出。若设置成 0.5，则每次
    尽量卖出一半可用仓位。清仓时允许卖出全部剩余股数，避免因为不是整手而残留尾仓。
    """

    if shares <= 0 or sell_fraction <= 0:
        return 0
    if sell_fraction >= 1:
        return shares

    raw_quantity = shares * sell_fraction
    if lot_size <= 1:
        return int(math.floor(raw_quantity))

    rounded_quantity = int(math.floor(raw_quantity / lot_size) * lot_size)
    if rounded_quantity > 0:
        return min(rounded_quantity, shares)

    # 如果比例卖出被整手规则压成 0，就至少卖一手；若剩余不足一手，则直接清掉。
    return min(lot_size, shares)


def run_cash_backtest(
    signal_df: pd.DataFrame,
    *,
    config: BacktestConfig,
    entry_rule: str,
    exit_rule: str,
) -> pd.DataFrame:
    """从现金和空仓开始，执行双均线策略并记录账户曲线。

    这是本课最重要的函数。它和很多博客里的“收益率乘以信号”不同，
    这里显式维护现金、持股数量、交易金额和成本，因此更容易发现：

    - 钱不够时买不到整手；
    - 交易成本会影响可买数量和最终收益；
    - 起始为空仓时，策略必须先等到买入信号；
    - T+1 日线回测中，今天信号默认下一交易日才执行。
    """

    if signal_df.empty:
        raise ValueError("signal_df is empty")
    if config.initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if not 0 < config.buy_fraction <= 1:
        raise ValueError("buy_fraction must be in (0, 1]")
    if config.buy_cash is not None and config.buy_cash <= 0:
        raise ValueError("buy_cash must be positive when provided")
    if not 0 < config.sell_fraction <= 1:
        raise ValueError("sell_fraction must be in (0, 1]")
    if config.lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if config.execution_lag < 0:
        raise ValueError("execution_lag must be non-negative")
    if config.execution_price_col not in signal_df.columns:
        raise ValueError(f"execution price column {config.execution_price_col!r} not found in data")
    if "close" not in signal_df.columns:
        raise ValueError("daily bars must contain close for portfolio valuation")

    df = signal_df.sort_values("trade_date").reset_index(drop=True).copy()
    close = pd.to_numeric(df["close"], errors="coerce")
    execution_price = pd.to_numeric(df[config.execution_price_col], errors="coerce")
    if close.isna().any() or execution_price.isna().any():
        raise ValueError("close or execution price contains missing/non-numeric values")

    cash = float(config.initial_capital)
    shares = 0
    first_close = float(close.iloc[0])
    records: list[dict[str, object]] = []

    for i, row in df.iterrows():
        action = "hold"
        signal_date = None

        # 默认 execution_lag=1：第 i-1 行收盘后看到的信号，在第 i 行执行。
        signal_index = i - config.execution_lag
        if signal_index >= 0:
            signal_row = df.iloc[signal_index]
            signal_date = signal_row["trade_date"]
            action = decide_trade_action(
                signal_row,
                shares=shares,
                entry_rule=entry_rule,
                exit_rule=exit_rule,
            )

        raw_execution_price = float(execution_price.iloc[i])
        close_price = float(close.iloc[i])
        executed_action = "hold"
        buy_quantity = 0
        sell_quantity = 0
        trade_amount = 0.0
        trade_cost = 0.0

        if action == "buy" and shares == 0:
            # 买入滑点：假设真实成交价比观测到的开盘价更贵一点。
            fill_price = raw_execution_price * (1 + config.slippage_rate)
            target_cash = config.buy_cash if config.buy_cash is not None else cash * config.buy_fraction
            buy_quantity = calc_buy_quantity(
                cash=cash,
                target_cash=target_cash,
                price=fill_price,
                cost_rate=config.buy_cost_rate,
                lot_size=config.lot_size,
            )
            if buy_quantity > 0:
                trade_amount = buy_quantity * fill_price
                trade_cost = trade_amount * config.buy_cost_rate
                cash -= trade_amount + trade_cost
                shares += buy_quantity
                executed_action = "buy"

        elif action == "sell" and shares > 0:
            # 卖出滑点：假设真实成交价比观测到的开盘价更便宜一点。
            fill_price = raw_execution_price * (1 - config.slippage_rate)
            sell_quantity = calc_sell_quantity(
                shares=shares,
                sell_fraction=config.sell_fraction,
                lot_size=config.lot_size,
            )
            if sell_quantity > 0:
                trade_amount = sell_quantity * fill_price
                trade_cost = trade_amount * config.sell_cost_rate
                cash += trade_amount - trade_cost
                shares -= sell_quantity
                executed_action = "sell"

        # 每日收盘后按收盘价给股票市值估值。成交价可以是开盘价，但估值价用收盘价。
        stock_market_value = shares * close_price
        portfolio_value = cash + stock_market_value
        benchmark_value = config.initial_capital * (close_price / first_close)

        records.append(
            {
                "trade_date": row["trade_date"],
                "signal_date": signal_date,
                "raw_action": action,
                "executed_action": executed_action,
                "execution_price": raw_execution_price,
                "buy_quantity": buy_quantity,
                "sell_quantity": sell_quantity,
                "trade_amount": trade_amount,
                "trade_cost": trade_cost,
                "cash": cash,
                "shares": shares,
                "stock_market_value": stock_market_value,
                "portfolio_value": portfolio_value,
                "benchmark_value": benchmark_value,
                "strategy_total_return": portfolio_value / config.initial_capital - 1,
                "stock_total_return": close_price / first_close - 1,
            }
        )

    account = pd.DataFrame.from_records(records)
    result = pd.concat([df.reset_index(drop=True), account.drop(columns=["trade_date"])], axis=1)

    # 每日收益率来自组合市值变化，不再用“信号乘收益率”近似。
    result["strategy_return_1d"] = result["portfolio_value"].pct_change().fillna(0)
    result["stock_return_1d"] = result["benchmark_value"].pct_change().fillna(0)
    result["excess_total_return"] = result["strategy_total_return"] - result["stock_total_return"]
    result["in_position"] = result["shares"].gt(0).astype(int)
    result["turnover"] = result["trade_amount"] / result["portfolio_value"].shift(1).fillna(config.initial_capital)

    return result


def max_drawdown(values: pd.Series) -> float:
    """计算最大回撤。"""

    curve = values.astype(float)
    drawdown = curve / curve.cummax() - 1
    return float(drawdown.min())


def summarize(result: pd.DataFrame, *, initial_capital: float) -> dict[str, float]:
    """计算一组入门级绩效指标。

    这些指标适合教学和快速 sanity check。真实研究还应补充分年表现、
    样本外测试、手续费细节、滑点、停牌、涨跌停成交约束等检查。
    """

    if result.empty:
        return {}

    returns = result["strategy_return_1d"].fillna(0)
    stock_returns = result["stock_return_1d"].fillna(0)
    final_value = float(result["portfolio_value"].iloc[-1])
    final_benchmark_value = float(result["benchmark_value"].iloc[-1])
    total_return = final_value / initial_capital - 1
    stock_total_return = final_benchmark_value / initial_capital - 1

    # A 股通常按约 252 个交易日年化。这里用样本行数近似交易日数。
    periods = max(len(result), 1)
    annual_return = (1 + total_return) ** (252 / periods) - 1 if total_return > -1 else float("nan")
    stock_annual_return = (1 + stock_total_return) ** (252 / periods) - 1 if stock_total_return > -1 else float("nan")
    annual_vol = float(returns.std(ddof=0) * math.sqrt(252))
    stock_annual_vol = float(stock_returns.std(ddof=0) * math.sqrt(252))

    # 简化夏普：未扣无风险利率。波动率为 0 时夏普没有定义。
    sharpe = float(returns.mean() / returns.std(ddof=0) * math.sqrt(252)) if returns.std(ddof=0) > 0 else float("nan")

    trade_rows = result[result["executed_action"].isin(["buy", "sell"])]

    return {
        "rows": float(len(result)),
        "initial_capital": float(initial_capital),
        "final_portfolio_value": final_value,
        "final_cash": float(result["cash"].iloc[-1]),
        "final_shares": float(result["shares"].iloc[-1]),
        "strategy_total_return": float(total_return),
        "stock_total_return": float(stock_total_return),
        "excess_total_return": float(total_return - stock_total_return),
        "strategy_annual_return": float(annual_return),
        "stock_annual_return": float(stock_annual_return),
        "strategy_annual_vol": annual_vol,
        "stock_annual_vol": stock_annual_vol,
        "strategy_sharpe": sharpe,
        "strategy_max_drawdown": max_drawdown(result["portfolio_value"]),
        "stock_max_drawdown": max_drawdown(result["benchmark_value"]),
        "trade_count": float(len(trade_rows)),
        "buy_count": float((trade_rows["executed_action"] == "buy").sum()),
        "sell_count": float((trade_rows["executed_action"] == "sell").sum()),
        "total_trade_amount": float(result["trade_amount"].sum()),
        "total_trade_cost": float(result["trade_cost"].sum()),
    }


def experiment_slug(
    *,
    ts_code: str,
    start: str,
    end: str,
    ma_type: str,
    fast_window: int,
    slow_window: int,
    entry_rule: str,
    exit_rule: str,
) -> str:
    """生成实验结果文件名主体。

    同一组回测通常会产生 Parquet、双均线图、资金曲线图等多个文件。
    统一 slug 可以避免这些文件命名不一致，后续批量实验时也更容易管理。
    """

    safe_ts_code = ts_code.replace(".", "_")
    return (
        f"{safe_ts_code}_{start}_{end}_{ma_type}_fast{fast_window}_slow{slow_window}"
        f"_entry-{entry_rule}_exit-{exit_rule}"
    )


def default_output_path(
    *,
    ts_code: str,
    start: str,
    end: str,
    ma_type: str,
    fast_window: int,
    slow_window: int,
    entry_rule: str,
    exit_rule: str,
) -> Path:
    """生成派生回测结果默认保存路径。

    输出放在 `data/derived/dual_ma/`，属于派生实验数据。根目录 `.gitignore`
    已经忽略 `data/`，所以不会把本地实验数据同步到远端仓库。
    """

    name = experiment_slug(
        ts_code=ts_code,
        start=start,
        end=end,
        ma_type=ma_type,
        fast_window=fast_window,
        slow_window=slow_window,
        entry_rule=entry_rule,
        exit_rule=exit_rule,
    )
    return Path("data") / "derived" / "dual_ma" / f"{name}.parquet"


def default_plot_paths(
    *,
    ts_code: str,
    start: str,
    end: str,
    ma_type: str,
    fast_window: int,
    slow_window: int,
    entry_rule: str,
    exit_rule: str,
    plot_dir: str | Path | None,
    plot_format: str,
) -> tuple[Path, Path]:
    """生成双均线图和策略对比图的默认保存路径。"""

    stem = experiment_slug(
        ts_code=ts_code,
        start=start,
        end=end,
        ma_type=ma_type,
        fast_window=fast_window,
        slow_window=slow_window,
        entry_rule=entry_rule,
        exit_rule=exit_rule,
    )
    base_dir = Path(plot_dir) if plot_dir else Path(__file__).resolve().parent
    return (
        base_dir / f"{stem}_signals.{plot_format}",
        base_dir / f"{stem}_strategy_vs_stock.{plot_format}",
    )


def build_parser() -> argparse.ArgumentParser:
    """定义命令行参数。

    参数分为四类：

    1. 数据范围：股票代码、开始结束日期、是否刷新；
    2. 均线指标：快慢窗口、SMA/EMA、价格列；
    3. 策略规则：金叉/趋势入场，死叉/趋势离场；
    4. 账户回测：本金、买卖额度、交易成本、滑点和成交价列。
    """

    parser = argparse.ArgumentParser(description="Backtest a dual moving average strategy on A-share daily bars.")
    parser.add_argument("--ts-code", default="600000.SH", help="Tushare code, e.g. 600000.SH, SH.600000 or 600000")
    parser.add_argument("--start", default="20200101", help="Start date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", default="20260731", help="End date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--refresh", action="store_true", help="Force DataPortal to refresh raw daily data")

    parser.add_argument("--fast-window", type=int, default=20, help="Fast moving average window")
    parser.add_argument("--slow-window", type=int, default=60, help="Slow moving average window")
    parser.add_argument("--ma-type", choices=["sma", "ema"], default="ema", help="Moving average type")
    parser.add_argument("--price-col", default="close", help="Price column used to calculate moving averages")
    parser.add_argument("--min-periods", type=int, default=None, help="Minimum observations for MA; default equals window")

    parser.add_argument(
        "--entry-rule",
        choices=["crossover", "trend"],
        default="crossover",
        help="Buy rule: crossover buys only on golden cross; trend buys whenever fast_ma > slow_ma and account is empty",
    )
    parser.add_argument(
        "--exit-rule",
        choices=["crossover", "trend"],
        default="crossover",
        help="Sell rule: crossover sells only on death cross; trend sells whenever fast_ma <= slow_ma while holding",
    )

    parser.add_argument("--initial-capital", type=float, default=100000.0, help="Initial cash capital")
    parser.add_argument("--buy-fraction", type=float, default=1.0, help="Fraction of available cash used on each buy")
    parser.add_argument("--buy-cash", type=float, default=None, help="Fixed cash budget per buy; overrides buy-fraction")
    parser.add_argument("--sell-fraction", type=float, default=1.0, help="Fraction of shares sold on each sell")
    parser.add_argument("--lot-size", type=int, default=100, help="Round lot size; A-share educational default is 100")
    parser.add_argument("--buy-cost-bps", type=float, default=5.0, help="Buy-side commission/cost in basis points")
    parser.add_argument("--sell-cost-bps", type=float, default=5.0, help="Sell-side commission/cost in basis points")
    parser.add_argument("--stamp-tax-bps", type=float, default=0.0, help="Sell-side stamp tax in basis points")
    parser.add_argument("--slippage-bps", type=float, default=0.0, help="Adverse slippage in basis points")
    parser.add_argument(
        "--execution-lag",
        type=int,
        default=1,
        help="Bars between signal observation and execution; 1 is the default T+1 daily setting",
    )
    parser.add_argument(
        "--execution-price-col",
        choices=["open", "close"],
        default="open",
        help="Price column used for execution; default is next trading day's open",
    )

    parser.add_argument("--output", default=None, help="Output parquet path; default is data/derived/dual_ma/")
    parser.add_argument("--no-save", action="store_true", help="Do not save derived backtest data")
    parser.add_argument("--plot", action="store_true", help="Save dual-MA and strategy-vs-stock plots")
    parser.add_argument("--plot-dir", default=None, help="Plot output directory; default is Lessons-1/")
    parser.add_argument("--plot-format", choices=["png", "pdf", "svg"], default="png", help="Plot file format")
    parser.add_argument("--plot-dpi", type=int, default=DEFAULT_PLOT_DPI, help="Plot resolution for raster formats")
    parser.add_argument("--plot-width", type=float, default=DEFAULT_PLOT_FIGSIZE[0], help="Plot width in inches")
    parser.add_argument("--plot-height", type=float, default=DEFAULT_PLOT_FIGSIZE[1], help="Plot height in inches")
    parser.add_argument("--no-plot-annotations", action="store_true", help="Do not annotate buy/sell dates on signal plot")
    return parser


def print_summary(summary: dict[str, float]) -> None:
    """把核心指标打印成适合命令行查看的格式。"""

    integer_keys = {"rows", "final_shares", "trade_count", "buy_count", "sell_count"}
    money_keys = {"initial_capital", "final_portfolio_value", "final_cash", "total_trade_amount", "total_trade_cost"}
    percent_keys = {
        "strategy_total_return",
        "stock_total_return",
        "excess_total_return",
        "strategy_annual_return",
        "stock_annual_return",
        "strategy_annual_vol",
        "stock_annual_vol",
        "strategy_max_drawdown",
        "stock_max_drawdown",
    }

    for key in [
        "rows",
        "initial_capital",
        "final_portfolio_value",
        "final_cash",
        "final_shares",
        "strategy_total_return",
        "stock_total_return",
        "excess_total_return",
        "strategy_annual_return",
        "stock_annual_return",
        "strategy_annual_vol",
        "stock_annual_vol",
        "strategy_sharpe",
        "strategy_max_drawdown",
        "stock_max_drawdown",
        "trade_count",
        "buy_count",
        "sell_count",
        "total_trade_amount",
        "total_trade_cost",
    ]:
        value = summary.get(key)
        if value is None:
            continue
        if key in integer_keys:
            print(f"{key}={int(value)}")
        elif key in money_keys:
            print(f"{key}={value:.2f}")
        elif key in percent_keys:
            print(f"{key}={value:.4%}")
        else:
            print(f"{key}={value:.4f}")


def main() -> None:
    """脚本入口：解析参数、读取行情、计算指标、回测账户并打印摘要。"""

    args = build_parser().parse_args()

    # 把用户输入统一成后续工具层可识别的标准格式。
    ts_code = normalize_ts_code(args.ts_code)
    start = format_date(args.start)
    end = format_date(args.end)

    # DataPortal 会优先读取本地 Parquet；若本地缺失，再按缓存策略补齐远端数据。
    portal = DataPortal()
    bars = portal.daily_bars(ts_code, start, end, refresh=args.refresh)

    # Step 1：计算双均线指标和当天收盘后可观察到的趋势信号。
    signal_df = calculate_dual_moving_average(
        bars,
        price_col=args.price_col,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        ma_type=args.ma_type,
        min_periods=args.min_periods,
    )

    # Step 2 + Step 3：把策略规则落到账户回测。初始状态是全现金、空仓。
    config = BacktestConfig(
        initial_capital=args.initial_capital,
        buy_fraction=args.buy_fraction,
        buy_cash=args.buy_cash,
        sell_fraction=args.sell_fraction,
        lot_size=args.lot_size,
        buy_cost_bps=args.buy_cost_bps,
        sell_cost_bps=args.sell_cost_bps,
        stamp_tax_bps=args.stamp_tax_bps,
        slippage_bps=args.slippage_bps,
        execution_lag=args.execution_lag,
        execution_price_col=args.execution_price_col,
    )
    result = run_cash_backtest(
        signal_df,
        config=config,
        entry_rule=args.entry_rule,
        exit_rule=args.exit_rule,
    )

    # 默认输出文件名包含股票、区间、均线类型、窗口和策略规则，方便保留多组实验结果。
    output = Path(args.output) if args.output else default_output_path(
        ts_code=ts_code,
        start=start,
        end=end,
        ma_type=args.ma_type,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        entry_rule=args.entry_rule,
        exit_rule=args.exit_rule,
    )
    if not args.no_save:
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(output, index=False)
        print(f"saved={output}")

    if args.plot:
        # 绘图接口放在公共 DrawingToolkit 中，后续 Lesson 复用这里的函数。
        from DrawingToolkit import plot_dual_moving_average, plot_strategy_vs_stock

        if args.plot_width <= 0 or args.plot_height <= 0:
            raise ValueError("--plot-width and --plot-height must be positive")

        signal_plot_path, comparison_plot_path = default_plot_paths(
            ts_code=ts_code,
            start=start,
            end=end,
            ma_type=args.ma_type,
            fast_window=args.fast_window,
            slow_window=args.slow_window,
            entry_rule=args.entry_rule,
            exit_rule=args.exit_rule,
            plot_dir=args.plot_dir,
            plot_format=args.plot_format,
        )
        signal_plot = plot_dual_moving_average(
            result,
            output_path=signal_plot_path,
            title=f"{ts_code} dual moving average",
            dpi=args.plot_dpi,
            figsize=(args.plot_width, args.plot_height),
            annotate_trades=not args.no_plot_annotations,
        )
        comparison_plot = plot_strategy_vs_stock(
            result,
            output_path=comparison_plot_path,
            title=f"{ts_code} strategy capital vs stock",
            initial_capital=args.initial_capital,
            dpi=args.plot_dpi,
            figsize=(args.plot_width, args.plot_height),
        )
        print(f"plot_dual_ma={signal_plot}")
        print(f"plot_strategy_vs_stock={comparison_plot}")

    # 只打印最后几行，避免命令行输出过长；完整结果保存在 Parquet 中。
    preview_cols = [
        "trade_date",
        args.price_col,
        "fast_ma",
        "slow_ma",
        "trend_signal_t",
        "raw_action",
        "executed_action",
        "cash",
        "shares",
        "portfolio_value",
        "strategy_total_return",
        "stock_total_return",
    ]
    print(result.tail()[preview_cols])
    print_summary(summarize(result, initial_capital=args.initial_capital))


if __name__ == "__main__":
    main()

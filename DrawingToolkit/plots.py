"""策略研究通用绘图函数。

本模块先提供 Lesson 1 需要的两类图：

1. 双均线价格图：价格、快均线、慢均线、实际买卖点；
2. 策略对比图：策略本金曲线、买入持有基准曲线、可选股票价格走势。

设计原则：

- 输入统一使用 `pandas.DataFrame`，方便承接任意 Lesson 的回测结果；
- 列名都可以通过参数覆盖，避免函数绑定到某一节课的固定字段；
- 函数默认保存图片到本地路径，也支持不传 `output_path` 时返回 Figure；
- 当前采用 Matplotlib，后续若要换成交互式图表，可以在这里集中扩展。
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from typing import Iterable

# Matplotlib 会在导入时初始化缓存目录。用户机器上的 `~/.matplotlib` 可能不可写，
# 所以这里设置一个可写的临时目录；如果用户自己设置了 MPLCONFIGDIR，则尊重用户设置。
MPLCONFIGDIR = Path(tempfile.gettempdir()) / "quanttrading_matplotlib"
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))

import matplotlib

# 这个工具包的主要用途是生成本地图片文件。使用 Agg 后端可以避免命令行、
# CI 或无窗口环境里因为 GUI 后端不可用而失败。
if "matplotlib.pyplot" not in sys.modules:
    matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

from .config import DEFAULT_PLOT_DPI, DEFAULT_PLOT_FIGSIZE


DEFAULT_FONT_CANDIDATES = [
    "PingFang SC",
    "Songti SC",
    "Heiti SC",
    "Microsoft YaHei",
    "SimHei",
    "Arial Unicode MS",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]


def configure_matplotlib_fonts(preferred_fonts: Iterable[str] | None = None) -> None:
    """配置 Matplotlib 中文字体和负号显示。

    Matplotlib 默认字体经常不能显示中文。这里会优先选择 macOS 和 Windows
    上常见的中文字体；如果机器上没有这些字体，则回退到 Matplotlib 自带字体。
    """

    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    candidates = list(preferred_fonts or DEFAULT_FONT_CANDIDATES)
    selected_fonts = [font for font in candidates if font in available_fonts]
    if selected_fonts:
        plt.rcParams["font.sans-serif"] = selected_fonts
    plt.rcParams["axes.unicode_minus"] = False


def prepare_time_series_frame(data: pd.DataFrame, *, date_col: str, required_cols: Iterable[str]) -> pd.DataFrame:
    """复制并整理时间序列数据。

    这个函数集中处理三类常见清洗动作：

    - 检查必需列是否存在；
    - 把 `YYYYMMDD`、`YYYY-MM-DD` 或 datetime 日期统一成 pandas datetime；
    - 按日期升序排序，保证折线不会乱连。
    """

    required = [date_col, *required_cols]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    df = data.copy()
    raw_dates = df[date_col]
    if pd.api.types.is_datetime64_any_dtype(raw_dates):
        dates = pd.to_datetime(raw_dates)
    else:
        date_text = raw_dates.astype(str).str.strip()
        compact_dates = date_text.str.replace("-", "", regex=False)
        dates = pd.to_datetime(compact_dates, format="%Y%m%d", errors="coerce")
        if dates.isna().any():
            dates = pd.to_datetime(date_text, errors="coerce")

    if dates.isna().any():
        bad_examples = raw_dates[dates.isna()].head(3).tolist()
        raise ValueError(f"date column {date_col!r} contains invalid values, examples={bad_examples}")

    df[date_col] = dates
    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(date_col).reset_index(drop=True)
    return df


def save_or_return_figure(fig: plt.Figure, output_path: str | Path | None, *, dpi: int, close: bool) -> Path | plt.Figure:
    """保存图片，或在未传路径时返回 Figure 对象。

    返回值约定：

    - 传入 `output_path`：保存文件并返回 `Path`；
    - 不传 `output_path`：返回 Matplotlib `Figure`，调用方可以自行显示或保存。
    """

    fig.tight_layout()
    if output_path is None:
        return fig

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    if close:
        plt.close(fig)
    return path


def format_date_axis(ax: plt.Axes) -> None:
    """统一设置日期坐标轴，避免日期标签过密。"""

    locator = mdates.AutoDateLocator(minticks=5, maxticks=10)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def annotate_trade_dates(
    ax: plt.Axes,
    trades: pd.DataFrame,
    *,
    date_col: str,
    price_col: str,
    color: str,
    y_offset_points: int,
    max_annotations: int,
) -> None:
    """在买卖点旁边标注日期。

    标注太多会让图不可读，所以默认最多标注 `max_annotations` 个点。
    超出时仍然保留买卖点 marker，只省略文字日期。
    """

    if trades.empty or len(trades) > max_annotations:
        return

    for _, row in trades.iterrows():
        ax.annotate(
            row[date_col].strftime("%Y-%m-%d"),
            xy=(row[date_col], row[price_col]),
            xytext=(0, y_offset_points),
            textcoords="offset points",
            ha="center",
            va="bottom" if y_offset_points >= 0 else "top",
            fontsize=8,
            color=color,
            rotation=35,
        )


def plot_dual_moving_average(
    data: pd.DataFrame,
    *,
    output_path: str | Path | None = None,
    date_col: str = "trade_date",
    price_col: str = "close",
    fast_ma_col: str = "fast_ma",
    slow_ma_col: str = "slow_ma",
    action_col: str = "executed_action",
    buy_action: str = "buy",
    sell_action: str = "sell",
    title: str | None = None,
    figsize: tuple[float, float] = DEFAULT_PLOT_FIGSIZE,
    dpi: int = DEFAULT_PLOT_DPI,
    annotate_trades: bool = True,
    max_annotations: int = 60,
    close: bool = True,
) -> Path | plt.Figure:
    """绘制价格、双均线和买卖日期。

    Parameters
    ----------
    data:
        至少包含日期列、价格列、快均线列、慢均线列和动作列的 DataFrame。
    output_path:
        图片保存路径；不传时返回 Figure 对象。
    action_col:
        默认使用 `executed_action`，因此图上标的是“真实成交日”，不是信号日。
        如果你想看信号日，可以传入 `action_for_next_day` 或其他动作列。
    annotate_trades:
        是否在买卖点旁边写出日期。交易次数很多时建议关闭。
    """

    configure_matplotlib_fonts()
    df = prepare_time_series_frame(
        data,
        date_col=date_col,
        required_cols=[price_col, fast_ma_col, slow_ma_col],
    )
    if action_col not in df.columns:
        raise ValueError(f"missing action column: {action_col}")

    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(df[date_col], df[price_col], color="#202124", linewidth=1.2, label=price_col)
    ax.plot(df[date_col], df[fast_ma_col], color="#f59e0b", linewidth=1.1, label=fast_ma_col)
    ax.plot(df[date_col], df[slow_ma_col], color="#2563eb", linewidth=1.1, label=slow_ma_col)

    buy_points = df[df[action_col] == buy_action]
    sell_points = df[df[action_col] == sell_action]

    ax.scatter(
        buy_points[date_col],
        buy_points[price_col],
        marker="^",
        s=70,
        color="#16a34a",
        edgecolors="white",
        linewidths=0.8,
        zorder=5,
        label="buy",
    )
    ax.scatter(
        sell_points[date_col],
        sell_points[price_col],
        marker="v",
        s=70,
        color="#dc2626",
        edgecolors="white",
        linewidths=0.8,
        zorder=5,
        label="sell",
    )

    if annotate_trades:
        annotate_trade_dates(
            ax,
            buy_points,
            date_col=date_col,
            price_col=price_col,
            color="#15803d",
            y_offset_points=10,
            max_annotations=max_annotations,
        )
        annotate_trade_dates(
            ax,
            sell_points,
            date_col=date_col,
            price_col=price_col,
            color="#b91c1c",
            y_offset_points=-14,
            max_annotations=max_annotations,
        )

    ax.set_title(title or "Dual Moving Average Signals")
    ax.set_ylabel("price")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.35)
    ax.legend(loc="best")
    format_date_axis(ax)
    fig.autofmt_xdate()

    return save_or_return_figure(fig, output_path, dpi=dpi, close=close)


def plot_strategy_vs_stock(
    data: pd.DataFrame,
    *,
    output_path: str | Path | None = None,
    date_col: str = "trade_date",
    portfolio_col: str = "portfolio_value",
    benchmark_col: str = "benchmark_value",
    price_col: str = "close",
    initial_capital: float | None = None,
    title: str | None = None,
    figsize: tuple[float, float] = DEFAULT_PLOT_FIGSIZE,
    dpi: int = DEFAULT_PLOT_DPI,
    show_price: bool = True,
    close: bool = True,
) -> Path | plt.Figure:
    """绘制策略本金变化与股票走势对比。

    图中默认包含三条信息：

    - 策略账户市值：来自 `portfolio_col`；
    - 买入并持有基准：优先使用 `benchmark_col`，若没有则由 `price_col` 归一化得到；
    - 股票原始价格：用右轴显示，可通过 `show_price=False` 关闭。

    这张图回答的是：双均线策略的本金曲线，是否比直接买入这只股票更好。
    """

    configure_matplotlib_fonts()

    # 如果已经有 benchmark_value，就直接使用；否则需要用价格列现场构造买入持有基准。
    required_cols = [portfolio_col]
    has_benchmark = benchmark_col in data.columns
    if has_benchmark:
        required_cols.append(benchmark_col)
    else:
        required_cols.append(price_col)
    if show_price and price_col not in required_cols:
        required_cols.append(price_col)

    df = prepare_time_series_frame(data, date_col=date_col, required_cols=required_cols)

    if initial_capital is None:
        initial_capital = float(df[portfolio_col].iloc[0])
    if not has_benchmark:
        first_price = float(df[price_col].iloc[0])
        if first_price <= 0:
            raise ValueError("first price must be positive to build benchmark")
        df[benchmark_col] = initial_capital * df[price_col] / first_price

    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(df[date_col], df[portfolio_col], color="#2563eb", linewidth=1.4, label="strategy capital")
    ax.plot(df[date_col], df[benchmark_col], color="#111827", linewidth=1.2, linestyle="--", label="buy and hold")
    ax.axhline(initial_capital, color="#6b7280", linewidth=0.9, linestyle=":", label="initial capital")

    ax.set_title(title or "Strategy Capital vs Stock Buy-and-Hold")
    ax.set_ylabel("capital")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.35)
    format_date_axis(ax)

    axes = [ax]
    if show_price:
        price_ax = ax.twinx()
        price_ax.plot(df[date_col], df[price_col], color="#9ca3af", linewidth=0.9, alpha=0.65, label=price_col)
        price_ax.set_ylabel("stock price")
        axes.append(price_ax)

    # 双轴图需要手工合并 legend，否则右轴价格线不会出现在图例里。
    handles: list[object] = []
    labels: list[str] = []
    for axis in axes:
        axis_handles, axis_labels = axis.get_legend_handles_labels()
        handles.extend(axis_handles)
        labels.extend(axis_labels)
    ax.legend(handles, labels, loc="best")
    fig.autofmt_xdate()

    return save_or_return_figure(fig, output_path, dpi=dpi, close=close)

"""QuantTrading 通用绘图接口。

后续 Lessons 里只需要从这里 import 公共函数，不直接依赖具体绘图实现文件。
"""

from .config import DEFAULT_PLOT_DPI, DEFAULT_PLOT_FIGSIZE
from .plots import plot_dual_moving_average, plot_strategy_vs_stock

__all__ = [
    "DEFAULT_PLOT_DPI",
    "DEFAULT_PLOT_FIGSIZE",
    "plot_dual_moving_average",
    "plot_strategy_vs_stock",
]

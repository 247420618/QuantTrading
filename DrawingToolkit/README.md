# DrawingToolkit

`DrawingToolkit` 是本仓库的公共绘图接口层。后续 Lesson 需要画图时，优先在这里新增或复用函数，避免每节课都复制一份 Matplotlib 代码。

当前教学图固定默认尺寸为 `28 x 7` 英寸，默认分辨率为 `600 dpi`。公共常量在 `DrawingToolkit.config` 中维护。

当前提供两个函数：

| 函数 | 用途 |
| --- | --- |
| `plot_dual_moving_average` | 绘制价格、快均线、慢均线，并标出买入和卖出日期 |
| `plot_strategy_vs_stock` | 绘制策略本金曲线、买入持有基准曲线，并可选绘制股票价格走势 |

最小用法：

```python
from DrawingToolkit import plot_dual_moving_average, plot_strategy_vs_stock

plot_dual_moving_average(
    result,
    output_path="Lessons-1/dual_ma_signals.png",
    figsize=(28, 7),
    dpi=600,
)

plot_strategy_vs_stock(
    result,
    output_path="Lessons-1/strategy_vs_stock.png",
    figsize=(28, 7),
    dpi=600,
)
```

这里的 `result` 是包含回测结果的 `pandas.DataFrame`。默认列名与 `Lessons-1/dual_moving_average.py` 输出一致；如果后续课程使用不同列名，可以通过函数参数覆盖。

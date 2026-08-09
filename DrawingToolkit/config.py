"""DrawingToolkit 的公共绘图配置。

这组尺寸和分辨率作为当前仓库教学图的固定默认标准：

- 图片尺寸：28 x 7 英寸；
- 图片分辨率：600 dpi。

如果后续确实需要为某一节课单独调整，可以在调用绘图函数时显式传参覆盖。
"""

DEFAULT_PLOT_FIGSIZE: tuple[float, float] = (28.0, 7.0)
DEFAULT_PLOT_DPI: int = 600

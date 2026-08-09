# QuantTrading

面向沪深股票的量化交易学习与研究仓库。

## 学习文档

- [沪深股票量化交易入门到进阶教程](tutorial.md)
- [Lesson 0：金融与市场背景课](Lesson-0/README.md)
  - [0.1 财务、行业与估值基础](Lesson-0/01-financial-fundamentals.md)
  - [0.2 行情、成交、盘口与技术指标](Lesson-0/02-market-indicators.md)
  - [0.3 宏观、政策、消息与趋势](Lesson-0/03-macro-policy-news-regime.md)
  - [0.4 跨资产、实体经济与另类指标](Lesson-0/04-cross-asset-indicators.md)
- [Lesson 1：基础策略实验课](Lessons-1/README.md)
  - [1.1 双均线趋势策略](Lessons-1/01-dual-moving-average.md)

## 工具代码

- [Tools：数据获取接口层](Tools/README.md)
  - 当前数据源：Tushare Pro
  - 主要入口：`Tools.quant_data.DataPortal`
  - 默认缓存：`data/raw/tushare/`
- [DrawingToolkit：公共绘图接口层](DrawingToolkit/README.md)
  - 当前支持：双均线买卖点图、策略本金与股票走势对比图

## Markdown 公式约定

- 块公式统一使用带 `math` 语言标记的三反引号围栏，不使用双美元符号块。
- 行内公式使用单美元符号作为定界符：定界符内侧不要保留首尾空格；定界符外侧与正文或中文标点之间都保留空格。
- 不使用 GitHub 数学渲染器禁止的宏。

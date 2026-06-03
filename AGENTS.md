# AGENTS.md

## 项目定位

本项目是中文 A 股多维研究 Skill / CLI 工具。它优化现有项目，不重建架构，不改变用户入口。普通用户通过“命令 + 自然语言”使用；CLI 是内部执行工具。

## 三命令入口

只允许三个主命令：

- `/股票`
- `/持仓`
- `/观察池`

不要新增 `/技术`、`/风险`、`/公告`、`/复盘`、`/买入`、`/卖出` 或其他用户入口。自然语言中的“技术面、公告、风险、财务、资金流”等词只进入 `focus` 字段。

## 数据源说明

- `TUSHARE_TOKEN` 只能从环境变量读取。
- 生产分析必须使用 Tushare Pro。
- 未设置 `TUSHARE_TOKEN` 时必须直接失败，不允许使用其他行情源回退。
- 外部接口失败必须写入 `data_gaps`，不得编造数据。
- 测试必须使用 `StaticProvider` 或 fake provider，不访问真实网络服务。

## 数据契约说明

`market_pack.json` 是唯一数值事实来源，必须保存：

- `meta`
- `request`
- `data_contract`
- `quote`
- `daily_bars`
- `indicators`
- `fundamental`
- `announcements`
- `moneyflow`
- `market_context`
- `data_gaps`
- `data_audit`
- `risk_flags`
- `trace`

`raw_data.json` 保存规范化原始数据快照，不允许包含 token、secret、cookie。

## 测试规则

运行：

```bash
python -m pytest
```

测试必须覆盖：

- 三命令解析
- 股票代码和中文名识别
- 时间范围解析
- 持仓信息解析
- `market_pack.json` 关键字段
- `raw_data.json` 落盘
- 观察池报告
- 评分权重配置

## 代码风格

- 保持现有轻量 Python 包结构。
- 优先小函数、清晰数据结构、可测试逻辑。
- 外部数据源通过 provider 接口封装。
- 报告、日志和说明默认中文。
- 不引入不必要的大型框架。

## 禁止行为

- 不编造行情、成交量、估值、财务、资金流、指数、公告数据。
- 不输出直接买入、卖出、满仓、清仓。
- 不输出目标价。
- 不把网页搜索结果作为交易数值依据。
- 不提交 `.venv/`、`.pytest_cache/`、`output/`、`.env`。
- 不删除测试或弱化断言来通过测试。

## 修改前检查清单

- 已阅读 `README.md`、`SKILL.md`、`AGENTS.md`。
- 已阅读 `stock_analyze/` 核心代码。
- 已确认不改变三命令入口。
- 已确认不会提交 token 或运行产物。

## 修改后检查清单

- 运行 `python -m pytest`。
- 检查 `git status --short --ignored`。
- 确认 `.venv/`、`.pytest_cache/`、`output/` 被忽略。
- 确认报告中文、无目标价、无直接买卖建议。
- 确认所有数值来自 `market_pack.json`。

---
name: a-share-research-zh
description: 使用中文命令和自然语言输入，对用户指定的 A 股股票进行多维研究分析。数据源为 Tushare Pro 或 Akshare fallback，输出中文报告。
---

# A 股多维研究 Skill

## Skill 使命

本 Skill 是中文 A 股多维研究工具。普通用户只通过“命令 + 自然语言”表达需求；CLI 脚本只是内部执行工具，不是普通用户主要入口。

本 Skill 不编造行情数据，不输出目标价，不输出直接买入、卖出、满仓、清仓等交易指令。所有数值结论必须来自 `output/{symbol}/market_pack.json`。

## 三个命令

只保留三个用户入口：

- `/股票`：单只股票多维研究。
- `/持仓`：结合用户成本、数量、仓位和持仓周期做持仓风险快检。
- `/观察池`：对用户提供的多只股票做横向观察和对比。

禁止新增 `/技术`、`/风险`、`/公告`、`/复盘`、`/买入`、`/卖出` 等用户入口。技术面、风险、公告、财务等词只作为自然语言关注重点。

## 输入格式

```text
/{命令} {自然语言需求}
```

示例：

```text
/股票 分析 600519.SH，最近两年，重点看技术面和估值
/持仓 300750.SZ，成本 185.30，持仓 200 股，中线持有
/观察池 600519.SH、300750.SZ、000001.SZ，做多维对比
```

## 命令解析规则

1. 命令前缀决定主模式。
2. 自然语言补充股票、时间范围、分析周期、关注重点和持仓信息。
3. 支持标准代码、六位代码、中文股票名和多股票分隔符。
4. 如果中文名无法唯一匹配，停止执行并要求用户补充标准代码。
5. 未写时间范围时默认最近两年。
6. 未写分析周期时默认中线。
7. `/股票` 输入多个股票时逐只生成单股报告；横向比较使用 `/观察池`。

## 数据流程

```text
解析用户命令
→ 生成 request.json
→ 拉取结构化数据
→ 生成 raw_data.json
→ 生成 market_pack.json
→ 校验 data_audit 和 data_gaps
→ 生成 scorecard.json
→ 生成 audit.md
→ 生成 decision_dossier.md
→ 生成中文 report.md / position_report.md / watchlist_report.md
→ 在对话中输出中文摘要
```

## 数据契约

`market_pack.json` 是唯一数值事实来源，必须包含：

- `meta`：股票、交易日、生成时间、数据源、契约版本。
- `request`：用户请求解析结果。
- `data_contract`：字段要求和禁止编造规则。
- `quote`：最新日线行情。
- `daily_bars`：日线原始序列。
- `indicators`：均线、MACD、RSI、布林带、ATR、波动率、回撤、量比等技术指标。
- `fundamental`：估值、财报、营收、利润、ROE 等。
- `announcements`：公告列表和风险分类。
- `moneyflow`：个股资金流。
- `market_context`：宽基指数、行业指数状态、市场情绪。
- `data_gaps`：缺失或失败的数据项。
- `data_audit`：字段级审计状态。
- `risk_flags`：自动风险标记。
- `trace`：关键数值来源说明。

`raw_data.json` 保存规范化后的原始数据快照，用于审计；不得包含 token、secret、cookie。

## 分析维度

- 技术面：趋势、均线、MACD、RSI、布林带、ATR、波动率、回撤。
- 量价：成交量均线、5日/20日量比、缩量反弹、放量下跌。
- 基本面：营收、归母净利润、同比增速、ROE、毛利率。
- 估值：PE TTM、PB、市值。
- 资金面：当日净流入、5日净流入。
- 公告事件：减持、解禁、监管、业绩预警、退市、质押冻结。
- 市场环境：上证指数、沪深300、中证500、行业指数状态、涨跌停情绪。
- 数据审计：字段完整性、数据缺口、接口失败。

## 输出文件

单只股票：

```text
output/{symbol}/request.json
output/{symbol}/raw_data.json
output/{symbol}/market_pack.json
output/{symbol}/scorecard.json
output/{symbol}/audit.md
output/{symbol}/decision_dossier.md
output/{symbol}/report.md
```

持仓快检：

```text
output/{symbol}/position_report.md
```

观察池：

```text
output/watchlist_report.md
output/{symbol}/report.md
```

## 中文报告结构

报告必须包含：

1. 核心结论
2. 数据状态
3. 关键证据
4. 技术面分析
5. 量价关系
6. 基本面与估值
7. 资金流分析
8. 行业指数与市场环境
9. 公告与事件风险
10. 持仓风险快检
11. 综合评分
12. 主要风险
13. 观察条件
14. 数据局限
15. 数据缺口
16. 免责声明

## 评级限制

允许输出：

- `watch`：值得观察
- `neutral`：中性
- `avoid`：风险较高

禁止输出：

- `buy`
- `sell`
- `strong buy`
- `strong sell`
- 目标价
- 无条件止损价

## 禁止行为

- 禁止编造行情、成交量、财务、估值、资金流、指数和公告数据。
- 禁止使用模型记忆补全数值。
- 禁止把网页搜索结果作为价格、均线、成交量、估值的唯一计算来源。
- 禁止把 `TUSHARE_TOKEN` 写入代码、测试、日志或报告。
- 禁止在测试中访问真实 Tushare / Akshare。
- 禁止新增超过三个主命令的用户入口。

## 最终检查清单

- 是否保持 `/股票`、`/持仓`、`/观察池` 三命令入口。
- 是否生成 `market_pack.json`。
- 是否生成 `raw_data.json`、`audit.md`、`decision_dossier.md`。
- 是否所有数值结论都可追溯到 `market_pack.json`。
- 是否说明 `trade_date` 和数据局限。
- 是否列出 `data_gaps`。
- 是否避免直接买卖建议和目标价。
- 是否报告全中文。


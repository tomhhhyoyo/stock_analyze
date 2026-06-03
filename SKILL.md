---
name: a-share-research-zh
description: 使用中文命令和自然语言输入，对用户指定的 A 股股票进行多维研究分析。数据源为 Tushare Pro 或 Akshare fallback，输出中文报告。
---

# A 股多维研究 Skill

## 使命

本 Skill 使用“命令 + 自然语言”的方式接收用户请求，对用户指定的 A 股股票进行中文多维研究分析。

用户不需要填写 JSON，也不需要记忆内部 CLI 参数，只需要输入：

- `/股票 分析 600519.SH`
- `/持仓 300750.SZ，成本 185.30，持仓 200 股`
- `/观察池 600519.SH、300750.SZ、000001.SZ，做对比`

## 核心原则

1. 不编造行情数据。
2. 所有数值结论必须来自 `output/{symbol}/market_pack.json`。
3. 不使用模型记忆生成价格、成交量、估值、财务指标、资金流或技术指标。
4. 不声称实时行情，除非数据包中明确包含实时行情时间戳。
5. 如果数据缺失、过期或日期不一致，停止数值分析，输出中文数据缺口报告。
6. 不输出直接买入、卖出、满仓、清仓等交易指令。
7. 不输出目标价。
8. 不输出止损价，除非用户明确提供交易系统参数。
9. 所有面向用户的输出必须使用中文。
10. 报告必须包含风险提示和数据局限。

## 三个主命令

- `/股票`：单只股票多维研究，支持技术面、基本面、估值、资金面、公告和风险审计。
- `/持仓`：结合用户成本、持仓数量或仓位比例，进行持仓风险快检。
- `/观察池`：对用户提供的多只股票进行横向对比和观察池分析。

不单独设置 `/技术`、`/风险`、`/公告`、`/复盘` 命令；这些词作为自然语言关注重点处理。

## 命令解析规则

1. 命令前缀决定主模式。
2. 自然语言补充股票代码、时间范围、持仓成本、持仓数量、分析周期和关注重点。
3. 如果命令和自然语言冲突，以命令为准。
4. 如果用户没有写时间范围，默认最近两年。
5. 如果用户没有写分析周期，默认中线。
6. 如果用户输入多个股票但使用 `/股票`，逐只生成单股报告。
7. 如果用户输入股票名称，先尝试内置名称映射；无法唯一匹配时要求用户确认标准代码。

## 数据流程

每次分析必须执行：

```text
解析用户命令
→ 生成内部请求
→ 获取结构化日线、财报、公告、资金流、指数环境和市场情绪数据
→ 生成 output/{symbol}/market_pack.json
→ 生成 scorecard.json
→ 生成 audit.md
→ 生成 decision_dossier.md
→ 生成中文 report.md 或 position_report.md
→ 在对话中输出中文摘要
```

## 内部执行命令

```bash
python -m stock_analyze "/股票 分析 600519.SH，最近两年，重点看技术面和估值"
python -m stock_analyze "/持仓 300750.SZ，成本 185.30，持仓 200 股"
python -m stock_analyze "/观察池 600519.SH、300750.SZ、000001.SZ，做对比"
```

## 数据源

- 优先：`TUSHARE_TOKEN` 环境变量存在时使用 Tushare Pro。
- Tushare 当前接入：
  - `daily`：日线行情。
  - `daily_basic`：PE TTM、PB、市值等估值字段。
  - `fina_indicator` / `income`：财务指标、营收、归母净利润、同比增速。
  - `anns`：公告与事件标题。
  - `moneyflow`：个股资金流。
  - `index_daily`：上证指数、沪深300、中证500。
  - `limit_list_d`：涨跌停情绪样本。
- 回退：未设置 `TUSHARE_TOKEN` 时使用 Akshare 日线接口；财报、公告、资金流、指数情绪字段会进入 `data_gaps`。
- 行业指数：当前保留 `market_context.industry` 字段和缺口审计；精确行业指数需要后续配置股票到行业指数代码的映射。
- 测试：单元测试使用 `StaticProvider`，不访问真实外部服务。

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

`market_pack.json` 中包含：

- `daily_bars`
- `indicators`
- `fundamental`
- `announcements`
- `moneyflow`
- `market_context`
- `data_gaps`
- `risk_flags`

持仓快检：

```text
output/{symbol}/position_report.md
```

观察池：

```text
output/watchlist_report.md
output/{symbol}/report.md
```

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

## 最终检查

输出前必须检查：

1. 是否生成 `market_pack.json`。
2. 是否所有数值都有来源。
3. 是否说明数据日期。
4. 是否说明不是 tick 级实时行情。
5. 是否包含风险提示。
6. 是否避免直接买卖建议。
7. 是否中文输出。

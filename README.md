# stock-analyze

中文 A 股多维研究 Skill。用户只需要使用 3 个命令：

- `/股票`
- `/持仓`
- `/观察池`

项目会生成结构化数据包、评分、审计、证据链和中文报告。所有数值结论都必须来自 `market_pack.json`。

## 安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

如需 Tushare：

```bash
export TUSHARE_TOKEN=your_token
```

未设置 `TUSHARE_TOKEN` 时，会尝试使用 Akshare 日线数据；财报、公告、资金流、指数和情绪字段会写入数据缺口。

## 数据范围

当前 Tushare 接入：

- 日线行情：`daily`
- 估值：`daily_basic`
- 财报：`fina_indicator`、`income`
- 公告：`anns`
- 资金流：`moneyflow`
- 指数环境：`index_daily`
- 市场情绪：`limit_list_d`

行业指数已保留输出字段，但需要后续配置“股票到行业指数代码”的映射后才能精确拉取。

## 使用

```bash
.venv/bin/python -m stock_analyze "/股票 分析 600519.SH，最近两年，重点看技术面和估值"
```

```bash
.venv/bin/python -m stock_analyze "/持仓 300750.SZ，成本 185.30，持仓 200 股"
```

```bash
.venv/bin/python -m stock_analyze "/观察池 600519.SH、300750.SZ、000001.SZ，做对比"
```

## 输出

单股输出：

```text
output/{symbol}/request.json
output/{symbol}/raw_data.json
output/{symbol}/market_pack.json
output/{symbol}/scorecard.json
output/{symbol}/audit.md
output/{symbol}/decision_dossier.md
output/{symbol}/report.md
```

`market_pack.json` 包含：

- `daily_bars`
- `indicators`
- `fundamental`
- `announcements`
- `moneyflow`
- `market_context`
- `data_gaps`
- `risk_flags`

观察池输出：

```text
output/watchlist_report.md
```

## 评级

只输出研究观察评级：

- `watch`
- `neutral`
- `avoid`

不输出 `buy` / `sell` / 目标价。

## 测试

```bash
.venv/bin/python -m pytest
```

## 免责声明

本项目仅用于学习研究和流程演示，不构成投资建议。

# stock-analyze

中文 A 股多维研究 Skill。用户只需要使用 3 个命令：

- `/股票`
- `/持仓`
- `/观察池`

项目会生成结构化数据包、评分、审计、证据链和中文报告。所有数值结论都必须来自 `market_pack.json`。

普通用户入口保持只有三个：

```text
/{命令} {自然语言需求}
```

CLI 只是内部执行工具，不是普通用户需要记忆的主要入口。

## 安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

必须设置 Tushare Token：

```bash
export TUSHARE_TOKEN=your_token
```

未设置 `TUSHARE_TOKEN` 时，程序会直接失败并提示设置环境变量；不会使用其他行情源回退。

## 数据范围

当前数据全部通过 Tushare 获取：

- 日线行情：`daily`
- 估值：`daily_basic`
- 财报：`fina_indicator`、`income`
- 公告：`anns`
- 资金流：`moneyflow`
- 指数环境：`index_daily`
- 市场情绪：`limit_list_d`
- 股票名称映射：`stock_basic`

行业指数已保留输出字段，但需要后续配置“股票到行业指数代码”的映射后才能精确拉取。

## 数据契约

`market_pack.json` 是唯一数值事实来源，包含：

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

`raw_data.json` 保存规范化后的原始数据快照，用于审计，不包含 token 或密钥。

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
output/{中文名（symbol）}/request.json
output/{中文名（symbol）}/raw_data.json
output/{中文名（symbol）}/market_pack.json
output/{中文名（symbol）}/scorecard.json
output/{中文名（symbol）}/audit.md
output/{中文名（symbol）}/decision_dossier.md
output/{中文名（symbol）}/report.md
```

如果中文名缺失，输出目录会回退为 `output/{symbol}`。

`market_pack.json` 包含：

- `daily_bars`
- `indicators`
- `fundamental`
- `announcements`
- `moneyflow`
- `market_context`
- `data_gaps`
- `data_audit`
- `risk_flags`

## 配置

评分权重位于：

```text
config/scoring_weights.json
```

股票中文名映射不再依赖少量手工字典。程序真实运行时会先通过 Tushare `stock_basic` 拉取当前上市 A 股基础列表，并生成本地缓存：

```text
config/symbol_cache.json
```

该文件是运行缓存，已加入 `.gitignore`，不会提交到仓库。解析 `/股票 中国电信`、`/观察池 贵州茅台、宁德时代` 这类中文名时，会优先读取缓存；代码中的内置映射只作为缓存不存在时的离线兜底。

缓存格式示例：

```json
{
  "updated_at": "2026-06-03T10:00:00",
  "source": "tushare.stock_basic",
  "count": 2,
  "items": [
    {
      "name": "贵州茅台",
      "ts_code": "600519.SH",
      "symbol": "600519",
      "market": "主板"
    }
  ]
}
```

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

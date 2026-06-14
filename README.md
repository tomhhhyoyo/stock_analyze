# stock-analyze

中文 A 股个人投研工具，用于个人持仓分析、自选池筛选和单股研究；不是自动荐股系统，也不做推荐结果复盘。用户只需要使用 3 个命令：

- `/股票`
- `/持仓`
- `/观察池`

项目会生成结构化数据包、评分、审计、证据链和中文报告。所有数值结论都必须来自 `market_pack.json`。
不会新增 `/复盘`、`/买入`、`/卖出`、`/荐股`、`/止损`、`/目标价` 等命令，也不会生成 `review/` 目录、5日/10日/20日收益复盘、`rating_accuracy`、`weekly_review.md` 或 `daily_review.json`。

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

未设置 `TUSHARE_TOKEN` 时，程序会直接失败并提示设置环境变量；不会使用 AkShare 或其他行情源绕过 token 要求。

## 数据范围

生产分析必须先设置 `TUSHARE_TOKEN` 并启动 Tushare 主流程；AkShare 仅作为个别 Tushare 接口权限不足、限频或覆盖不足后的公开数据兜底，不能作为无 token 启动路径。

Tushare 主数据包括：

- 日线行情：`daily`
- 复权因子：`adj_factor`，与 `daily` 合并生成 `qfq_open`、`qfq_high`、`qfq_low`、`qfq_close`，技术指标优先使用前复权价格计算
- 估值：`daily_basic`
- 换手与流通市值：`daily_basic`，为量价模块补充 `turnover_rate`、`turnover_rate_f`、`volume_ratio`、`total_mv`、`circ_mv`
- 财报：`fina_indicator`、`income`、`balancesheet`、`cashflow`
- 公告：`anns_d`
- 资金流：`moneyflow`
- 指数环境：`index_daily`
- 行业分类：`index_member_all`
- 行业指数：`sw_daily`
- 涨跌停价：`stk_limit`，写入 `quote`、`daily_bars`，并参与 `risk_flags`
- 市场情绪：优先 `limit_list_d`，降级 `limit_list_ths`，再降级 `stk_limit` + `daily` 近似计算
- 股票名称映射：`stock_basic`

核心价格、成交量、估值、财务、资金流必须来自 Tushare；如缺失，必须写入 `data_gaps`，不允许用缺失数据推断结论。只有在 `TUSHARE_TOKEN` 已设置、Tushare 主流程已启动后，若公告、行业指数、涨跌停情绪等非核心字段因权限不足或接口覆盖问题不可用，项目才会尝试 AkShare 公开数据作为兜底，并在 `market_pack.json` 中明确写入 `source=akshare.*`：

- 公告兜底：AkShare `stock_individual_notice_report`
- 申万行业指数兜底：AkShare `index_hist_sw`
- 涨跌停情绪兜底：AkShare 东方财富涨停池、炸板池、跌停池

已在 `market_pack.json` 中预留但可为空的 Tushare 字段：

- 第二批：`fina_mainbz`、`forecast`、`express`、`dividend`、`disclosure_date`
- 第三批：`top_list`、`top_inst`、`margin`、`margin_detail`、`moneyflow_hsgt`、`hsgt_top10`、`index_dailybasic`、`index_classify`、`index_member`、`concept`、`concept_detail`

行业指数会优先通过 Tushare `index_member_all` 自动识别股票所属申万一级行业，再用 `sw_daily` 拉取对应行业指数；`config/industry_index_map.json` 仅用于人工覆盖或兜底。`limit_list_d`、`index_member_all` 和 `sw_daily` 这类频率受限接口会写入 `data_cache/`，同一交易日重复分析时优先使用缓存，避免反复触发 Tushare 限频。

Tushare 调用默认会对限频、超时、临时连接失败做等待重试，默认等待序列为 `1,3` 秒，可通过环境变量覆盖：

```bash
export TUSHARE_RETRY_DELAYS=2,5,10
```

权限不足、接口不存在这类错误不会无意义重试，会优先尝试同源兜底和 AkShare 公开数据兜底。例如公告 `anns_d` 权限不足时，会先尝试 AkShare 个股公告，再尝试 `disclosure_date` 生成财报披露事件；行业指数 `sw_daily` 不可用时，会尝试 `index_daily`、AkShare 申万指数和本地历史缓存。若仍不可用，必须继续写入 `data_gaps`，不能隐藏缺口或编造行业指数行情。

市场情绪如果使用 `stk_limit` + `daily` 兜底，涨跌停状态由日线价格与涨跌停价近似计算，无法覆盖封板时间、封单金额和真实炸板次数。全部来源失败时，市场情绪只作为结构化 warning 记录，主报告和核心技术、估值、基本面分析继续生成。

## 数据契约

`market_pack.json` 是唯一数值事实来源，包含：

- `meta`
- `request`
- `data_contract`
- `quote`
- `daily_bars`
- `indicators`
- `volume_price`
- `fundamental`
- `tushare_extensions`
- `announcements`
- `moneyflow`
- `market_context`
- `market_sentiment`
- `market_regime`
- `sector_context`
- `data_gaps`
- `data_audit`
- `risk_flags`
- `trace`

`raw_data.json` 保存规范化后的原始数据快照，用于审计，不包含 token 或密钥；包含 `daily`、`daily_basic`、`financials`、`moneyflow`、`market_context`、`market_sentiment`、`volume_price` 的当次快照。

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
output/{中文名（symbol）}/report.html
```

如果中文名缺失，输出目录会回退为 `output/{symbol}`。

`market_pack.json` 包含：

- `daily_bars`
- `indicators`
- `volume_price`
- `fundamental`
- `tushare_extensions`
- `announcements`
- `moneyflow`
- `market_context`
- `market_regime`
- `sector_context`
- `data_gaps`
- `data_audit`
- `risk_flags`

## 配置

评分权重位于：

```text
config/scoring_weights.json
```

当前默认权重：

- 趋势结构：25%
- 量价关系：20%
- 基本面质量：20%
- 估值位置：15%
- 资金流：10%
- 风险事件：10%

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
output/watchlist_report.html
```

## 评级

用户可见报告只输出中文研究观察评级：

- 偏强，重点跟踪
- 中性偏强，继续观察
- 中性，等待确认
- 中性偏弱，谨慎观察
- 偏弱，优先规避风险

内部 `scorecard.json` 会保存 `rating_code` 和 `rating_label`，用户可见报告只展示中文 `rating_label`。

不输出 `buy` / `sell` / 买入 / 卖出 / 加仓 / 清仓 / 目标价 / 无条件止损价。

## 测试

```bash
.venv/bin/python -m pytest
```

## 免责声明

本项目仅用于学习研究和流程演示，不构成投资建议。

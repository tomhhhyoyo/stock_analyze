from __future__ import annotations

import html
import re
from typing import Any


RISK_FLAG_DESCRIPTIONS = {
    "PE_TTM_HIGH": "PE TTM 偏高，估值容错空间较低",
    "PB_HIGH": "PB 偏高，账面估值压力较大",
    "MA20_BELOW_MA60": "MA20 低于 MA60，中期均线结构偏弱",
    "RECENT_DRAWDOWN": "近20日回撤较大，短期波动风险上升",
    "NET_PROFIT_GROWTH_NEGATIVE": "归母净利润同比为负，盈利增长承压",
    "REVENUE_GROWTH_NEGATIVE": "营收同比为负，收入增长承压",
    "MONEYFLOW_5D_NEGATIVE": "近5日资金净流出，资金面偏弱",
    "MARKET_SENTIMENT_WEAK": "跌停样本多于涨停样本，市场情绪偏弱",
    "ANNOUNCEMENT_EVENT_RISK": "近期公告存在中高风险事件，需复核公告原文",
    "ASSET_LIABILITY_RATIO_HIGH": "资产负债率偏高，偿债压力需要复核",
    "INTEREST_BEARING_DEBT_ABOVE_CASH": "有息负债高于货币资金，债务覆盖需要复核",
    "GOODWILL_RATIO_HIGH": "商誉占资产比例偏高，需关注减值风险",
    "OPERATING_CASHFLOW_NEGATIVE": "经营现金流为负，现金创造能力偏弱",
    "FREE_CASHFLOW_NEGATIVE": "自由现金流为负，资本开支后现金流承压",
    "CASHFLOW_TO_PROFIT_WEAK": "经营现金流对归母净利润覆盖不足",
    "AT_LIMIT_UP": "收盘价接近或达到涨停价，短期波动可能放大",
    "NEAR_LIMIT_UP": "收盘价距涨停价较近，需关注追高波动",
    "AT_LIMIT_DOWN": "收盘价接近或达到跌停价，流动性和情绪风险较高",
    "NEAR_LIMIT_DOWN": "收盘价距跌停价较近，需关注下行波动",
}

DATA_GAP_DESCRIPTIONS = {
    "announcements_empty_or_unavailable": "公告接口未返回可用公告；可能是接口权限、数据覆盖或查询区间问题",
    "financials_empty_or_unavailable": "财报接口未返回可用财务数据",
    "moneyflow_empty_or_unavailable": "资金流接口未返回可用数据",
    "market_indices_empty_or_unavailable": "宽基指数接口未返回可用数据",
    "industry_index_mapping_not_configured": "尚未配置该股票对应的行业指数映射",
    "industry_index_unavailable": "已自动识别行业指数，但本次行业指数行情接口未返回可用数据",
    "limit_list_d_rate_limited": "Tushare 涨跌停情绪接口触发频率限制；后续同一交易日成功后会优先使用本地缓存",
}


def render_report(pack: dict[str, Any], scorecard: dict[str, Any], position: dict[str, Any] | None = None) -> str:
    symbol = pack["meta"]["symbol"]
    display_name = _stock_display_name(pack)
    trade_date = pack["meta"]["trade_date"]
    quote = pack["quote"]
    ind = pack["indicators"]
    scores = scorecard["scores"]
    position_lines = _position_lines(quote, position)
    position_status_section = (
        f"""
## 持仓状态判断

{_position_status_lines(pack, scorecard, position)}
"""
        if position
        else ""
    )
    position_volume_section = (
        f"""
## 持仓视角下的量价风险

{_position_volume_price_lines(pack, position)}
"""
        if position
        else ""
    )
    return f"""# {display_name}中文多维研究报告

## 核心结论

- **股票**：{display_name}
- **数据日期**：{trade_date}
- **综合评级**：{scorecard["rating"]}
- **综合分数**：{scores["total"]}/100
- **综合判断**：{_summary(pack, scorecard)}
- **评级说明**：{scorecard["rating_note"]}

### 数据依据

{_conclusion_basis_lines(pack, scorecard)}

## 多空证据表

{_evidence_table(scorecard)}

## 数据状态

- **数据源**：{pack["meta"]["source"]}
- **更新时间**：{pack["meta"]["as_of"]}
- **数据限制**：{pack["meta"]["data_delay_note"]}
- **追溯规则**：所有价格、成交量、均线和评分字段来自 `market_pack.json`。

## 关键证据

- **收盘价**：{quote.get("close")}
- **MA20**：{ind.get("ma20")}
- **MA60**：{ind.get("ma60")}
- **20日涨跌幅**：{ind.get("ret_20d_pct")}%
- **5日/20日量比**：{ind.get("vol_ratio_5_20")}
- **PE TTM**：{pack.get("fundamental", {}).get("pe_ttm")}
- **PB**：{pack.get("fundamental", {}).get("pb")}
- **营收同比**：{pack.get("fundamental", {}).get("revenue_growth_yoy")}%
- **归母净利润同比**：{pack.get("fundamental", {}).get("net_profit_growth_yoy")}%
- **资产负债率**：{pack.get("fundamental", {}).get("asset_liability_ratio")}
- **自由现金流**：{pack.get("fundamental", {}).get("free_cashflow")}
- **净现比**：{pack.get("fundamental", {}).get("operating_cashflow_to_net_profit")}
- **距涨停/跌停**：{quote.get("pct_to_limit_up")}% / {quote.get("pct_to_limit_down")}%
- **5日资金净流入**：{(pack.get("moneyflow") or {}).get("latest", {}).get("net_amount_5d")}

## 技术面分析

- **均线结构**：{_ma_structure(pack)}
- **趋势强弱**：{_trend_text(scorecard)}
- **短期位置**：20日高点 {ind.get("high_20")}，20日低点 {ind.get("low_20")}。

## 量价关系

{_volume_price_lines(pack)}

## 基本面与估值

- **财报摘要**：{_financial_text(pack)}
- **资产负债与现金流**：{_balance_cashflow_text(pack)}
- **估值评分**：{scores["valuation"]}/100
- **估值字段**：PE TTM={pack.get("fundamental", {}).get("pe_ttm")}，PB={pack.get("fundamental", {}).get("pb")}
- **说明**：若估值字段为空，表示当前数据源未返回该字段，不能用模型记忆补齐。

## 资金流分析

{_moneyflow_lines(pack)}

## 行业指数与市场环境

{_market_context_lines(pack)}

## 市场情绪与涨跌停结构

{_market_sentiment_lines(pack)}

{_limit_lines(pack)}

## 公告与事件风险

{_announcement_lines(pack)}

## 持仓风险快检

{position_lines}
{position_status_section}
{position_volume_section}

## 综合评分

- **趋势**：{scores["trend"]}/100
- **量价**：{scores["volume_price"]}/100
- **基本面**：{scores.get("fundamental")}/100
- **估值**：{scores["valuation"]}/100
- **资金流**：{scores.get("moneyflow")}/100
- **市场环境**：{scores.get("market_context")}/100
- **风险**：{scores["risk"]}/100
- **总分**：{scores["total"]}/100

## 主要风险

{_risk_lines(pack, include_code=False)}

## 观察条件

- **转强条件**：价格重新站上关键中期均线，且量能不低于20日均量。
- **转弱条件**：跌破近20日低点，或 MA20 继续低于 MA60 并扩大。
- **复核条件**：公告、财报、减持、解禁、行业政策变化后应重新生成数据包。

## 数据局限

- 本报告不是 tick 级实时行情。
- 本报告不输出目标价，不输出直接买入或卖出指令。
- 若数据源字段缺失，对应章节只做缺口说明，不做数值推断。

## 数据缺口

{_gap_lines(pack)}

## 免责声明

本报告仅用于学习研究和流程演示，不构成投资建议。市场有风险，决策需独立判断。
"""


def render_html_document(markdown_text: str, title: str) -> str:
    body = _markdown_to_html(markdown_text)
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --paper: #ffffff;
      --text: #1f2937;
      --muted: #64748b;
      --border: #d9e0ea;
      --accent: #0f766e;
      --soft: #eef7f6;
      --danger: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.72;
    }}
    main {{
      width: min(1080px, calc(100% - 32px));
      margin: 32px auto;
      padding: 36px 40px;
      background: var(--paper);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
    }}
    h1, h2, h3 {{ line-height: 1.28; margin: 28px 0 14px; }}
    h1 {{ margin-top: 0; font-size: 30px; color: #0f172a; }}
    h2 {{ padding-top: 12px; border-top: 1px solid var(--border); font-size: 22px; color: var(--accent); }}
    h3 {{ font-size: 18px; }}
    p {{ margin: 10px 0; }}
    ul {{ padding-left: 22px; margin: 10px 0 18px; }}
    li {{ margin: 6px 0; }}
    strong {{ color: #0f172a; }}
    code {{
      padding: 2px 6px;
      border-radius: 5px;
      background: #eef2f7;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 0.92em;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0 22px;
      font-size: 14px;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: var(--soft); color: #0f172a; }}
    .meta {{
      margin-bottom: 20px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 720px) {{
      main {{ width: 100%; margin: 0; padding: 24px 18px; border-radius: 0; border-left: 0; border-right: 0; }}
      h1 {{ font-size: 24px; }}
      h2 {{ font-size: 19px; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="meta">本 HTML 由项目生成，数值来源以同目录 <code>market_pack.json</code> 为准。</div>
{body}
  </main>
</body>
</html>
"""


def _markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    chunks: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []
    i = 0

    def flush_paragraph() -> None:
        if paragraph:
            chunks.append(f"    <p>{_inline_html(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_bullets() -> None:
        if bullets:
            chunks.append("    <ul>")
            chunks.extend(f"      <li>{item}</li>" for item in bullets)
            chunks.append("    </ul>")
            bullets.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            flush_paragraph()
            flush_bullets()
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            flush_paragraph()
            flush_bullets()
            table_lines = [line]
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i].rstrip())
                i += 1
            chunks.append(_table_html(table_lines))
            continue
        if line.startswith("#"):
            flush_paragraph()
            flush_bullets()
            level = min(len(line) - len(line.lstrip("#")), 3)
            text = line[level:].strip()
            chunks.append(f"    <h{level}>{_inline_html(text)}</h{level}>")
            i += 1
            continue
        if line.startswith("- "):
            flush_paragraph()
            bullets.append(_inline_html(line[2:].strip()))
            i += 1
            continue
        paragraph.append(line.strip())
        i += 1
    flush_paragraph()
    flush_bullets()
    return "\n".join(chunks)


def _inline_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and set(stripped.replace("|", "").replace(" ", "")) <= {"-", ":"}


def _table_html(lines: list[str]) -> str:
    rows = [_split_table_row(line) for line in lines]
    if not rows:
        return ""
    head = rows[0]
    body = rows[1:]
    parts = ["    <table>", "      <thead>", "        <tr>"]
    parts.extend(f"          <th>{_inline_html(cell)}</th>" for cell in head)
    parts.extend(["        </tr>", "      </thead>", "      <tbody>"])
    for row in body:
        parts.append("        <tr>")
        parts.extend(f"          <td>{_inline_html(cell)}</td>" for cell in row)
        parts.append("        </tr>")
    parts.extend(["      </tbody>", "    </table>"])
    return "\n".join(parts)


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_audit(pack: dict[str, Any], scorecard: dict[str, Any]) -> str:
    return f"""# 数据审计

## 数据状态

- **股票**：{_stock_display_name(pack)}
- **交易日**：{pack["meta"]["trade_date"]}
- **数据源**：{pack["meta"]["source"]}
- **日线数量**：{len(pack.get("daily_bars", []))}
- **公告数量**：{len(pack.get("announcements", []))}
- **数据缺口数量**：{len(pack.get("data_gaps", []))}

## 字段检查

- **quote.close**：{pack["quote"].get("close") is not None}
- **indicators.ma20**：{pack["indicators"].get("ma20") is not None}
- **indicators.ma60**：{pack["indicators"].get("ma60") is not None}
- **scorecard.total**：{scorecard["scores"].get("total") is not None}
- **fundamental.report_end_date**：{pack.get("fundamental", {}).get("report_end_date") is not None}
- **moneyflow.latest**：{bool((pack.get("moneyflow") or {}).get("latest"))}
- **market_context.indices**：{bool((pack.get("market_context") or {}).get("indices"))}
- **market_sentiment**：{bool(pack.get("market_sentiment")) and (pack.get("market_sentiment") or {}).get("data_quality") != "warning"}
- **announcements**：{bool(pack.get("announcements"))}

## 可选字段 warning

{_optional_warning_lines(pack)}

## 数据缺口

{_gap_lines(pack)}

## 风险标记

{_risk_lines(pack, include_code=True)}
"""


def render_dossier(pack: dict[str, Any], scorecard: dict[str, Any]) -> str:
    return f"""# 决策证据链

## 输入

- **股票**：{_stock_display_name(pack)}
- **交易日**：{pack["meta"]["trade_date"]}
- **请求模式**：{pack["request"]["mode"]}

## 证据

- **收盘价来源**：`daily_bars[-1].close`
- **均线来源**：`daily_bars.close` 滚动计算
- **量比来源**：`vol_ma5 / vol_ma20`
- **财报来源**：`provider.fetch_financials`
- **公告来源**：`provider.fetch_announcements`
- **资金流来源**：`provider.fetch_moneyflow`
- **指数与情绪来源**：`provider.fetch_market_context`
- **评分来源**：`scorecard.json`

## 结论

- **评级**：{scorecard["rating"]}
- **总分**：{scorecard["scores"]["total"]}/100
- **解释**：{_summary(pack, scorecard)}

## 禁止项检查

- **未输出目标价**：是
- **未输出直接买卖建议**：是
- **未使用模型记忆补行情**：是
"""


def render_watchlist_report(results: list[dict[str, Any]]) -> str:
    lines = ["# 观察池对比报告", "", "## 观察优先级排序", ""]
    ranked = sorted(results, key=lambda item: item["scorecard"]["scores"]["total"], reverse=True)
    lines.append(
        "| 股票 | 评级 | 总分 | 趋势 | 量价 | 基本面 | 估值 | 资金流 | 市场环境 | 风险 | 数据质量 |"
    )
    lines.append(
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
    )
    for item in ranked:
        sc = item["scorecard"]
        scores = sc["scores"]
        audit = (item.get("pack") or {}).get("data_audit") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _stock_display_name(item.get("pack") or {"meta": {"symbol": sc["symbol"]}}),
                    str(sc["rating"]),
                    _score_cell(scores.get("total")),
                    _score_cell(scores.get("trend")),
                    _score_cell(scores.get("volume_price")),
                    _score_cell(scores.get("fundamental")),
                    _score_cell(scores.get("valuation")),
                    _score_cell(scores.get("moneyflow")),
                    _score_cell(scores.get("market_context")),
                    _score_cell(scores.get("risk")),
                    _data_quality_text(audit),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 升级/降级理由", ""])
    for idx, item in enumerate(ranked, 1):
        sc = item["scorecard"]
        ev = sc.get("evidence") or {}
        lines.append(
            f"- **第 {idx} 位 {_stock_display_name(item.get('pack') or {'meta': {'symbol': sc['symbol']}})}**：{_watchlist_reason(sc, ev)}"
        )
    lines.extend(["", "## 核心结论", ""])
    for idx, item in enumerate(ranked, 1):
        sc = item["scorecard"]
        ev = sc.get("evidence") or {}
        flags = sc.get("risk_flags") or []
        lines.append(
            f"- **第 {idx} 档 {_stock_display_name(item.get('pack') or {'meta': {'symbol': sc['symbol']}})}**：评级 {sc['rating']}，总分 {sc['scores']['total']}/100，交易日 {sc['trade_date']}，"
            f"20日涨跌幅 {ev.get('ret_20d_pct')}%，5日资金净流入 {ev.get('moneyflow_net_amount_5d')}，风险标记 {len(flags)} 个。"
        )
    lines.extend(["", "## 量价强弱对比", ""])
    lines.append("| 股票 | 量价结论 | 置信度 | 量价分 | 5日/20日量比 | 20日涨跌幅 | 主要信号 |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | --- |")
    for item in ranked:
        pack = item.get("pack") or {}
        vp = pack.get("volume_price") or {}
        metrics = vp.get("metrics") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _stock_display_name(pack or {"meta": {"symbol": item["scorecard"]["symbol"]}}),
                    str(vp.get("verdict")),
                    str(vp.get("confidence")),
                    _score_cell(metrics.get("score")),
                    str(metrics.get("volume_ratio_5_20")),
                    str(metrics.get("price_change_20d")),
                    "、".join((vp.get("signals") or [])[:3]) or "暂无",
                ]
            )
            + " |"
        )
    lines.extend(["", "## 风险提示", "", "- 观察池报告只做横向研究排序，不构成买入推荐。", "- 如需单票详细证据，请查看各股票目录下的 `report.md` 和 `market_pack.json`。"])
    return "\n".join(lines) + "\n"


def _score_cell(value: Any) -> str:
    return "" if value is None else f"{value}/100"


def _data_quality_text(audit: dict[str, Any]) -> str:
    if not audit:
        return "未知"
    gaps = int(audit.get("data_gaps_count") or 0)
    if gaps == 0:
        return "完整"
    if gaps <= 2:
        return f"少量缺口({gaps})"
    return f"缺口较多({gaps})"


def _stock_display_name(pack: dict[str, Any]) -> str:
    meta = pack.get("meta") or {}
    symbol = meta.get("symbol") or ""
    name = meta.get("name")
    return f"{name}（{symbol}）" if name else str(symbol)


def _summary(pack: dict[str, Any], scorecard: dict[str, Any]) -> str:
    rating = scorecard["rating"]
    mapping = {
        "strong_watch": "明显偏强，重点跟踪。",
        "watch": "偏强，继续观察。",
        "neutral": "中性，等待确认。",
        "cautious": "偏弱，谨慎观察。",
        "avoid": "明显偏弱，优先规避风险。",
    }
    return mapping.get(rating, "中性，等待确认。")


def _conclusion_basis_lines(pack: dict[str, Any], scorecard: dict[str, Any]) -> str:
    ind = pack.get("indicators") or {}
    f = pack.get("fundamental") or {}
    vp = pack.get("volume_price") or {}
    metrics = vp.get("metrics") or {}
    money = ((pack.get("moneyflow") or {}).get("latest") or {})
    lines = [
        f"- **趋势结构**：收盘价 {pack.get('quote', {}).get('close')}，MA20={ind.get('ma20')}，MA60={ind.get('ma60')}，20日涨跌幅={ind.get('ret_20d_pct')}%。",
        f"- **量价关系**：结论 {vp.get('verdict')}，量价分={metrics.get('score')}，5日/20日量比={metrics.get('volume_ratio_5_20')}，20日涨跌幅={metrics.get('price_change_20d')}%。",
        f"- **基本面质量**：营收同比={f.get('revenue_growth_yoy')}%，归母净利润同比={f.get('net_profit_growth_yoy')}%，资产负债率={f.get('asset_liability_ratio')}。",
        f"- **估值位置**：PE TTM={f.get('pe_ttm')}，PB={f.get('pb')}。",
    ]
    if money:
        lines.append(f"- **资金流**：当日净流入={money.get('net_amount')}，5日净流入={money.get('net_amount_5d')}。")
    return "\n".join(lines[:5])


def _evidence_table(scorecard: dict[str, Any]) -> str:
    evidence = scorecard.get("evidence") or {}
    rows = [
        ("bullish_evidence", "偏多证据", evidence.get("bullish_evidence") or []),
        ("bearish_evidence", "偏空证据", evidence.get("bearish_evidence") or []),
        ("neutral_evidence", "中性证据", evidence.get("neutral_evidence") or []),
    ]
    lines = ["| 类型 | 字段 | 证据 |", "| --- | --- | --- |"]
    for key, label, items in rows:
        lines.append(f"| {label} | `{key}` | {'；'.join(items) if items else '暂无'} |")
    return "\n".join(lines)


def _watchlist_reason(scorecard: dict[str, Any], evidence: dict[str, Any]) -> str:
    rating = scorecard.get("rating")
    bullish = evidence.get("bullish_evidence") or []
    bearish = evidence.get("bearish_evidence") or []
    if rating in {"strong_watch", "watch"}:
        return f"优先级靠前，主要支撑为{'；'.join(bullish[:3]) or '总分相对靠前'}。"
    if rating in {"cautious", "avoid"}:
        return f"优先级靠后，主要拖累为{'；'.join(bearish[:3]) or '风险项或分项评分偏弱'}。"
    return "维持中性观察，等待趋势、量价或基本面证据进一步确认。"


def _ma_structure(pack: dict[str, Any]) -> str:
    close = pack["quote"]["close"]
    ind = pack["indicators"]
    above = [ma for ma in ["ma5", "ma10", "ma20", "ma60", "ma120"] if ind.get(ma) and close >= ind[ma]]
    below = [ma for ma in ["ma5", "ma10", "ma20", "ma60", "ma120"] if ind.get(ma) and close < ind[ma]]
    return f"收盘价位于 {', '.join(above) or '无'} 上方，位于 {', '.join(below) or '无'} 下方。"


def _trend_text(scorecard: dict[str, Any]) -> str:
    score = scorecard["scores"]["trend"]
    if score >= 70:
        return "趋势评分偏强。"
    if score >= 45:
        return "趋势评分中性。"
    return "趋势评分偏弱。"


def _volume_text(ind: dict[str, Any]) -> str:
    ratio = ind.get("vol_ratio_5_20")
    if ratio is None:
        return "量能数据不足。"
    if ratio >= 1.2:
        return "近5日成交量高于20日均量，资金活跃度提升。"
    if ratio < 0.7:
        return "近5日成交量低于20日均量，反弹或下跌的持续性需要观察。"
    return "近5日成交量接近20日均量，量能中性。"


def _volume_price_lines(pack: dict[str, Any]) -> str:
    vp = pack.get("volume_price") or {}
    metrics = vp.get("metrics") or {}
    signals = vp.get("signals") or []
    risks = vp.get("risks") or []
    basis = vp.get("data_basis") or []
    return "\n".join(
        [
            f"- **量价结论**：{vp.get('verdict')}，置信度 {vp.get('confidence')}，量价分 {metrics.get('score')}/100。",
            f"- **摘要**：{vp.get('summary')}",
            f"- **核心指标**：5日/20日量比={metrics.get('volume_ratio_5_20')}，5日/20日成交额比={metrics.get('amount_ratio_5_20')}，换手率={metrics.get('turnover_latest')}，换手率 z-score={metrics.get('turnover_zscore')}。",
            f"- **价格位置**：5日涨跌幅={metrics.get('price_change_5d')}%，20日涨跌幅={metrics.get('price_change_20d')}%，20日区间位置={metrics.get('close_position_in_range')}，量价相关={metrics.get('volume_price_corr_20d')}。",
            f"- **K线结构**：上影线比例={metrics.get('upper_shadow_ratio')}，下影线比例={metrics.get('lower_shadow_ratio')}。",
            f"- **识别信号**：{'、'.join(signals) if signals else '暂无强量价信号'}。",
            f"- **量价风险**：{'；'.join(risks) if risks else '暂无突出的量价风险'}",
            f"- **数据依据**：{'；'.join(basis)}。",
        ]
    )


def _position_volume_price_lines(pack: dict[str, Any], position: dict[str, Any] | None) -> str:
    vp = pack.get("volume_price") or {}
    signals = vp.get("signals") or []
    risks = vp.get("risks") or []
    if not position:
        return "- **状态**：用户未提供持仓成本，本节只展示通用量价风险。"
    cost = position.get("cost_price")
    close = (pack.get("quote") or {}).get("close")
    diff = round((close / cost - 1) * 100, 2) if cost and close else None
    return "\n".join(
        [
            f"- **相对成本位置**：当前收盘价相对成本 {diff}%。",
            f"- **量价结论**：{vp.get('verdict')}，置信度 {vp.get('confidence')}。",
            f"- **对持仓的含义**：{'、'.join(signals[:3]) if signals else '暂无明确量价强化信号'}。",
            f"- **需重点复核**：{'；'.join(risks) if risks else '暂无突出的量价风险'}。",
        ]
    )


def _position_status_lines(pack: dict[str, Any], scorecard: dict[str, Any], position: dict[str, Any] | None) -> str:
    if not position:
        return "- **状态**：未提供持仓信息。"
    cost = position.get("cost_price")
    close = (pack.get("quote") or {}).get("close")
    diff = round((close / cost - 1) * 100, 2) if cost and close else None
    rating = scorecard.get("rating")
    if diff is None:
        state = "成本或收盘价缺失，无法计算相对成本状态。"
    elif diff >= 8 and rating in {"strong_watch", "watch"}:
        state = "持仓处于盈利且结构偏强，重点观察趋势延续和量价风险。"
    elif diff >= 0:
        state = "持仓略有浮盈或接近成本，等待量价和趋势进一步确认。"
    elif rating in {"cautious", "avoid"}:
        state = "持仓浮亏且评级偏弱，需优先复核风险释放情况。"
    else:
        state = "持仓低于成本，但综合评级未明显恶化，继续观察关键证据变化。"
    return "\n".join(
        [
            f"- **相对成本状态**：当前收盘价相对成本 {diff}%。",
            f"- **综合评级约束**：{rating}，{_summary(pack, scorecard)}",
            f"- **状态判断**：{state}",
        ]
    )


def _financial_text(pack: dict[str, Any]) -> str:
    f = pack.get("fundamental") or {}
    if not any(f.get(k) is not None for k in ["revenue", "net_profit_parent", "revenue_growth_yoy", "net_profit_growth_yoy"]):
        return "财报字段缺失，已记录到数据缺口。"
    return (
        f"报告期 {f.get('report_end_date')}，公告日 {f.get('ann_date')}；"
        f"营收={f.get('revenue')}，归母净利润={f.get('net_profit_parent')}，"
        f"营收同比={f.get('revenue_growth_yoy')}%，归母净利润同比={f.get('net_profit_growth_yoy')}%，"
        f"ROE={f.get('roe')}。"
    )


def _balance_cashflow_text(pack: dict[str, Any]) -> str:
    f = pack.get("fundamental") or {}
    keys = [
        "asset_liability_ratio",
        "money_cap",
        "accounts_receiv",
        "inventories",
        "goodwill",
        "interest_bearing_debt",
        "operating_cashflow",
        "free_cashflow",
        "operating_cashflow_to_net_profit",
    ]
    if not any(f.get(key) is not None for key in keys):
        return "资产负债表或现金流量表扩展字段缺失，已记录到数据缺口。"
    return (
        f"资产负债率={f.get('asset_liability_ratio')}，货币资金={f.get('money_cap')}，"
        f"应收账款={f.get('accounts_receiv')}，存货={f.get('inventories')}，商誉={f.get('goodwill')}，"
        f"有息负债={f.get('interest_bearing_debt')}；经营现金流={f.get('operating_cashflow')}，"
        f"投资现金流={f.get('investing_cashflow')}，筹资现金流={f.get('financing_cashflow')}，"
        f"自由现金流={f.get('free_cashflow')}，净现比={f.get('operating_cashflow_to_net_profit')}。"
    )


def _moneyflow_lines(pack: dict[str, Any]) -> str:
    moneyflow = pack.get("moneyflow") or {}
    latest = moneyflow.get("latest") or {}
    if not latest:
        return "- **资金流**：数据源未返回资金流，已记录到数据缺口。"
    return "\n".join(
        [
            f"- **数据源**：{moneyflow.get('source')}",
            f"- **交易日**：{latest.get('trade_date')}",
            f"- **当日净流入**：{latest.get('net_amount')}",
            f"- **5日净流入**：{latest.get('net_amount_5d')}",
        ]
    )


def _market_context_lines(pack: dict[str, Any]) -> str:
    context = pack.get("market_context") or {}
    lines = [f"- **数据源**：{context.get('source')}"]
    indices = context.get("indices") or []
    if indices:
        for item in indices:
            lines.append(
                f"- **{item.get('name')}**：{item.get('trade_date')} 收盘 {item.get('close')}，涨跌幅 {item.get('pct_chg')}%"
            )
    else:
        lines.append("- **指数环境**：指数数据缺失，已记录到数据缺口。")
    industry = context.get("industry") or {}
    if industry.get("status") == "ok":
        lines.append(
            f"- **行业指数**：{industry.get('name')}（{industry.get('ts_code')}）{industry.get('trade_date')} 收盘 {industry.get('close')}，涨跌幅 {industry.get('pct_chg')}%"
        )
    elif industry.get("status") == "not_configured":
        lines.append(f"- **行业指数**：{industry.get('note') or '未配置行业指数映射。'}")
    elif industry.get("status") == "failed":
        label = f"{industry.get('name')}（{industry.get('ts_code')}）" if industry.get("ts_code") else "行业指数"
        lines.append(f"- **行业指数**：{label} 已识别；{industry.get('note') or '行业指数行情接口未返回数据。'}")
    sentiment = context.get("sentiment") or {}
    if sentiment:
        lines.append(
            f"- **市场情绪**：情绪标签 {sentiment.get('sentiment_label')}，情绪分 {sentiment.get('sentiment_score')}，来源 {sentiment.get('source')}。"
        )
    else:
        lines.append("- **市场情绪**：涨跌停情绪数据缺失，已记录到数据缺口。")
    return "\n".join(lines)


def _market_sentiment_lines(pack: dict[str, Any]) -> str:
    sentiment = pack.get("market_sentiment") or (pack.get("market_context") or {}).get("sentiment") or {}
    if not sentiment:
        return "- **状态**：市场情绪数据缺失，市场环境分项按中性降级。"
    lines = [
        f"- **交易日**：{sentiment.get('trade_date')}",
        f"- **涨停家数**：{sentiment.get('up_limit_count')}",
        f"- **跌停家数**：{sentiment.get('down_limit_count')}",
        f"- **炸板家数**：{sentiment.get('limit_break_count')}",
        f"- **炸板率**：{sentiment.get('limit_break_rate')}",
        f"- **最高连板**：{sentiment.get('highest_limit_step')}",
        f"- **情绪标签**：{sentiment.get('sentiment_label')}（{sentiment.get('sentiment_score')}/100）",
        f"- **数据来源**：{sentiment.get('source')}，数据质量 {sentiment.get('data_quality')}",
    ]
    warnings = sentiment.get("warnings") or []
    for item in warnings:
        message = item.get("message") or item.get("exception_message")
        if message:
            lines.append(f"- **局限**：{message}")
    return "\n".join(lines)


def _limit_lines(pack: dict[str, Any]) -> str:
    quote = pack.get("quote") or {}
    if quote.get("limit_up") is None and quote.get("limit_down") is None:
        return "- **个股涨跌停价**：`stk_limit` 未返回可用数据，已记录到数据缺口。"
    return "\n".join(
        [
            f"- **个股涨停价**：{quote.get('limit_up')}，距涨停 {quote.get('pct_to_limit_up')}%",
            f"- **个股跌停价**：{quote.get('limit_down')}，距跌停 {quote.get('pct_to_limit_down')}%",
        ]
    )


def _announcement_lines(pack: dict[str, Any]) -> str:
    announcements = pack.get("announcements") or []
    if not announcements:
        return "- **公告**：未获取到公告数据，已记录到数据缺口。"
    lines = []
    for item in announcements[:5]:
        title = item.get("title") or ""
        lines.append(f"- **{item.get('date')}**：{title}（{item.get('type') or '公告'}）")
    return "\n".join(lines)


def _risk_lines(pack: dict[str, Any], include_code: bool = False) -> str:
    flags = pack.get("risk_flags") or []
    if not flags:
        return "- **风险标记**：暂无自动风险标记。"
    lines = []
    for flag in flags:
        description = _risk_description(flag)
        if include_code:
            lines.append(f"- **{description}**（内部标记：`{flag}`）：需复核。")
        else:
            lines.append(f"- **{description}**：需复核。")
    return "\n".join(lines)


def _risk_description(flag: str) -> str:
    return RISK_FLAG_DESCRIPTIONS.get(flag, "未配置中文说明的风险标记")


def _gap_lines(pack: dict[str, Any]) -> str:
    gaps = pack.get("data_gaps") or []
    if not gaps:
        return "- **数据缺口**：暂无。"
    return "\n".join(f"- **{_gap_description(gap)}**：需复核或补充数据源权限。" for gap in gaps)


def _optional_warning_lines(pack: dict[str, Any]) -> str:
    warnings = ((pack.get("data_audit") or {}).get("optional_fields_missing") or [])
    if not warnings:
        return "- **可选字段**：暂无 warning。"
    return "\n".join(f"- **{item.get('field')}**：{item.get('message')}" for item in warnings)


def _gap_description(gap: str) -> str:
    if gap in DATA_GAP_DESCRIPTIONS:
        return DATA_GAP_DESCRIPTIONS[gap]
    if gap.startswith("sw_daily:") and gap.endswith("_rate_limited"):
        code = gap.removeprefix("sw_daily:").removesuffix("_rate_limited")
        return f"Tushare 申万行业指数接口 {code} 触发频率限制；后续同一交易日成功后会优先使用本地缓存"
    if gap.endswith("_permission_denied"):
        return f"{gap.removesuffix('_permission_denied')} 接口权限不足"
    if gap.endswith("_invalid_interface"):
        return f"{gap.removesuffix('_invalid_interface')} 接口名称不兼容或不可用"
    if gap.endswith("_rate_limited"):
        return f"{gap.removesuffix('_rate_limited')} 接口触发频率限制"
    return gap


def _position_lines(quote: dict[str, Any], position: dict[str, Any] | None) -> str:
    if not position:
        return "- **状态**：用户未提供持仓成本或仓位，本节仅保留。"
    cost = position.get("cost_price")
    if not cost:
        return "- **状态**：未识别成本价，无法计算相对成本风险。"
    close = quote["close"]
    diff = round((close / cost - 1) * 100, 2)
    return f"- **相对成本**：当前收盘价相对成本 {diff}%。\n- **说明**：该数值来自用户成本和 `market_pack.json` 收盘价计算。"

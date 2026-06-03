from __future__ import annotations

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
}


def render_report(pack: dict[str, Any], scorecard: dict[str, Any], position: dict[str, Any] | None = None) -> str:
    symbol = pack["meta"]["symbol"]
    trade_date = pack["meta"]["trade_date"]
    quote = pack["quote"]
    ind = pack["indicators"]
    scores = scorecard["scores"]
    position_lines = _position_lines(quote, position)
    return f"""# {symbol} 中文多维研究报告

## 核心结论

- **股票**：{symbol}
- **数据日期**：{trade_date}
- **综合评级**：{scorecard["rating"]}
- **综合分数**：{scores["total"]}/100
- **主要结论**：{_summary(pack, scorecard)}
- **评级说明**：{scorecard["rating_note"]}

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
- **5日资金净流入**：{(pack.get("moneyflow") or {}).get("latest", {}).get("net_amount_5d")}

## 技术面分析

- **均线结构**：{_ma_structure(pack)}
- **趋势强弱**：{_trend_text(scorecard)}
- **短期位置**：20日高点 {ind.get("high_20")}，20日低点 {ind.get("low_20")}。

## 量价关系

- **量能判断**：{_volume_text(ind)}
- **风险解释**：放量下跌或缩量反弹都需要降低结论置信度。

## 基本面与估值

- **财报摘要**：{_financial_text(pack)}
- **估值评分**：{scores["valuation"]}/100
- **估值字段**：PE TTM={pack.get("fundamental", {}).get("pe_ttm")}，PB={pack.get("fundamental", {}).get("pb")}
- **说明**：若估值字段为空，表示当前数据源未返回该字段，不能用模型记忆补齐。

## 资金流分析

{_moneyflow_lines(pack)}

## 行业指数与市场环境

{_market_context_lines(pack)}

## 公告与事件风险

{_announcement_lines(pack)}

## 持仓风险快检

{position_lines}

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

{_risk_lines(pack)}

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


def render_audit(pack: dict[str, Any], scorecard: dict[str, Any]) -> str:
    return f"""# 数据审计

## 数据状态

- **股票**：{pack["meta"]["symbol"]}
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
- **announcements**：{bool(pack.get("announcements"))}

## 数据缺口

{_gap_lines(pack)}

## 风险标记

{_risk_lines(pack)}
"""


def render_dossier(pack: dict[str, Any], scorecard: dict[str, Any]) -> str:
    return f"""# 决策证据链

## 输入

- **股票**：{pack["meta"]["symbol"]}
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
    lines = ["# 观察池对比报告", "", "## 横向对比", ""]
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
                    str(sc["symbol"]),
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
    lines.extend(["", "## 核心结论", ""])
    for idx, item in enumerate(ranked, 1):
        sc = item["scorecard"]
        ev = sc.get("evidence") or {}
        flags = sc.get("risk_flags") or []
        lines.append(
            f"- **第 {idx} 档 {sc['symbol']}**：评级 {sc['rating']}，总分 {sc['scores']['total']}/100，交易日 {sc['trade_date']}，"
            f"20日涨跌幅 {ev.get('ret_20d_pct')}%，5日资金净流入 {ev.get('moneyflow_net_amount_5d')}，风险标记 {len(flags)} 个。"
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


def _summary(pack: dict[str, Any], scorecard: dict[str, Any]) -> str:
    rating = scorecard["rating"]
    if rating == "watch":
        return "结构相对较好，可继续观察，但仍需等待数据和风险复核。"
    if rating == "neutral":
        return "多空证据不充分，适合保持中性观察，不宜基于单一信号行动。"
    return "风险证据较多或趋势偏弱，应优先控制风险并等待结构改善。"


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
    if industry.get("status") == "not_configured":
        lines.append(f"- **行业指数**：{industry.get('note') or '未配置行业指数映射。'}")
    sentiment = context.get("sentiment") or {}
    if sentiment:
        lines.append(
            f"- **市场情绪**：涨停样本 {sentiment.get('limit_up_count')}，跌停样本 {sentiment.get('limit_down_count')}，样本数 {sentiment.get('sample_size')}。"
        )
    else:
        lines.append("- **市场情绪**：涨跌停情绪数据缺失，已记录到数据缺口。")
    return "\n".join(lines)


def _announcement_lines(pack: dict[str, Any]) -> str:
    announcements = pack.get("announcements") or []
    if not announcements:
        return "- **公告**：未获取到公告数据，已记录到数据缺口。"
    lines = []
    for item in announcements[:5]:
        title = item.get("title") or ""
        lines.append(f"- **{item.get('date')}**：{title}（{item.get('type') or '公告'}）")
    return "\n".join(lines)


def _risk_lines(pack: dict[str, Any]) -> str:
    flags = pack.get("risk_flags") or []
    if not flags:
        return "- **风险标记**：暂无自动风险标记。"
    return "\n".join(f"- **{_risk_description(flag)}**（风险码：`{flag}`）：需复核。" for flag in flags)


def _risk_description(flag: str) -> str:
    return RISK_FLAG_DESCRIPTIONS.get(flag, "未配置中文说明的风险标记")


def _gap_lines(pack: dict[str, Any]) -> str:
    gaps = pack.get("data_gaps") or []
    if not gaps:
        return "- **数据缺口**：暂无。"
    return "\n".join(f"- **{gap}**：需复核或补充数据源权限。" for gap in gaps)


def _position_lines(quote: dict[str, Any], position: dict[str, Any] | None) -> str:
    if not position:
        return "- **状态**：用户未提供持仓成本或仓位，本节仅保留。"
    cost = position.get("cost_price")
    if not cost:
        return "- **状态**：未识别成本价，无法计算相对成本风险。"
    close = quote["close"]
    diff = round((close / cost - 1) * 100, 2)
    return f"- **相对成本**：当前收盘价相对成本 {diff}%。\n- **说明**：该数值来自用户成本和 `market_pack.json` 收盘价计算。"

from __future__ import annotations

from typing import Any


def analyze_market_regime(
    market_context: dict[str, Any],
    market_sentiment: dict[str, Any],
    data_gaps: list[str],
) -> dict[str, Any]:
    indices = market_context.get("indices") or []
    if not indices:
        data_gaps.append("index_daily_missing")
    data_gaps.append("index_dailybasic_missing")
    data_gaps.append("moneyflow_hsgt_missing")

    index_rows: dict[str, Any] = {}
    positive = 0
    negative = 0
    for item in indices:
        pct = _num(item.get("pct_chg"))
        if pct is not None and pct > 0:
            positive += 1
        elif pct is not None and pct < 0:
            negative += 1
        name = item.get("name") or item.get("ts_code") or "指数"
        index_rows[str(name)] = {
            "trade_date": item.get("trade_date"),
            "close": item.get("close"),
            "pct_chg": pct,
            "above_ma20": None,
            "above_ma60": None,
            "ma20_above_ma60": None,
            "return_5d": None,
            "return_20d": pct,
            "return_60d": None,
            "max_drawdown20": None,
            "max_drawdown60": None,
        }

    up = _num(market_sentiment.get("up_limit_count"))
    down = _num(market_sentiment.get("down_limit_count"))
    breaks = _num(market_sentiment.get("limit_break_count"))
    break_rate = _num(market_sentiment.get("limit_break_rate"))
    ratio = round(up / down, 4) if up is not None and down not in (None, 0) else None
    score = 50
    score += min(20, positive * 5)
    score -= min(20, negative * 5)
    if up is not None and down is not None:
        score += 12 if up > down * 1.5 else -12 if down > up else 0
    if break_rate is not None:
        score -= 8 if break_rate >= 0.35 else 0
    score = int(max(0, min(100, round(score))))
    stage = "risk_on" if score >= 65 else "risk_off" if score < 42 else "neutral"
    verdict = _verdict(score)
    risks = []
    if stage == "risk_off":
        risks.append("大盘处于 risk_off，整体风险偏好较低。")
    if down is not None and up is not None and down > up:
        risks.append("跌停数高于涨停数，市场情绪偏弱。")
    return {
        "verdict": verdict,
        "stage": stage,
        "score": score,
        "confidence": "medium" if indices and market_sentiment else "low",
        "indices": index_rows,
        "breadth": {"positive_indices": positive, "negative_indices": negative, "sample_size": len(indices)},
        "sentiment": {
            "up_limit_count": up,
            "down_limit_count": down,
            "limit_break_count": breaks,
            "limit_break_rate": break_rate,
            "up_down_limit_ratio": ratio,
        },
        "northbound": {"net_inflow_1d": None, "net_inflow_5d": None, "net_inflow_20d": None},
        "risks": risks,
        "evidence": [f"主要指数上涨数量={positive}，下跌数量={negative}", f"涨停数={up}，跌停数={down}"],
    }


def _verdict(score: int) -> str:
    if score >= 78:
        return "偏强"
    if score >= 64:
        return "中性偏强"
    if score >= 48:
        return "中性"
    if score >= 35:
        return "中性偏弱"
    return "偏弱"


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

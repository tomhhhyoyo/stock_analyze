from __future__ import annotations

from typing import Any


def analyze_sector_context(
    market_context: dict[str, Any],
    daily_bars: list[dict[str, Any]],
    indicators: dict[str, Any],
    data_gaps: list[str],
) -> dict[str, Any]:
    industry = market_context.get("industry") or {}
    if industry.get("status") != "ok":
        data_gaps.append("sector_index_missing")
    data_gaps.append("sector_member_missing")
    data_gaps.append("sector_sentiment_missing")

    sector_ret20 = _num(industry.get("pct_chg"))
    stock_ret20 = _num(indicators.get("ret_20d_pct"))
    excess = round(stock_ret20 - sector_ret20, 4) if stock_ret20 is not None and sector_ret20 is not None else None
    outperformed = excess is not None and excess >= 3
    underperformed = excess is not None and excess <= -3
    close = _num(industry.get("close"))
    score = 50
    if sector_ret20 is not None:
        score += 15 if sector_ret20 > 3 else -15 if sector_ret20 < -3 else 0
    if excess is not None:
        score += 8 if excess > 0 else -8 if excess < 0 else 0
    score = int(max(0, min(100, round(score))))
    stage = _stage(score, sector_ret20)
    verdict = _verdict(score)
    evidence = []
    if industry.get("name"):
        evidence.append(f"所属行业={industry.get('name')}（{industry.get('ts_code')}）")
    if sector_ret20 is not None:
        evidence.append(f"板块涨跌幅={sector_ret20}%")
    if excess is not None:
        evidence.append(f"个股20日超额收益={excess}%")
    risks = []
    if stage == "退潮":
        risks.append("板块阶段为退潮，需降低个股进攻性假设。")
    if underperformed:
        risks.append("个股明显跑输所属板块，弱于行业表现。")
    return {
        "sector_name": industry.get("name") or "",
        "sector_code": industry.get("ts_code") or "",
        "verdict": verdict,
        "stage": stage,
        "score": score,
        "confidence": "medium" if industry.get("status") == "ok" else "low",
        "sector_trend": {
            "close": close,
            "ma20": None,
            "ma60": None,
            "close_above_ma20": None,
            "close_above_ma60": None,
            "ma20_above_ma60": None,
            "return_5d": None,
            "return_20d": sector_ret20,
            "return_60d": None,
        },
        "sector_position": {"price_percentile_250d": None, "price_percentile_120d": None, "max_drawdown20": None},
        "sector_sentiment": {"up_limit_count": None, "down_limit_count": None, "limit_break_count": None, "limit_break_rate": None},
        "relative_strength": {
            "stock_return_20d": stock_ret20,
            "sector_return_20d": sector_ret20,
            "excess_return_20d": excess,
            "outperformed_sector": outperformed,
            "underperformed_sector": underperformed,
        },
        "stock_vs_sector": {
            "stock_return_20d": stock_ret20,
            "sector_return_20d": sector_ret20,
            "excess_return_20d": excess,
        },
        "risks": risks,
        "evidence": evidence,
    }


def _stage(score: int, ret20: float | None) -> str:
    if score >= 68:
        return "主升"
    if ret20 is not None and ret20 > 0:
        return "修复"
    if score < 42:
        return "退潮"
    return "无明显趋势"


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

from __future__ import annotations

from typing import Any

from .ratings import clamp_rating, rating_label, shift_rating


def apply_regime_adjustment(pack: dict[str, Any], scorecard: dict[str, Any]) -> dict[str, Any]:
    before = scorecard.get("rating_code") or scorecard.get("rating") or "neutral"
    code = before
    adjustments: list[dict[str, Any]] = []
    market = pack.get("market_regime") or {}
    sector = pack.get("sector_context") or {}
    volume = pack.get("volume_price") or {}
    money = ((pack.get("moneyflow") or {}).get("latest") or {})
    if not market:
        adjustments.append({"type": "data_gap", "message": "market_regime 缺失，未做大盘修正。"})
    if not sector:
        adjustments.append({"type": "data_gap", "message": "sector_context 缺失，未做板块修正。"})
    if market.get("stage") == "risk_off":
        limited = clamp_rating(code, "watch")
        if limited != code:
            adjustments.append({"type": "cap", "message": "大盘 risk_off，最终评级最高不超过中性偏强，继续观察。", "from": code, "to": limited})
            code = limited
        sent = market.get("sentiment") or {}
        up = sent.get("up_limit_count") or 0
        down = sent.get("down_limit_count") or 0
        if down > up:
            lowered = shift_rating(code, -1)
            adjustments.append({"type": "downgrade", "message": "大盘 risk_off 且跌停数高于涨停数，评级下调一档。", "from": code, "to": lowered})
            code = lowered
    if sector.get("stage") == "退潮":
        max_code = "watch" if ((sector.get("relative_strength") or {}).get("outperformed_sector")) else "neutral"
        limited = clamp_rating(code, max_code)
        if limited != code:
            adjustments.append({"type": "cap", "message": f"板块退潮，最终评级最高不超过{rating_label(max_code)}。", "from": code, "to": limited})
            code = limited
        signals = set(volume.get("signals") or [])
        if signals & {"放量下跌", "高位放量滞涨", "放量长上影"}:
            lowered = shift_rating(code, -1)
            adjustments.append({"type": "downgrade", "message": "板块退潮叠加量价恶化信号，评级下调一档。", "from": code, "to": lowered})
            code = lowered
    if (
        market.get("stage") == "risk_on"
        and sector.get("stage") == "主升"
        and volume.get("verdict") in {"偏强", "中性偏强"}
        and (money.get("net_amount_5d") is None or money.get("net_amount_5d") >= 0)
    ):
        raised = shift_rating(code, 1)
        if raised != code:
            adjustments.append({"type": "upgrade", "message": "大盘偏强、板块主升且量价偏强，评级上调一档。", "from": code, "to": raised})
            code = raised
    evidence = scorecard.get("evidence") or {}
    bullish = list(evidence.get("bullish_evidence") or [])
    bearish = list(evidence.get("bearish_evidence") or [])
    neutral = list(evidence.get("neutral_evidence") or [])
    rel = sector.get("relative_strength") or {}
    if rel.get("outperformed_sector"):
        bullish.append("个股明显跑赢所属板块，具备相对强势")
    if rel.get("underperformed_sector"):
        bearish.append("个股明显跑输所属板块，弱于行业表现")
    result = dict(scorecard)
    result["rating_code_before_adjustment"] = before
    result["rating_label_before_adjustment"] = rating_label(before)
    result["rating_code"] = code
    result["rating_label"] = rating_label(code)
    result["rating"] = rating_label(code)
    result["rating_adjustments"] = adjustments
    result["bullish_evidence"] = bullish[:8]
    result["bearish_evidence"] = bearish[:8]
    result["neutral_evidence"] = neutral[:8]
    result["evidence"] = {**evidence, "bullish_evidence": bullish[:8], "bearish_evidence": bearish[:8], "neutral_evidence": neutral[:8]}
    return result

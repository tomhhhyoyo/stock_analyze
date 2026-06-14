from __future__ import annotations

import math
from typing import Any

VERDICT_SCORE = {
    "偏强": 82,
    "中性偏强": 68,
    "中性": 55,
    "中性偏弱": 42,
    "偏弱": 28,
}


def analyze_volume_price(
    daily_bars: list[dict[str, Any]],
    basic: dict[str, Any],
    moneyflow: dict[str, Any],
    market_sentiment: dict[str, Any],
    data_gaps: list[str],
) -> dict[str, Any]:
    if len(daily_bars) < 20:
        data_gaps.append("volume_price_insufficient_daily_bars")
        return _empty_result("样本少于 20 个交易日，量价关系只保留缺口记录。")

    prices = [_price(row, "close") for row in daily_bars]
    opens = [_price(row, "open") for row in daily_bars]
    highs = [_price(row, "high") for row in daily_bars]
    lows = [_price(row, "low") for row in daily_bars]
    volumes = [_num(row.get("volume")) for row in daily_bars]
    amounts = [_num(row.get("amount")) for row in daily_bars]
    turnovers = [_num(row.get("turnover_rate")) for row in daily_bars]

    if not any(row.get("qfq_close") is not None for row in daily_bars):
        data_gaps.append("volume_price_adj_factor_missing_using_raw_price")
    if not any(row.get("limit_up") is not None and row.get("limit_down") is not None for row in daily_bars):
        data_gaps.append("volume_price_stk_limit_missing")
    if not (moneyflow.get("latest") or {}):
        data_gaps.append("volume_price_moneyflow_missing")
    if not market_sentiment:
        data_gaps.append("volume_price_limit_sentiment_missing")

    latest = daily_bars[-1]
    close = prices[-1]
    open_ = opens[-1]
    high = highs[-1]
    low = lows[-1]
    volume = volumes[-1]

    metrics = {
        "vol_ma5": _ma(volumes, 5),
        "vol_ma20": _ma(volumes, 20),
        "amount_ma5": _ma(amounts, 5),
        "amount_ma20": _ma(amounts, 20),
        "volume_ratio_5_20": _ratio(_ma(volumes, 5), _ma(volumes, 20)),
        "amount_ratio_5_20": _ratio(_ma(amounts, 5), _ma(amounts, 20)),
        "turnover_latest": _last_present(turnovers) or basic.get("turnover_rate"),
        "turnover_ma20": _ma(turnovers, 20),
        "turnover_zscore": _zscore(turnovers, 20),
        "price_change_5d": _pct_change(prices, 5),
        "price_change_20d": _pct_change(prices, 20),
        "volume_price_corr_20d": _corr(_pct_series(prices[-21:]), volumes[-20:]) if len(prices) >= 21 else None,
        "close_position_in_range": _close_position(close, max(highs[-20:]), min(lows[-20:])),
        "upper_shadow_ratio": _upper_shadow(open_, high, close, low),
        "lower_shadow_ratio": _lower_shadow(open_, high, close, low),
        "daily_basic_volume_ratio": latest.get("volume_ratio") or basic.get("volume_ratio"),
        "limit_up": latest.get("limit_up"),
        "limit_down": latest.get("limit_down"),
        "moneyflow_net_amount_5d": ((moneyflow.get("latest") or {}).get("net_amount_5d")),
        "market_limit_up_count": market_sentiment.get("up_limit_count"),
        "market_limit_down_count": market_sentiment.get("down_limit_count"),
        "market_limit_break_count": market_sentiment.get("limit_break_count"),
    }
    metrics["score"] = _score(metrics, close, prices, volume, volumes)
    verdict = _verdict(metrics["score"])
    signals = _signals(metrics, close, prices, volume, volumes)
    risks = _risks(metrics, signals)
    confidence = _confidence(metrics, moneyflow, market_sentiment)
    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": _summary(verdict, signals, risks),
        "metrics": metrics,
        "signals": signals,
        "risks": risks,
        "data_basis": [
            "daily_bars.open/high/low/close/volume/amount",
            "daily_bars.qfq_open/qfq_high/qfq_low/qfq_close with raw price fallback",
            "daily_bars.turnover_rate/turnover_rate_f/volume_ratio from daily_basic",
            "moneyflow.latest.net_amount/net_amount_5d",
            "quote/daily_bars.limit_up/limit_down from stk_limit",
            "market_sentiment limit_list_d/akshare limit pool fallback",
        ],
    }


def _empty_result(summary: str) -> dict[str, Any]:
    return {
        "verdict": "中性",
        "confidence": "low",
        "summary": summary,
        "metrics": {"score": 50},
        "signals": [],
        "risks": ["样本不足，量价结论置信度低。"],
        "data_basis": ["daily_bars"],
    }


def _score(metrics: dict[str, Any], close: float | None, prices: list[float | None], volume: float | None, volumes: list[float | None]) -> int:
    score = 55
    ret5 = metrics.get("price_change_5d")
    ret20 = metrics.get("price_change_20d")
    vr = metrics.get("volume_ratio_5_20")
    ar = metrics.get("amount_ratio_5_20")
    pos = metrics.get("close_position_in_range")
    corr = metrics.get("volume_price_corr_20d")
    upper = metrics.get("upper_shadow_ratio")
    net5 = metrics.get("moneyflow_net_amount_5d")
    if ret5 is not None:
        score += 8 if ret5 > 3 else -8 if ret5 < -3 else 0
    if ret20 is not None:
        score += 10 if ret20 > 5 else -10 if ret20 < -6 else 0
    if vr is not None:
        score += 9 if vr >= 1.25 and (ret5 or 0) > 0 else -9 if vr >= 1.25 and (ret5 or 0) < 0 else -4 if vr < 0.7 else 0
    if ar is not None:
        score += 5 if ar >= 1.2 and (ret5 or 0) > 0 else -5 if ar >= 1.2 and (ret5 or 0) < 0 else 0
    if pos is not None:
        score += 8 if pos >= 0.75 else -8 if pos <= 0.25 else 0
    if corr is not None:
        score += 5 if corr >= 0.25 else -5 if corr <= -0.25 else 0
    if upper is not None and upper >= 0.45 and vr is not None and vr >= 1.2:
        score -= 10
    if net5 is not None:
        score += 5 if net5 > 0 else -5 if net5 < 0 else 0
    return int(max(0, min(100, round(score))))


def _signals(metrics: dict[str, Any], close: float | None, prices: list[float | None], volume: float | None, volumes: list[float | None]) -> list[str]:
    signals: list[str] = []
    ret5 = metrics.get("price_change_5d") or 0
    ret20 = metrics.get("price_change_20d") or 0
    vr = metrics.get("volume_ratio_5_20") or 0
    ar = metrics.get("amount_ratio_5_20") or 0
    pos = metrics.get("close_position_in_range")
    upper = metrics.get("upper_shadow_ratio") or 0
    recent_high = max(v for v in prices[-20:] if v is not None)
    prev_high = max(v for v in prices[-21:-1] if v is not None) if len(prices) >= 21 else recent_high
    recent_vol_high = max(v for v in volumes[-20:] if v is not None)
    prev_vol_high = max(v for v in volumes[-21:-1] if v is not None) if len(volumes) >= 21 else recent_vol_high
    if ret5 > 2 and vr >= 1.2:
        signals.append("放量上涨")
    if ret5 > 1 and vr < 0.85:
        signals.append("缩量上涨")
    if ret5 < -2 and vr >= 1.2:
        signals.append("放量下跌")
    if ret5 < -1 and vr < 0.85:
        signals.append("缩量下跌")
    if close is not None and close >= prev_high and vr >= 1.2:
        signals.append("放量突破")
    if ret5 > 0 and ret20 <= 0 and vr < 0.9:
        signals.append("缩量反弹")
    if pos is not None and pos >= 0.75 and vr >= 1.2 and abs(ret5) < 1.5:
        signals.append("高位放量滞涨")
    if pos is not None and pos <= 0.3 and ret5 >= 0 and vr >= 1.2:
        signals.append("低位放量止跌")
    if close is not None and close >= prev_high and volume is not None and volume < prev_vol_high:
        signals.append("价格创新高但成交量未创新高")
    if upper >= 0.45 and vr >= 1.2:
        signals.append("放量长上影")
    if ret5 < 0 and vr < 0.85:
        signals.append("缩量回调")
    return list(dict.fromkeys(signals))


def _risks(metrics: dict[str, Any], signals: list[str]) -> list[str]:
    risks = []
    if "放量下跌" in signals:
        risks.append("放量下跌显示抛压放大。")
    if "高位放量滞涨" in signals:
        risks.append("高位放量但价格推进不足，需防止筹码松动。")
    if "放量长上影" in signals:
        risks.append("长上影叠加放量，盘中冲高回落压力较明显。")
    if metrics.get("turnover_zscore") is not None and metrics["turnover_zscore"] >= 2:
        risks.append("换手率显著高于 20 日均值，短线波动可能放大。")
    return risks


def _summary(verdict: str, signals: list[str], risks: list[str]) -> str:
    sig = "、".join(signals[:3]) if signals else "暂无强信号"
    risk = "；".join(risks[:2]) if risks else "未识别到突出的量价风险"
    return f"量价结论为{verdict}，主要信号：{sig}；风险提示：{risk}。"


def _confidence(metrics: dict[str, Any], moneyflow: dict[str, Any], market_sentiment: dict[str, Any]) -> str:
    present = sum(1 for key in ["volume_ratio_5_20", "amount_ratio_5_20", "turnover_latest", "volume_price_corr_20d"] if metrics.get(key) is not None)
    if moneyflow.get("latest"):
        present += 1
    if market_sentiment:
        present += 1
    return "high" if present >= 5 else "medium" if present >= 3 else "low"


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


def _price(row: dict[str, Any], field: str) -> float | None:
    return _num(row.get(f"qfq_{field}")) if row.get(f"qfq_{field}") is not None else _num(row.get(field))


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(value)
        if math.isnan(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _ma(values: list[float | None], window: int) -> float | None:
    sample = [v for v in values[-window:] if v is not None]
    if len(sample) < window:
        return None
    return round(sum(sample) / window, 4)


def _ratio(left: float | None, right: float | None) -> float | None:
    if left is None or right in (None, 0):
        return None
    return round(left / right, 4)


def _pct_change(values: list[float | None], days: int) -> float | None:
    if len(values) <= days or values[-days - 1] in (None, 0) or values[-1] is None:
        return None
    return round((values[-1] / values[-days - 1] - 1) * 100, 4)


def _pct_series(values: list[float | None]) -> list[float | None]:
    result = []
    for idx in range(1, len(values)):
        if values[idx - 1] in (None, 0) or values[idx] is None:
            result.append(None)
        else:
            result.append((values[idx] / values[idx - 1] - 1) * 100)
    return result


def _corr(left: list[float | None], right: list[float | None]) -> float | None:
    pairs = [(a, b) for a, b in zip(left, right) if a is not None and b is not None]
    if len(pairs) < 5:
        return None
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return round(num / (den_x * den_y), 4)


def _zscore(values: list[float | None], window: int) -> float | None:
    sample = [v for v in values[-window:] if v is not None]
    latest = _last_present(values)
    if len(sample) < window or latest is None:
        return None
    mean = sum(sample) / window
    variance = sum((v - mean) ** 2 for v in sample) / window
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return round((latest - mean) / std, 4)


def _last_present(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _close_position(close: float | None, high: float | None, low: float | None) -> float | None:
    if close is None or high is None or low is None or high == low:
        return None
    return round((close - low) / (high - low), 4)


def _upper_shadow(open_: float | None, high: float | None, close: float | None, low: float | None) -> float | None:
    if None in (open_, high, close, low) or high == low:
        return None
    return round((high - max(open_, close)) / (high - low), 4)


def _lower_shadow(open_: float | None, high: float | None, close: float | None, low: float | None) -> float | None:
    if None in (open_, high, close, low) or high == low:
        return None
    return round((min(open_, close) - low) / (high - low), 4)

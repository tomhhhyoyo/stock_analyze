from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_SCORING_CONFIG = {
    "weights": {
        "trend": 0.3,
        "volume_price": 0.15,
        "fundamental": 0.15,
        "valuation": 0.15,
        "moneyflow": 0.1,
        "market_context": 0.05,
        "risk": 0.1,
    },
    "rating_thresholds": {"watch": 72, "neutral": 50},
    "risk_penalty_per_flag": 12,
    "gap_penalty": {"critical": 6, "warning": 3, "info": 1},
}


def build_scorecard(pack: dict[str, Any]) -> dict[str, Any]:
    config = load_scoring_config()
    weights = config["weights"]
    quote = pack["quote"]
    ind = pack["indicators"]
    risk_flags = pack.get("risk_flags", [])
    trend_score = _trend_score(quote, ind)
    volume_score = _volume_score(ind)
    fundamental_score = _fundamental_score(pack.get("fundamental") or {})
    valuation_score = _valuation_score(pack.get("fundamental") or {})
    moneyflow_score = _moneyflow_score(pack.get("moneyflow") or {})
    market_score = _market_score(pack.get("market_context") or {})
    risk_score = max(
        0,
        100
        - len(risk_flags) * int(config.get("risk_penalty_per_flag", 12))
        - _gap_penalty(pack.get("data_gaps") or [], config.get("gap_penalty") or {}),
    )
    total = round(
        trend_score * weights["trend"]
        + volume_score * weights["volume_price"]
        + fundamental_score * weights["fundamental"]
        + valuation_score * weights["valuation"]
        + moneyflow_score * weights["moneyflow"]
        + market_score * weights["market_context"]
        + risk_score * weights["risk"],
        1,
    )
    thresholds = config.get("rating_thresholds") or {}
    rating = "watch" if total >= thresholds.get("watch", 72) else "neutral" if total >= thresholds.get("neutral", 50) else "avoid"
    return {
        "symbol": pack["meta"]["symbol"],
        "trade_date": pack["meta"]["trade_date"],
        "scores": {
            "trend": trend_score,
            "volume_price": volume_score,
            "fundamental": fundamental_score,
            "valuation": valuation_score,
            "moneyflow": moneyflow_score,
            "market_context": market_score,
            "risk": risk_score,
            "total": total,
        },
        "rating": rating,
        "rating_note": "评级仅表示研究观察优先级，不代表买入或卖出建议。",
        "scoring_config": config,
        "risk_flags": risk_flags,
        "evidence": _evidence(pack),
    }


def _trend_score(quote: dict[str, Any], ind: dict[str, Any]) -> int:
    close = quote["close"]
    score = 50
    for ma, weight in [("ma5", 8), ("ma10", 8), ("ma20", 12), ("ma60", 14), ("ma120", 10)]:
        value = ind.get(ma)
        if value is None:
            continue
        score += weight if close >= value else -weight
    if ind.get("ret_20d_pct") is not None:
        score += 8 if ind["ret_20d_pct"] > 5 else -8 if ind["ret_20d_pct"] < -8 else 0
    return _clamp(score)


def _volume_score(ind: dict[str, Any]) -> int:
    ratio = ind.get("vol_ratio_5_20")
    ret20 = ind.get("ret_20d_pct")
    if ratio is None:
        return 50
    score = 50
    if ratio >= 1.2 and (ret20 or 0) > 0:
        score += 25
    elif ratio >= 1.2 and (ret20 or 0) < 0:
        score -= 20
    elif ratio < 0.7:
        score -= 10
    return _clamp(score)


def _valuation_score(fundamental: dict[str, Any]) -> int:
    pe = fundamental.get("pe_ttm")
    pb = fundamental.get("pb")
    score = 60
    if pe is not None:
        score += 10 if 0 < pe <= 25 else -15 if pe > 60 or pe <= 0 else 0
    if pb is not None:
        score += 8 if 0 < pb <= 3 else -12 if pb > 8 or pb <= 0 else 0
    return _clamp(score)


def _fundamental_score(fundamental: dict[str, Any]) -> int:
    score = 55
    revenue_growth = fundamental.get("revenue_growth_yoy")
    profit_growth = fundamental.get("net_profit_growth_yoy")
    roe = fundamental.get("roe") or fundamental.get("roe_dt")
    if revenue_growth is not None:
        score += 12 if revenue_growth > 5 else -10 if revenue_growth < 0 else 0
    if profit_growth is not None:
        score += 15 if profit_growth > 10 else -15 if profit_growth < 0 else 0
    if roe is not None:
        score += 10 if roe >= 10 else -8 if roe < 5 else 0
    return _clamp(score)


def _moneyflow_score(moneyflow: dict[str, Any]) -> int:
    latest = moneyflow.get("latest") or {}
    net_5d = latest.get("net_amount_5d")
    if net_5d is None:
        return 50
    return _clamp(65 if net_5d > 0 else 35 if net_5d < 0 else 50)


def _market_score(market_context: dict[str, Any]) -> int:
    indices = market_context.get("indices") or []
    if not indices:
        return 50
    values = [item.get("pct_chg") for item in indices if item.get("pct_chg") is not None]
    if not values:
        return 50
    avg = sum(values) / len(values)
    return _clamp(65 if avg > 0.5 else 35 if avg < -0.5 else 50)


def _evidence(pack: dict[str, Any]) -> dict[str, Any]:
    ind = pack["indicators"]
    quote = pack["quote"]
    return {
        "close": quote.get("close"),
        "ma20": ind.get("ma20"),
        "ma60": ind.get("ma60"),
        "ret_20d_pct": ind.get("ret_20d_pct"),
        "vol_ratio_5_20": ind.get("vol_ratio_5_20"),
        "pe_ttm": (pack.get("fundamental") or {}).get("pe_ttm"),
        "pb": (pack.get("fundamental") or {}).get("pb"),
        "revenue_growth_yoy": (pack.get("fundamental") or {}).get("revenue_growth_yoy"),
        "net_profit_growth_yoy": (pack.get("fundamental") or {}).get("net_profit_growth_yoy"),
        "moneyflow_net_amount_5d": ((pack.get("moneyflow") or {}).get("latest") or {}).get("net_amount_5d"),
    }


def _clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))


def load_scoring_config(path: str | Path = "config/scoring_weights.json") -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return DEFAULT_SCORING_CONFIG
    data = json.loads(config_path.read_text(encoding="utf-8"))
    merged = json.loads(json.dumps(DEFAULT_SCORING_CONFIG))
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    _validate_weights(merged["weights"])
    return merged


def _validate_weights(weights: dict[str, float]) -> None:
    total = round(sum(float(value) for value in weights.values()), 6)
    if total != 1:
        raise ValueError(f"评分权重合计必须为 1，当前为 {total}")


def _gap_penalty(gaps: list[str], config: dict[str, int]) -> int:
    penalty = 0
    for gap in gaps:
        if "financials" in gap or "moneyflow" in gap or "market_indices" in gap:
            penalty += int(config.get("critical", 6))
        elif "announcements" in gap or "limit_list" in gap:
            penalty += int(config.get("warning", 3))
        else:
            penalty += int(config.get("info", 1))
    return penalty

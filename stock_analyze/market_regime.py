from __future__ import annotations

import math
from typing import Any

INDEX_AK_SYMBOLS = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "沪深300": "sh000300",
    "中证500": "sh000905",
    "中证1000": "sh000852",
}


def analyze_market_regime(
    market_context: dict[str, Any],
    market_sentiment: dict[str, Any],
    data_gaps: list[str],
) -> dict[str, Any]:
    indices = market_context.get("indices") or []
    if not indices:
        data_gaps.append("index_daily_missing")

    index_rows: dict[str, Any] = {}
    positive = 0
    negative = 0
    amount_ratios: list[float] = []
    for item in indices:
        pct = _num(item.get("pct_chg"))
        if pct is not None and pct > 0:
            positive += 1
        elif pct is not None and pct < 0:
            negative += 1
        name = item.get("name") or item.get("ts_code") or "指数"
        ak_metrics = _history_index_metrics(item.get("history") or []) or _akshare_index_metrics(str(name))
        if ak_metrics.get("amount_ratio_5_20") is not None:
            amount_ratios.append(ak_metrics["amount_ratio_5_20"])
        index_rows[str(name)] = {
            "trade_date": item.get("trade_date"),
            "close": item.get("close"),
            "pct_chg": pct,
            "above_ma20": ak_metrics.get("above_ma20"),
            "above_ma60": ak_metrics.get("above_ma60"),
            "ma20_above_ma60": ak_metrics.get("ma20_above_ma60"),
            "return_5d": ak_metrics.get("return_5d"),
            "return_20d": ak_metrics.get("return_20d") if ak_metrics.get("return_20d") is not None else pct,
            "return_60d": ak_metrics.get("return_60d"),
            "max_drawdown20": ak_metrics.get("max_drawdown20"),
            "max_drawdown60": ak_metrics.get("max_drawdown60"),
            "amount_ma5": ak_metrics.get("amount_ma5"),
            "amount_ma20": ak_metrics.get("amount_ma20"),
            "amount_ratio_5_20": ak_metrics.get("amount_ratio_5_20"),
            "fallback_source": ak_metrics.get("source"),
        }
    if indices and not amount_ratios:
        data_gaps.append("index_dailybasic_missing")
    northbound = _akshare_northbound()
    if not northbound:
        data_gaps.append("moneyflow_hsgt_missing")

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
        "turnover": {
            "amount_ratio_5_20_avg": round(sum(amount_ratios) / len(amount_ratios), 4) if amount_ratios else None,
            "source": "akshare.stock_zh_index_daily_em" if amount_ratios else None,
        },
        "northbound": northbound or {"net_inflow_1d": None, "net_inflow_5d": None, "net_inflow_20d": None},
        "risks": risks,
        "evidence": [f"主要指数上涨数量={positive}，下跌数量={negative}", f"涨停数={up}，跌停数={down}"],
    }


def _akshare_index_metrics(name: str) -> dict[str, Any]:
    symbol = INDEX_AK_SYMBOLS.get(name)
    if not symbol:
        return {}
    try:
        ak = _load_akshare()
        df = ak.stock_zh_index_daily_em(symbol=symbol)
        rows = _records(df)
    except Exception:  # noqa: BLE001 - AkShare 兜底失败不影响主流程
        return {}
    if len(rows) < 20:
        return {}
    closes = [_num(row.get("close") or row.get("收盘")) for row in rows]
    amounts = [_num(row.get("amount") or row.get("成交额")) for row in rows]
    if not any(value is not None for value in amounts):
        amounts = [_num(row.get("volume") or row.get("成交量")) for row in rows]
    closes = [value for value in closes if value is not None]
    amounts = [value for value in amounts if value is not None]
    if len(closes) < 20:
        return {}
    ma20 = _ma(closes, 20)
    ma60 = _ma(closes, 60)
    amount_ma5 = _ma(amounts, 5)
    amount_ma20 = _ma(amounts, 20)
    close = closes[-1]
    return {
        "source": "akshare.stock_zh_index_daily_em",
        "ma20": ma20,
        "ma60": ma60,
        "above_ma20": close >= ma20 if ma20 is not None else None,
        "above_ma60": close >= ma60 if ma60 is not None else None,
        "ma20_above_ma60": ma20 >= ma60 if ma20 is not None and ma60 is not None else None,
        "return_5d": _pct_change(closes, 5),
        "return_20d": _pct_change(closes, 20),
        "return_60d": _pct_change(closes, 60),
        "max_drawdown20": _max_drawdown(closes, 20),
        "max_drawdown60": _max_drawdown(closes, 60),
        "amount_ma5": amount_ma5,
        "amount_ma20": amount_ma20,
        "amount_ratio_5_20": round(amount_ma5 / amount_ma20, 4) if amount_ma5 is not None and amount_ma20 not in (None, 0) else None,
    }


def _history_index_metrics(history: list[dict[str, Any]]) -> dict[str, Any]:
    if len(history) < 20:
        return {}
    closes = [_num(row.get("close")) for row in history]
    amounts = [_num(row.get("amount")) for row in history]
    if not any(value is not None for value in amounts):
        amounts = [_num(row.get("volume")) for row in history]
    closes = [value for value in closes if value is not None]
    amounts = [value for value in amounts if value is not None]
    if len(closes) < 20:
        return {}
    ma20 = _ma(closes, 20)
    ma60 = _ma(closes, 60)
    amount_ma5 = _ma(amounts, 5)
    amount_ma20 = _ma(amounts, 20)
    close = closes[-1]
    return {
        "source": "tushare.index_daily.history",
        "ma20": ma20,
        "ma60": ma60,
        "above_ma20": close >= ma20 if ma20 is not None else None,
        "above_ma60": close >= ma60 if ma60 is not None else None,
        "ma20_above_ma60": ma20 >= ma60 if ma20 is not None and ma60 is not None else None,
        "return_5d": _pct_change(closes, 5),
        "return_20d": _pct_change(closes, 20),
        "return_60d": _pct_change(closes, 60),
        "max_drawdown20": _max_drawdown(closes, 20),
        "max_drawdown60": _max_drawdown(closes, 60),
        "amount_ma5": amount_ma5,
        "amount_ma20": amount_ma20,
        "amount_ratio_5_20": round(amount_ma5 / amount_ma20, 4) if amount_ma5 is not None and amount_ma20 not in (None, 0) else None,
    }


def _akshare_northbound() -> dict[str, Any] | None:
    try:
        ak = _load_akshare()
        for name in ["stock_hsgt_north_net_flow_in_em", "stock_hsgt_hist_em"]:
            func = getattr(ak, name, None)
            if func is None:
                continue
            rows = _records(func())
            values = [
                _num(
                    row.get("北向资金")
                    or row.get("净流入")
                    or row.get("当日资金流入")
                    or row.get("资金净流入")
                    or row.get("value")
                )
                for row in rows
            ]
            values = [value for value in values if value is not None]
            if values:
                return {
                    "net_inflow_1d": round(values[-1], 4),
                    "net_inflow_5d": round(sum(values[-5:]), 4) if len(values) >= 5 else None,
                    "net_inflow_20d": round(sum(values[-20:]), 4) if len(values) >= 20 else None,
                    "source": f"akshare.{name}",
                }
    except Exception:  # noqa: BLE001 - AkShare 兜底失败不影响主流程
        return None
    return None


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
        result = float(value)
        if math.isnan(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _records(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    if hasattr(df, "to_dict"):
        return list(df.to_dict("records"))
    if isinstance(df, list):
        return [item for item in df if isinstance(item, dict)]
    return []


def _ma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 4)


def _pct_change(values: list[float], days: int) -> float | None:
    if len(values) <= days or values[-days - 1] == 0:
        return None
    return round((values[-1] / values[-days - 1] - 1) * 100, 4)


def _max_drawdown(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    sample = values[-window:]
    peak = sample[0]
    worst = 0.0
    for value in sample:
        peak = max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1)
    return round(worst * 100, 4)


def _load_akshare():
    import akshare as ak

    return ak

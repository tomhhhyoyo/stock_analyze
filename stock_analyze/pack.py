from __future__ import annotations

from datetime import datetime
from typing import Any

from .data_provider import MarketDataProvider
from .announcements import enrich_announcements
from .indicators import atr, bollinger, macd, max_drawdown, moving_average, pct_change, rsi, volatility
from .models import AnalysisRequest
from .symbols import lookup_name_by_symbol


def build_market_pack(request: AnalysisRequest, symbol: str, provider: MarketDataProvider) -> dict[str, Any]:
    bars = provider.fetch_daily_bars(symbol, request.period.start_date, request.period.end_date)
    if len(bars) < 20:
        raise RuntimeError(f"{symbol} 可用日线少于 20 根，停止数值分析。")
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    last = bars[-1]
    basic = provider.fetch_basic(symbol, last.date)
    financials = provider.fetch_financials(symbol, request.period.start_date, request.period.end_date)
    announcements = enrich_announcements(provider.fetch_announcements(symbol, request.period.start_date, request.period.end_date))
    moneyflow = provider.fetch_moneyflow(symbol, request.period.start_date, request.period.end_date)
    market_context = provider.fetch_market_context(last.date, symbol)
    data_gaps = _collect_data_gaps(financials, moneyflow, market_context, announcements)
    indicators = {
        "ma5": moving_average(closes, 5),
        "ma10": moving_average(closes, 10),
        "ma20": moving_average(closes, 20),
        "ma60": moving_average(closes, 60),
        "ma120": moving_average(closes, 120),
        "ma250": moving_average(closes, 250),
        "rsi14": rsi(closes, 14),
        "macd": macd(closes),
        "bollinger20": bollinger(closes, 20),
        "atr14": atr(highs, lows, closes, 14),
        "max_drawdown60": max_drawdown(closes, 60),
        "volatility20": volatility(closes, 20),
        "max_drawdown_60d_pct": max_drawdown(closes, 60),
        "volatility_20d_pct": volatility(closes, 20),
        "vol_ma5": moving_average(volumes, 5),
        "vol_ma20": moving_average(volumes, 20),
        "ret_5d_pct": pct_change(closes, 5),
        "ret_20d_pct": pct_change(closes, 20),
        "ret_60d_pct": pct_change(closes, 60),
        "high_20": round(max(highs[-20:]), 4),
        "low_20": round(min(lows[-20:]), 4),
        "high_60": round(max(highs[-60:]), 4) if len(highs) >= 60 else None,
        "low_60": round(min(lows[-60:]), 4) if len(lows) >= 60 else None,
    }
    if indicators["vol_ma5"] and indicators["vol_ma20"]:
        indicators["vol_ratio_5_20"] = round(indicators["vol_ma5"] / indicators["vol_ma20"], 4)
    else:
        indicators["vol_ratio_5_20"] = None
    quote = {
        "open": last.open,
        "high": last.high,
        "low": last.low,
        "close": last.close,
        "volume": last.volume,
        "amount": last.amount,
    }
    return {
        "meta": {
            "contract_version": "1.1.0",
            "symbol": symbol,
            "name": lookup_name_by_symbol(symbol),
            "market": "A-share",
            "currency": "CNY",
            "as_of": datetime.now().astimezone().isoformat(timespec="seconds"),
            "trade_date": last.date,
            "source": basic.get("source") or provider.__class__.__name__,
            "data_delay_note": "日线数据可能存在数据源刷新延迟，不是 tick 级实时行情。",
        },
        "request": request.to_dict(),
        "data_contract": {
            "required_sections": ["meta", "quote", "daily_bars", "indicators", "fundamental", "moneyflow", "market_context"],
            "numeric_source_rule": "所有数值结论必须来自 market_pack.json，不允许模型记忆补数。",
            "staleness_rule": "trade_date 是行情交易日，as_of 是本地生成时间。",
        },
        "quote": quote,
        "daily_bars": [bar.to_dict() for bar in bars],
        "indicators": indicators,
        "fundamental": {
            "pe_ttm": basic.get("pe_ttm"),
            "pb": basic.get("pb"),
            "market_cap": basic.get("market_cap"),
            "circ_market_cap": basic.get("circ_market_cap"),
            "roe": financials.get("latest", {}).get("roe") or basic.get("roe"),
            "roe_dt": financials.get("latest", {}).get("roe_dt"),
            "revenue": financials.get("latest", {}).get("revenue"),
            "net_profit_parent": financials.get("latest", {}).get("net_profit_parent"),
            "revenue_growth_yoy": financials.get("latest", {}).get("revenue_growth_yoy") or basic.get("revenue_growth_yoy"),
            "net_profit_growth_yoy": financials.get("latest", {}).get("net_profit_growth_yoy")
            or basic.get("net_profit_growth_yoy"),
            "gross_margin": financials.get("latest", {}).get("gross_margin"),
            "report_end_date": financials.get("latest", {}).get("report_end_date"),
            "ann_date": financials.get("latest", {}).get("ann_date"),
            "source": financials.get("source") or basic.get("source"),
        },
        "announcements": announcements,
        "moneyflow": moneyflow,
        "market_context": market_context,
        "data_gaps": data_gaps,
        "risk_flags": _risk_flags(basic, indicators, financials, moneyflow, market_context, announcements),
        "data_audit": _build_data_audit(bars, indicators, financials, moneyflow, market_context, announcements, data_gaps),
        "trace": {
            "quote.close": "daily_bars[-1].close",
            "indicators.ma20": "computed from daily_bars.close[-20:]",
            "indicators.ma60": "computed from daily_bars.close[-60:]",
            "indicators.vol_ratio_5_20": "vol_ma5 / vol_ma20",
            "fundamental": "provider.fetch_financials + provider.fetch_basic",
            "announcements": "provider.fetch_announcements",
            "moneyflow": "provider.fetch_moneyflow",
            "market_context": "provider.fetch_market_context",
        },
    }


def _risk_flags(
    basic: dict[str, Any],
    indicators: dict[str, Any],
    financials: dict[str, Any],
    moneyflow: dict[str, Any],
    market_context: dict[str, Any],
    announcements: list[dict[str, Any]],
) -> list[str]:
    flags: list[str] = []
    pe = basic.get("pe_ttm")
    if pe is not None and pe > 60:
        flags.append("PE_TTM_HIGH")
    pb = basic.get("pb")
    if pb is not None and pb > 8:
        flags.append("PB_HIGH")
    if indicators.get("ma20") and indicators.get("ma60") and indicators["ma20"] < indicators["ma60"]:
        flags.append("MA20_BELOW_MA60")
    if indicators.get("ret_20d_pct") is not None and indicators["ret_20d_pct"] < -10:
        flags.append("RECENT_DRAWDOWN")
    fin = financials.get("latest") or {}
    if fin.get("net_profit_growth_yoy") is not None and fin["net_profit_growth_yoy"] < 0:
        flags.append("NET_PROFIT_GROWTH_NEGATIVE")
    if fin.get("revenue_growth_yoy") is not None and fin["revenue_growth_yoy"] < 0:
        flags.append("REVENUE_GROWTH_NEGATIVE")
    mf = moneyflow.get("latest") or {}
    if mf.get("net_amount_5d") is not None and mf["net_amount_5d"] < 0:
        flags.append("MONEYFLOW_5D_NEGATIVE")
    sentiment = (market_context.get("sentiment") or {})
    if sentiment.get("limit_down_count", 0) > sentiment.get("limit_up_count", 0):
        flags.append("MARKET_SENTIMENT_WEAK")
    if any(item.get("risk_level") in {"medium", "high"} for item in announcements[:5]):
        flags.append("ANNOUNCEMENT_EVENT_RISK")
    return flags


def _collect_data_gaps(
    financials: dict[str, Any],
    moneyflow: dict[str, Any],
    market_context: dict[str, Any],
    announcements: list[dict[str, Any]],
) -> list[str]:
    gaps: list[str] = []
    gaps.extend(financials.get("gaps") or [])
    gaps.extend(moneyflow.get("gaps") or [])
    gaps.extend(market_context.get("gaps") or [])
    if not announcements:
        gaps.append("announcements_empty_or_unavailable")
    if not (financials.get("latest") or {}):
        gaps.append("financials_empty_or_unavailable")
    if not (moneyflow.get("latest") or {}):
        gaps.append("moneyflow_empty_or_unavailable")
    if not (market_context.get("indices") or []):
        gaps.append("market_indices_empty_or_unavailable")
    industry = market_context.get("industry") or {}
    if industry.get("status") == "not_configured":
        gaps.append("industry_index_mapping_not_configured")
    if industry.get("status") == "failed":
        gaps.append("industry_index_unavailable")
    return sorted(set(gaps))


def _build_data_audit(
    bars: list[Any],
    indicators: dict[str, Any],
    financials: dict[str, Any],
    moneyflow: dict[str, Any],
    market_context: dict[str, Any],
    announcements: list[dict[str, Any]],
    data_gaps: list[str],
) -> dict[str, Any]:
    return {
        "daily_bars_count": len(bars),
        "has_ma20": indicators.get("ma20") is not None,
        "has_ma60": indicators.get("ma60") is not None,
        "has_financials": bool(financials.get("latest")),
        "has_moneyflow": bool(moneyflow.get("latest")),
        "has_market_indices": bool(market_context.get("indices")),
        "has_market_sentiment": bool(market_context.get("sentiment")),
        "announcements_count": len(announcements),
        "high_risk_announcements_count": sum(1 for item in announcements if item.get("risk_level") == "high"),
        "data_gaps_count": len(data_gaps),
        "data_gaps": data_gaps,
    }

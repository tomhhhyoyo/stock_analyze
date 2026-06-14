from __future__ import annotations

from datetime import datetime
from typing import Any

from .data_provider import MarketDataProvider
from .announcements import enrich_announcements
from .indicators import atr, bollinger, macd, max_drawdown, moving_average, pct_change, rsi, volatility
from .market_regime import analyze_market_regime
from .models import AnalysisRequest
from .sector_context import analyze_sector_context
from .symbols import lookup_name_by_symbol
from .volume_price import analyze_volume_price

SECOND_BATCH_RESERVED = ("fina_mainbz", "forecast", "express", "dividend", "disclosure_date")
THIRD_BATCH_RESERVED = (
    "top_list",
    "top_inst",
    "margin",
    "margin_detail",
    "moneyflow_hsgt",
    "hsgt_top10",
    "index_dailybasic",
    "index_classify",
    "index_member",
    "concept",
    "concept_detail",
)


def build_market_pack(request: AnalysisRequest, symbol: str, provider: MarketDataProvider) -> dict[str, Any]:
    bars = provider.fetch_daily_bars(symbol, request.period.start_date, request.period.end_date)
    if len(bars) < 20:
        raise RuntimeError(f"{symbol} 可用日线少于 20 根，停止数值分析。")
    closes = [bar.qfq_close if bar.qfq_close is not None else bar.close for bar in bars]
    highs = [bar.qfq_high if bar.qfq_high is not None else bar.high for bar in bars]
    lows = [bar.qfq_low if bar.qfq_low is not None else bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    last = bars[-1]
    basic = provider.fetch_basic(symbol, last.date)
    financials = provider.fetch_financials(symbol, request.period.start_date, request.period.end_date)
    announcements = enrich_announcements(provider.fetch_announcements(symbol, request.period.start_date, request.period.end_date))
    moneyflow = provider.fetch_moneyflow(symbol, request.period.start_date, request.period.end_date)
    market_context = provider.fetch_market_context(last.date, symbol)
    market_sentiment = market_context.get("sentiment") or {}
    provider_gaps = provider.consume_data_gaps() if hasattr(provider, "consume_data_gaps") else []
    data_gaps = _collect_data_gaps(financials, moneyflow, market_context, announcements, provider_gaps)
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
        "adj_factor": last.adj_factor,
        "qfq_open": last.qfq_open,
        "qfq_high": last.qfq_high,
        "qfq_low": last.qfq_low,
        "qfq_close": last.qfq_close,
        "limit_up": last.limit_up,
        "limit_down": last.limit_down,
        "pct_to_limit_up": last.pct_to_limit_up,
        "pct_to_limit_down": last.pct_to_limit_down,
    }
    fundamental = _build_fundamental(basic, financials)
    tushare_extensions = _build_tushare_extensions(financials)
    daily_bar_rows = [bar.to_dict() for bar in bars]
    volume_price = analyze_volume_price(daily_bar_rows, basic, moneyflow, market_sentiment, data_gaps)
    market_regime = analyze_market_regime(market_context, market_sentiment, data_gaps)
    sector_context = analyze_sector_context(market_context, daily_bar_rows, indicators, data_gaps)
    data_gaps = sorted(set(data_gaps))
    return {
        "meta": {
            "contract_version": "1.2.0",
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
            "required_sections": [
                "meta",
                "quote",
                "daily_bars",
                "indicators",
                "volume_price",
                "fundamental",
                "moneyflow",
                "market_context",
                "market_sentiment",
                "market_regime",
                "sector_context",
            ],
            "numeric_source_rule": "所有数值结论必须来自 market_pack.json，不允许模型记忆补数。",
            "staleness_rule": "trade_date 是行情交易日，as_of 是本地生成时间。",
        },
        "quote": quote,
        "daily_bars": daily_bar_rows,
        "indicators": indicators,
        "volume_price": volume_price,
        "fundamental": fundamental,
        "tushare_extensions": tushare_extensions,
        "announcements": announcements,
        "moneyflow": moneyflow,
        "market_context": market_context,
        "market_sentiment": market_sentiment,
        "market_regime": market_regime,
        "sector_context": sector_context,
        "data_gaps": data_gaps,
        "risk_flags": _risk_flags(basic, indicators, financials, moneyflow, market_context, announcements, last),
        "data_audit": _build_data_audit(
            bars,
            indicators,
            financials,
            moneyflow,
            market_context,
            market_sentiment,
            announcements,
            data_gaps,
            tushare_extensions,
            volume_price,
            market_regime,
            sector_context,
        ),
        "trace": {
            "quote.close": "daily_bars[-1].close",
            "quote.qfq_close": "daily_bars[-1].qfq_close, computed from daily + adj_factor",
            "indicators.ma20": "computed from daily_bars.qfq_close[-20:] with raw close fallback",
            "indicators.ma60": "computed from daily_bars.qfq_close[-60:] with raw close fallback",
            "indicators.vol_ratio_5_20": "vol_ma5 / vol_ma20",
            "volume_price": "computed from daily_bars, daily_basic fields, moneyflow, stk_limit, market_sentiment",
            "fundamental": "provider.fetch_financials + provider.fetch_basic",
            "fundamental.balance_sheet": "provider.fetch_financials.balancesheet",
            "fundamental.cashflow": "provider.fetch_financials.cashflow",
            "quote.limit_up/down": "provider.fetch_daily_bars.stk_limit",
            "announcements": "provider.fetch_announcements",
            "moneyflow": "provider.fetch_moneyflow",
            "market_context": "provider.fetch_market_context",
            "market_regime": "computed from market_context.indices, market_sentiment, optional index_dailybasic and moneyflow_hsgt gaps",
            "sector_context": "computed from market_context.industry and stock daily_bars relative strength",
        },
    }


def _build_fundamental(basic: dict[str, Any], financials: dict[str, Any]) -> dict[str, Any]:
    latest = financials.get("latest") or {}
    return {
        "pe_ttm": basic.get("pe_ttm"),
        "pb": basic.get("pb"),
        "market_cap": basic.get("market_cap"),
        "circ_market_cap": basic.get("circ_market_cap"),
        "turnover_rate": basic.get("turnover_rate"),
        "turnover_rate_f": basic.get("turnover_rate_f"),
        "volume_ratio": basic.get("volume_ratio"),
        "roe": latest.get("roe") or basic.get("roe"),
        "roe_dt": latest.get("roe_dt"),
        "revenue": latest.get("revenue"),
        "net_profit_parent": latest.get("net_profit_parent"),
        "revenue_growth_yoy": latest.get("revenue_growth_yoy") or basic.get("revenue_growth_yoy"),
        "net_profit_growth_yoy": latest.get("net_profit_growth_yoy") or basic.get("net_profit_growth_yoy"),
        "gross_margin": latest.get("gross_margin"),
        "asset_liability_ratio": latest.get("asset_liability_ratio"),
        "money_cap": latest.get("money_cap"),
        "accounts_receiv": latest.get("accounts_receiv"),
        "inventories": latest.get("inventories"),
        "goodwill": latest.get("goodwill"),
        "interest_bearing_debt": latest.get("interest_bearing_debt"),
        "total_assets": latest.get("total_assets"),
        "total_liab": latest.get("total_liab"),
        "operating_cashflow": latest.get("operating_cashflow"),
        "investing_cashflow": latest.get("investing_cashflow"),
        "financing_cashflow": latest.get("financing_cashflow"),
        "free_cashflow": latest.get("free_cashflow"),
        "operating_cashflow_to_net_profit": latest.get("operating_cashflow_to_net_profit"),
        "report_end_date": latest.get("report_end_date"),
        "ann_date": latest.get("ann_date"),
        "source": financials.get("source") or basic.get("source"),
    }


def _build_tushare_extensions(financials: dict[str, Any]) -> dict[str, Any]:
    reserved = financials.get("reserved") or {}
    return {
        "implemented": {
            "adj_factor": "daily_bars.qfq_*",
            "balancesheet": "fundamental.balance_sheet fields",
            "cashflow": "fundamental.cashflow fields",
            "stk_limit": "quote.limit_* and daily_bars.limit_*",
        },
        "reserved": {
            "second_batch": {key: list(reserved.get(key) or []) for key in SECOND_BATCH_RESERVED},
            "third_batch": {key: list(reserved.get(key) or []) for key in THIRD_BATCH_RESERVED},
        },
    }


def _risk_flags(
    basic: dict[str, Any],
    indicators: dict[str, Any],
    financials: dict[str, Any],
    moneyflow: dict[str, Any],
    market_context: dict[str, Any],
    announcements: list[dict[str, Any]],
    last_bar: Any,
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
    if fin.get("asset_liability_ratio") is not None and fin["asset_liability_ratio"] >= 0.7:
        flags.append("ASSET_LIABILITY_RATIO_HIGH")
    if fin.get("interest_bearing_debt") is not None and fin.get("money_cap") is not None and fin["interest_bearing_debt"] > fin["money_cap"]:
        flags.append("INTEREST_BEARING_DEBT_ABOVE_CASH")
    if fin.get("goodwill") is not None and fin.get("total_assets") not in (None, 0):
        if fin["goodwill"] / fin["total_assets"] >= 0.1:
            flags.append("GOODWILL_RATIO_HIGH")
    if fin.get("operating_cashflow") is not None and fin["operating_cashflow"] < 0:
        flags.append("OPERATING_CASHFLOW_NEGATIVE")
    if fin.get("free_cashflow") is not None and fin["free_cashflow"] < 0:
        flags.append("FREE_CASHFLOW_NEGATIVE")
    if fin.get("operating_cashflow_to_net_profit") is not None and fin["operating_cashflow_to_net_profit"] < 0.8:
        flags.append("CASHFLOW_TO_PROFIT_WEAK")
    mf = moneyflow.get("latest") or {}
    if mf.get("net_amount_5d") is not None and mf["net_amount_5d"] < 0:
        flags.append("MONEYFLOW_5D_NEGATIVE")
    sentiment = (market_context.get("sentiment") or {})
    down_count = sentiment.get("down_limit_count", sentiment.get("limit_down_count", 0)) or 0
    up_count = sentiment.get("up_limit_count", sentiment.get("limit_up_count", 0)) or 0
    if down_count > up_count:
        flags.append("MARKET_SENTIMENT_WEAK")
    if any(item.get("risk_level") in {"medium", "high"} for item in announcements[:5]):
        flags.append("ANNOUNCEMENT_EVENT_RISK")
    if getattr(last_bar, "limit_up", None) is not None and getattr(last_bar, "close", None) is not None:
        if last_bar.close >= last_bar.limit_up * 0.999:
            flags.append("AT_LIMIT_UP")
        elif getattr(last_bar, "pct_to_limit_up", None) is not None and last_bar.pct_to_limit_up <= 2:
            flags.append("NEAR_LIMIT_UP")
    if getattr(last_bar, "limit_down", None) is not None and getattr(last_bar, "close", None) is not None:
        if last_bar.close <= last_bar.limit_down * 1.001:
            flags.append("AT_LIMIT_DOWN")
        elif getattr(last_bar, "pct_to_limit_down", None) is not None and last_bar.pct_to_limit_down <= 2:
            flags.append("NEAR_LIMIT_DOWN")
    return flags


def _collect_data_gaps(
    financials: dict[str, Any],
    moneyflow: dict[str, Any],
    market_context: dict[str, Any],
    announcements: list[dict[str, Any]],
    daily_gaps: list[str] | None = None,
) -> list[str]:
    gaps: list[str] = []
    gaps.extend(daily_gaps or [])
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
    market_sentiment: dict[str, Any],
    announcements: list[dict[str, Any]],
    data_gaps: list[str],
    tushare_extensions: dict[str, Any] | None = None,
    volume_price: dict[str, Any] | None = None,
    market_regime: dict[str, Any] | None = None,
    sector_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    optional_missing = []
    if not market_sentiment or market_sentiment.get("data_quality") == "warning":
        optional_missing.append(
            {
                "field": "market_sentiment",
                "level": "warning",
                "message": "市场情绪多源数据未完整返回，已按中性降级，不影响技术面、估值和基本面评分。",
                "warnings": (market_sentiment or {}).get("warnings", []),
            }
        )
    return {
        "daily_bars_count": len(bars),
        "has_adj_factor": any(getattr(bar, "adj_factor", None) is not None for bar in bars),
        "has_qfq_prices": any(getattr(bar, "qfq_close", None) is not None for bar in bars),
        "has_stk_limit": any(getattr(bar, "limit_up", None) is not None and getattr(bar, "limit_down", None) is not None for bar in bars),
        "has_ma20": indicators.get("ma20") is not None,
        "has_ma60": indicators.get("ma60") is not None,
        "has_financials": bool(financials.get("latest")),
        "has_balancesheet": _has_any(
            financials,
            ["asset_liability_ratio", "money_cap", "accounts_receiv", "inventories", "goodwill", "interest_bearing_debt"],
        ),
        "has_cashflow": _has_any(
            financials,
            ["operating_cashflow", "investing_cashflow", "financing_cashflow", "free_cashflow", "operating_cashflow_to_net_profit"],
        ),
        "has_moneyflow": bool(moneyflow.get("latest")),
        "has_market_indices": bool(market_context.get("indices")),
        "has_market_sentiment": bool(market_sentiment) and market_sentiment.get("data_quality") != "warning",
        "has_volume_price": bool(volume_price and (volume_price.get("metrics") or {}).get("score") is not None),
        "volume_price_confidence": (volume_price or {}).get("confidence"),
        "has_market_regime": bool(market_regime and market_regime.get("score") is not None),
        "has_sector_context": bool(sector_context and sector_context.get("score") is not None),
        "market_regime_confidence": (market_regime or {}).get("confidence"),
        "sector_context_confidence": (sector_context or {}).get("confidence"),
        "announcements_count": len(announcements),
        "high_risk_announcements_count": sum(1 for item in announcements if item.get("risk_level") == "high"),
        "optional_fields_missing": optional_missing,
        "reserved_tushare_fields": (tushare_extensions or {}).get("reserved") or {},
        "data_gaps_count": len(data_gaps),
        "data_gaps": data_gaps,
    }


def _has_any(financials: dict[str, Any], keys: list[str]) -> bool:
    latest = financials.get("latest") or {}
    return any(latest.get(key) is not None for key in keys)

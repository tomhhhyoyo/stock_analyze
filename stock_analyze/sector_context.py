from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

CACHE_DIR = Path("data_cache")


def analyze_sector_context(
    market_context: dict[str, Any],
    daily_bars: list[dict[str, Any]],
    indicators: dict[str, Any],
    data_gaps: list[str],
) -> dict[str, Any]:
    industry = market_context.get("industry") or {}
    if industry.get("status") != "ok":
        data_gaps.append("sector_index_missing")
    sector_members = _akshare_sector_members(industry)
    if not sector_members:
        data_gaps.append("sector_member_missing")
    sector_sentiment = _akshare_sector_sentiment(industry, sector_members) or _market_sentiment_proxy(market_context, industry)
    if not sector_sentiment:
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
        "sector_members": sector_members,
        "sector_sentiment": sector_sentiment
        or {"up_limit_count": None, "down_limit_count": None, "limit_break_count": None, "limit_break_rate": None},
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


def _akshare_sector_members(industry: dict[str, Any]) -> dict[str, Any]:
    code = str(industry.get("ts_code") or "").split(".")[0]
    if not code:
        return {}
    try:
        ak = _load_akshare()
        for name in ["index_component_sw", "index_component"]:
            func = getattr(ak, name, None)
            if func is None:
                continue
            rows = _records(func(symbol=code))
            if rows:
                codes = [_stock_code(row) for row in rows]
                return {
                    "source": f"akshare.{name}",
                    "count": len(rows),
                    "codes": [code for code in codes if code],
                    "sample": [_json_safe(row) for row in rows[:10]],
                }
    except Exception:  # noqa: BLE001 - AkShare 兜底失败不影响主流程
        return {}
    return {}


def _akshare_sector_sentiment(industry: dict[str, Any], sector_members: dict[str, Any]) -> dict[str, Any]:
    sector_name = str(industry.get("name") or "")
    member_codes = {str(code).zfill(6) for code in sector_members.get("codes", [])}
    if not member_codes:
        member_codes = {str(row.get("证券代码") or row.get("代码") or "").zfill(6) for row in sector_members.get("sample", [])}
    member_codes = {code for code in member_codes if code and code != "000000"}
    if not sector_name and not member_codes:
        return {}
    try:
        ak = _load_akshare()
    except Exception:  # noqa: BLE001 - AkShare 兜底不可用时不影响主流程
        return {}
    up_rows = _safe_pool_rows(ak, "stock_zt_pool_em", sector_name, member_codes)
    break_rows = _safe_pool_rows(ak, "stock_zt_pool_zbgc_em", sector_name, member_codes)
    down_rows = _safe_pool_rows(ak, "stock_zt_pool_dtgc_em", sector_name, member_codes)
    total = len(up_rows) + len(break_rows)
    spot_stats = _akshare_spot_limit_stats(member_codes)
    up_count = len(up_rows) or spot_stats.get("up_limit_count")
    down_count = len(down_rows) or spot_stats.get("down_limit_count")
    if up_count is None and down_count is None and not break_rows:
        return {}
    return {
        "up_limit_count": up_count,
        "down_limit_count": down_count,
        "limit_break_count": len(break_rows),
        "limit_break_rate": round(len(break_rows) / total, 4) if total else None,
        "source": "akshare.limit_pool_sector_filter+" + str(spot_stats.get("source") or "limit_pool_only"),
        "sector_name": sector_name,
        "limit_calc_note": "涨停/跌停数量由行业成分代码匹配全市场日涨跌幅近似计算；炸板数优先来自炸板池。",
    }


def _market_sentiment_proxy(market_context: dict[str, Any], industry: dict[str, Any]) -> dict[str, Any]:
    sentiment = market_context.get("sentiment") or {}
    up = _num(sentiment.get("up_limit_count") or sentiment.get("limit_up_count"))
    down = _num(sentiment.get("down_limit_count") or sentiment.get("limit_down_count"))
    breaks = _num(sentiment.get("limit_break_count"))
    if up is None and down is None and breaks is None:
        return {}
    return {
        "up_limit_count": int(up or 0),
        "down_limit_count": int(down or 0),
        "limit_break_count": int(breaks or 0),
        "limit_break_rate": sentiment.get("limit_break_rate"),
        "source": "market_sentiment_proxy",
        "sector_name": industry.get("name") or "",
        "data_quality": "proxy",
        "limit_calc_note": "板块成分实时行情不可用时，使用全市场涨跌停情绪作为代理值；该字段不等同于真实板块成分统计。",
    }


def _safe_pool_rows(ak: Any, func_name: str, sector_name: str, member_codes: set[str]) -> list[dict[str, Any]]:
    func = getattr(ak, func_name, None)
    if func is None:
        return []
    try:
        return _filter_sector(_records(func()), sector_name, member_codes)
    except Exception:  # noqa: BLE001 - 单个 AkShare 池子失败不影响实时行情兜底
        return []


def _akshare_spot_limit_stats(member_codes: set[str]) -> dict[str, Any]:
    if not member_codes:
        return {}
    rows: list[dict[str, Any]] = []
    source = ""
    try:
        ak = _load_akshare()
    except Exception:  # noqa: BLE001 - AkShare 兜底失败不影响主流程
        return {}
    for func_name in ["stock_zh_a_spot_em", "stock_zh_a_spot"]:
        func = getattr(ak, func_name, None)
        if func is None:
            continue
        try:
            rows = _records(func())
            if rows:
                source = f"akshare.{func_name}"
                _write_spot_cache(rows, source)
                break
        except Exception:  # noqa: BLE001 - 单个 AkShare 行情源失败时尝试下一个公开源
            continue
    if not rows:
        cached = _read_spot_cache()
        rows = cached.get("rows") or []
        source = cached.get("source") or "akshare.spot_cache"
    if not rows:
        return {}
    up = 0
    down = 0
    matched = 0
    for row in rows:
        code = _stock_code(row)
        if code not in member_codes:
            continue
        pct = _num(row.get("涨跌幅") or row.get("changepercent") or row.get("pct_chg"))
        if pct is None:
            continue
        matched += 1
        threshold = _limit_threshold(code, str(row.get("名称") or row.get("name") or ""))
        if pct >= threshold:
            up += 1
        elif pct <= -threshold:
            down += 1
    if matched == 0:
        return {}
    return {"up_limit_count": up, "down_limit_count": down, "matched_count": matched, "source": source}


def _read_spot_cache() -> dict[str, Any]:
    path = CACHE_DIR / "akshare_stock_zh_a_spot.json"
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            return data
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def _write_spot_cache(rows: list[dict[str, Any]], source: str) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"source": source, "updated_at": datetime.now().isoformat(timespec="seconds"), "rows": [_json_safe(row) for row in rows]}
        (CACHE_DIR / "akshare_stock_zh_a_spot.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return


def _filter_sector(rows: list[dict[str, Any]], sector_name: str, member_codes: set[str]) -> list[dict[str, Any]]:
    keys = ["行业", "所属行业", "板块", "概念", "所属概念"]
    result = []
    for row in rows:
        code = _stock_code(row)
        if code in member_codes:
            result.append(row)
            continue
        text = " ".join(str(row.get(key) or "") for key in keys)
        if sector_name and sector_name in text:
            result.append(row)
    return result


def _stock_code(row: dict[str, Any]) -> str:
    raw = str(row.get("证券代码") or row.get("代码") or row.get("code") or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def _limit_threshold(code: str, name: str) -> float:
    if "ST" in name.upper() or "退" in name:
        return 4.8
    if code.startswith(("300", "301", "688", "689")):
        return 19.5
    if code.startswith(("8", "4", "920")):
        return 29.0
    return 9.5


def _records(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    if hasattr(df, "to_dict"):
        return list(df.to_dict("records"))
    if isinstance(df, list):
        return [item for item in df if isinstance(item, dict)]
    return []


def _json_safe(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _json_value(value) for key, value in row.items()}


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _load_akshare():
    import akshare as ak

    return ak

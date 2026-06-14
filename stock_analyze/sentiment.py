from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Callable

CACHE_DIR = Path("data_cache")


def fetch_market_sentiment(pro: Any, trade_date: str) -> dict[str, Any]:
    compact = trade_date.replace("-", "")
    cached = _read_cache(f"market_sentiment_{compact}")
    if cached and not _should_refresh_sentiment_cache(cached):
        return cached
    warnings: list[dict[str, Any]] = []
    for source, fetcher in [
        ("tushare.limit_list_d", lambda: _from_limit_list_d(pro, compact)),
        ("tushare.limit_list_ths", lambda: _from_limit_list_ths(pro, compact)),
        ("akshare.limit_pool", lambda: _from_akshare_limit_pool(compact)),
        ("tushare.stk_limit+tushare.daily", lambda: _from_stk_limit_daily(pro, compact)),
    ]:
        result = _try_source(source, fetcher, warnings)
        if result:
            if str(result.get("source", "")).startswith("akshare."):
                result["fallback_attempts"] = warnings
                result["warnings"] = list(result.get("warnings") or [])
            else:
                result["warnings"] = warnings + list(result.get("warnings") or [])
            _write_cache(f"market_sentiment_{compact}", result)
            return result
    return _empty_warning(compact, warnings)


def _try_source(source: str, fetcher: Callable[[], dict[str, Any] | None], warnings: list[dict[str, Any]]) -> dict[str, Any] | None:
    last_exc: Exception | None = None
    for delay in _retry_schedule():
        try:
            return fetcher()
        except Exception as exc:  # noqa: BLE001 - 外部数据源失败需要结构化降级
            last_exc = exc
            if not _is_retryable_error(exc) or delay is None:
                break
            if delay > 0:
                time.sleep(delay)
    if last_exc is not None:
        warnings.append(
            {
                "source": source,
                "exception_type": last_exc.__class__.__name__,
                "exception_message": str(last_exc),
                "retryable": _is_retryable_error(last_exc),
            }
        )
    return None


def _should_refresh_sentiment_cache(cached: dict[str, Any]) -> bool:
    source = str(cached.get("source") or "")
    if source == "tushare.stk_limit+tushare.daily" and cached.get("data_quality") == "partial":
        return True
    warnings = cached.get("warnings") or []
    return any("cannot convert float NaN" in str(item.get("exception_message") or item.get("message") or "") for item in warnings)


def _retry_schedule() -> list[float | None]:
    raw = os.environ.get("TUSHARE_RETRY_DELAYS", "1,3")
    delays: list[float | None] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            delays.append(float(value))
        except ValueError:
            continue
    return delays + [None]


def _is_retryable_error(exc: Exception) -> bool:
    message = str(exc)
    non_retry_markers = ["权限", "没有权限", "permission", "接口名"]
    if any(marker in message for marker in non_retry_markers):
        return False
    retry_markers = [
        "频率超限",
        "每分钟最多访问",
        "访问太频繁",
        "Max retries exceeded",
        "ConnectionError",
        "ConnectTimeout",
        "ReadTimeout",
        "Timeout",
        "temporarily unavailable",
        "nodename nor servname provided",
    ]
    return any(marker in message for marker in retry_markers)


def _from_limit_list_d(pro: Any, trade_date: str) -> dict[str, Any] | None:
    df = pro.limit_list_d(trade_date=trade_date)
    rows = _records(df)
    if not rows:
        return None
    up = 0
    down = 0
    breaks = 0
    highest = 0
    for row in rows:
        text = _row_text(row)
        limit_value = str(row.get("limit") or row.get("limit_type") or "")
        if _is_break_text(text):
            breaks += 1
        if _is_down_limit(limit_value, text):
            down += 1
        elif _is_up_limit(limit_value, text):
            up += 1
        highest = max(highest, _limit_step(row))
    return _build_result(trade_date, "tushare.limit_list_d", up, down, breaks, highest, "full", [])


def _from_limit_list_ths(pro: Any, trade_date: str) -> dict[str, Any] | None:
    df = pro.limit_list_ths(trade_date=trade_date)
    rows = _records(df)
    if not rows:
        return None
    up = 0
    down = 0
    breaks = 0
    highest = 0
    for row in rows:
        text = _row_text(row)
        if _is_break_text(text):
            breaks += 1
            highest = max(highest, _limit_step(row))
            continue
        change = _num(row.get("pct_chg") or row.get("change_rate"))
        if "跌停" in text or change is not None and change <= -9:
            down += 1
        else:
            up += 1
        highest = max(highest, _limit_step(row))
    return _build_result(trade_date, "tushare.limit_list_ths", up, down, breaks, highest, "full", [])


def _from_akshare_limit_pool(trade_date: str) -> dict[str, Any] | None:
    ak = _load_akshare()
    up_rows = _records(ak.stock_zt_pool_em(date=trade_date))
    break_rows = _records(ak.stock_zt_pool_zbgc_em(date=trade_date))
    down_rows = _records(ak.stock_zt_pool_dtgc_em(date=trade_date))
    if not up_rows and not break_rows and not down_rows:
        return None
    highest = 0
    for row in up_rows + break_rows:
        highest = max(highest, _limit_step(row))
    result = _build_result(
        trade_date,
        "akshare.stock_zt_pool_em+stock_zt_pool_zbgc_em+stock_zt_pool_dtgc_em",
        len(up_rows),
        len(down_rows),
        len(break_rows),
        highest,
        "full",
        [],
    )
    result["fallback_note"] = "Tushare 涨跌停情绪接口不可用时，使用 AkShare 东方财富涨停池、炸板池、跌停池公开数据兜底。"
    return result


def _from_stk_limit_daily(pro: Any, trade_date: str) -> dict[str, Any] | None:
    limit_df = pro.stk_limit(trade_date=trade_date)
    daily_df = pro.daily(trade_date=trade_date, fields="ts_code,trade_date,high,low,close")
    limit_rows = _records(limit_df)
    daily_rows = _records(daily_df)
    if not limit_rows or not daily_rows:
        return None
    limits = {row.get("ts_code"): row for row in limit_rows if row.get("ts_code")}
    up = 0
    down = 0
    breaks = 0
    down_open = 0
    for row in daily_rows:
        code = row.get("ts_code")
        limit = limits.get(code)
        if not limit:
            continue
        close = _num(row.get("close"))
        high = _num(row.get("high"))
        low = _num(row.get("low"))
        up_limit = _num(limit.get("up_limit"))
        down_limit = _num(limit.get("down_limit"))
        if close is None:
            continue
        if up_limit is not None:
            if close >= up_limit:
                up += 1
            elif high is not None and high >= up_limit and close < up_limit:
                breaks += 1
        if down_limit is not None:
            if close <= down_limit:
                down += 1
            elif low is not None and low <= down_limit and close > down_limit:
                down_open += 1
    warnings = [
        {
            "source": "tushare.stk_limit+tushare.daily",
            "warning_type": "approximation",
            "message": "本次涨跌停状态由日线价格与涨跌停价近似计算，无法覆盖封板时间、封单金额和真实炸板次数。",
        }
    ]
    result = _build_result(trade_date, "tushare.stk_limit+tushare.daily", up, down, breaks, 0, "partial", warnings)
    result["down_limit_open_count"] = down_open
    return result


def _build_result(
    trade_date: str,
    source: str,
    up: int,
    down: int,
    breaks: int,
    highest: int,
    quality: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    break_base = up + breaks
    break_rate = round(breaks / break_base, 4) if break_base else 0.0
    ratio = round(up / down, 4) if down else float(up) if up else 0.0
    score = _sentiment_score(up, down, break_rate)
    return {
        "trade_date": _fmt_trade_date(trade_date),
        "source": source,
        "up_limit_count": up,
        "down_limit_count": down,
        "limit_break_count": breaks,
        "highest_limit_step": highest,
        "limit_break_rate": break_rate,
        "up_down_limit_ratio": ratio,
        "sentiment_score": score,
        "sentiment_label": _sentiment_label(score),
        "data_quality": quality,
        "warnings": warnings,
    }


def _empty_warning(trade_date: str, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "trade_date": _fmt_trade_date(trade_date),
        "source": "market_sentiment_unavailable",
        "up_limit_count": None,
        "down_limit_count": None,
        "limit_break_count": None,
        "highest_limit_step": None,
        "limit_break_rate": None,
        "up_down_limit_ratio": None,
        "sentiment_score": 50,
        "sentiment_label": "数据不足",
        "data_quality": "warning",
        "warnings": warnings
        + [
            {
                "source": "market_sentiment",
                "warning_type": "all_sources_failed",
                "message": "涨跌停情绪多源数据均未返回，市场情绪维度按中性降级处理。",
            }
        ],
    }


def _sentiment_score(up: int, down: int, break_rate: float) -> int:
    score = 50 + min(up, 80) * 0.5 - min(down, 80) * 0.7 - min(break_rate, 1) * 20
    return int(max(0, min(100, round(score))))


def _sentiment_label(score: int) -> str:
    if score >= 70:
        return "偏强"
    if score <= 35:
        return "偏弱"
    return "中性"


def _records(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    if hasattr(df, "empty") and df.empty:
        return []
    if hasattr(df, "to_dict"):
        return df.to_dict("records")
    if isinstance(df, list):
        return [item for item in df if isinstance(item, dict)]
    return []


def _row_text(row: dict[str, Any]) -> str:
    return " ".join(str(value) for value in row.values() if value is not None)


def _is_up_limit(limit_value: str, text: str) -> bool:
    value = limit_value.upper()
    return "U" in value or "涨停" in text or "首板" in text or "连板" in text


def _is_down_limit(limit_value: str, text: str) -> bool:
    value = limit_value.upper()
    return "D" in value or "跌停" in text


def _is_break_text(text: str) -> bool:
    return "炸板" in text or "打开" in text or "开板" in text or "曾涨停" in text


def _limit_step(row: dict[str, Any]) -> int:
    tag_step = _limit_step_from_text(str(row.get("tag") or ""))
    if tag_step:
        return tag_step
    for key in ["limit_times", "连板数", "high_days", "连续跌停"]:
        value = _num(row.get(key))
        if value is not None:
            return int(value)
    return _limit_step_from_text(_row_text(row))


def _limit_step_from_text(text: str) -> int:
    import re

    if "首板" in text:
        return 1
    match = re.search(r"(\d+)\s*天\s*\d+\s*板", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*连板", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*/\s*\d+", text)
    return int(match.group(1)) if match else 0


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


def _load_akshare():
    import akshare as ak

    return ak


def _fmt_trade_date(value: str) -> str:
    if len(value) < 8:
        return value
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def _cache_path(key: str) -> Path:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in key)
    return CACHE_DIR / f"{safe}.json"


def _read_cache(key: str) -> dict[str, Any] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_cache(key: str, data: dict[str, Any]) -> None:
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

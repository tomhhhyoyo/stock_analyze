from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_NAME_TO_SYMBOL = {
    "贵州茅台": "600519.SH",
    "宁德时代": "300750.SZ",
    "平安银行": "000001.SZ",
    "中国联通": "600050.SH",
    "中芯国际": "688981.SH",
    "招商银行": "600036.SH",
    "五粮液": "000858.SZ",
    "比亚迪": "002594.SZ",
    "中国平安": "601318.SH",
    "工业富联": "601138.SH",
    "紫金矿业": "601899.SH",
    "长江电力": "600900.SH",
    "东方财富": "300059.SZ",
    "立讯精密": "002475.SZ",
    "迈瑞医疗": "300760.SZ",
    "隆基绿能": "601012.SH",
    "京东方A": "000725.SZ",
    "海康威视": "002415.SZ",
    "万科A": "000002.SZ",
    "格力电器": "000651.SZ",
}

DEFAULT_SYMBOL_CACHE_PATH = Path("config/symbol_cache.json")


def infer_exchange(code: str) -> str:
    value = code.strip()
    if not re.fullmatch(r"\d{6}", value):
        raise ValueError(f"无法识别股票代码：{code}")
    if value.startswith(("6", "9")):
        return "SH"
    if value.startswith(("0", "2", "3")):
        return "SZ"
    if value.startswith(("4", "8")):
        return "BJ"
    raise ValueError(f"无法推断交易所：{code}")


def normalize_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", value):
        return value
    if re.fullmatch(r"\d{6}", value):
        return f"{value}.{infer_exchange(value)}"
    raise ValueError(f"无法标准化股票代码：{symbol}")


def load_symbol_cache(path: str | Path | None = None) -> dict[str, list[str]]:
    cache_path = Path(path or DEFAULT_SYMBOL_CACHE_PATH)
    if not cache_path.exists():
        return {}
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    result: dict[str, list[str]] = {}
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = ((str(item.get("name", "")), item.get("ts_code") or item.get("symbol")) for item in data["items"] if isinstance(item, dict))
    elif isinstance(data, dict):
        items = data.items()
    elif isinstance(data, list):
        items = ((str(item.get("name", "")), item.get("ts_code") or item.get("symbol")) for item in data if isinstance(item, dict))
    else:
        return {}
    for name, value in items:
        if not name or not value:
            continue
        result.setdefault(name, [])
        values = value if isinstance(value, list) else [value]
        for symbol in values:
            try:
                normalized = normalize_symbol(str(symbol))
            except ValueError:
                continue
            if normalized not in result[name]:
                result[name].append(normalized)
    return result


def refresh_symbol_cache(stock_list: list[dict[str, Any]], path: str | Path | None = None) -> Path:
    cache_path = Path(path or DEFAULT_SYMBOL_CACHE_PATH)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    seen: set[tuple[str, str]] = set()
    for item in stock_list:
        name = str(item.get("name") or "").strip()
        ts_code = str(item.get("ts_code") or item.get("symbol") or "").strip()
        if not name or not ts_code:
            continue
        try:
            normalized = normalize_symbol(ts_code)
        except ValueError:
            continue
        key = (name, normalized)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "name": name,
                "ts_code": normalized,
                "symbol": str(item.get("symbol") or normalized.split(".")[0]),
                "market": item.get("market"),
                "industry": item.get("industry"),
                "list_date": item.get("list_date"),
            }
        )
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "tushare.stock_basic",
        "count": len(rows),
        "items": sorted(rows, key=lambda row: row["ts_code"]),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cache_path


def ensure_symbol_cache(provider: Any, path: str | Path | None = None, max_age_days: int = 7) -> Path | None:
    cache_path = Path(path or DEFAULT_SYMBOL_CACHE_PATH)
    if _is_cache_fresh(cache_path, max_age_days):
        return cache_path
    fetcher = getattr(provider, "fetch_stock_list", None)
    if not callable(fetcher):
        return cache_path if cache_path.exists() else None
    return refresh_symbol_cache(fetcher(), cache_path)


def _is_cache_fresh(path: Path, max_age_days: int) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime <= timedelta(days=max_age_days)


def lookup_symbol_by_name(name: str, cache: dict[str, list[str]] | None = None) -> str | None:
    merged: dict[str, list[str]] = {k: [v] for k, v in DEFAULT_NAME_TO_SYMBOL.items()}
    for key, values in (cache or {}).items():
        merged.setdefault(key, [])
        for value in values:
            if value not in merged[key]:
                merged[key].append(value)
    matched = [(key, values) for key, values in merged.items() if key and key in name]
    symbols = []
    for _, values in matched:
        symbols.extend(values)
    unique = list(dict.fromkeys(symbols))
    if len(unique) > 1:
        raise ValueError(f"股票名称匹配到多个代码：{name} -> {', '.join(unique)}，请补充标准代码。")
    return unique[0] if unique else None


def lookup_name_by_symbol(symbol: str, cache: dict[str, list[str]] | None = None) -> str | None:
    normalized = normalize_symbol(symbol)
    merged: dict[str, list[str]] = {k: [v] for k, v in DEFAULT_NAME_TO_SYMBOL.items()}
    for key, values in (cache or load_symbol_cache()).items():
        merged.setdefault(key, [])
        for value in values:
            if value not in merged[key]:
                merged[key].append(value)
    matches = [name for name, values in merged.items() if normalized in values]
    return matches[0] if matches else None


def extract_symbols(text: str, cache_path: str | Path | None = None) -> list[str]:
    found: list[str] = []
    for match in re.findall(r"\b\d{6}(?:\.(?:SH|SZ|BJ|sh|sz|bj))?\b", text):
        symbol = normalize_symbol(match)
        if symbol not in found:
            found.append(symbol)
    cache = load_symbol_cache(cache_path)
    for token in re.split(r"[,，、\s\n]+", text):
        if not token:
            continue
        symbol = lookup_symbol_by_name(token, cache)
        if symbol and symbol not in found:
            found.append(symbol)
    if not found:
        symbol = lookup_symbol_by_name(text, cache)
        if symbol:
            found.append(symbol)
    return found

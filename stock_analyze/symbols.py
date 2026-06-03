from __future__ import annotations

import json
import re
from pathlib import Path

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
    cache_path = Path(path or "config/symbol_cache.json")
    if not cache_path.exists():
        return {}
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    result: dict[str, list[str]] = {}
    if isinstance(data, dict):
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


from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from .models import DailyBar

CACHE_DIR = Path("data_cache")
INDUSTRY_INDEX_MAP_PATH = Path("config/industry_index_map.json")


class MarketDataProvider(Protocol):
    def fetch_stock_list(self) -> list[dict]:
        ...

    def fetch_daily_bars(self, symbol: str, start_date: date, end_date: date) -> list[DailyBar]:
        ...

    def fetch_basic(self, symbol: str, trade_date: str | None = None) -> dict:
        ...

    def fetch_financials(self, symbol: str, start_date: date, end_date: date) -> dict:
        ...

    def fetch_announcements(self, symbol: str, start_date: date, end_date: date) -> list[dict]:
        ...

    def fetch_moneyflow(self, symbol: str, start_date: date, end_date: date) -> dict:
        ...

    def fetch_market_context(self, trade_date: str | None = None, symbol: str | None = None) -> dict:
        ...


class TushareProvider:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("TUSHARE_TOKEN", "")
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN 未设置，无法使用 Tushare 拉取数据。")
        import tushare as ts

        self.pro = ts.pro_api(self.token)

    def fetch_stock_list(self) -> list[dict]:
        df = self.pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
        if df is None or df.empty:
            raise RuntimeError("Tushare 未返回股票基础列表。")
        return df.to_dict("records")

    def fetch_daily_bars(self, symbol: str, start_date: date, end_date: date) -> list[DailyBar]:
        df = self.pro.daily(
            ts_code=symbol,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            raise RuntimeError(f"Tushare 未返回日线数据：{symbol}")
        df = df.sort_values("trade_date")
        bars: list[DailyBar] = []
        for row in df.to_dict("records"):
            bars.append(
                DailyBar(
                    date=_fmt_trade_date(str(row["trade_date"])),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("vol") or 0),
                    amount=float(row.get("amount") or 0),
                )
            )
        return bars

    def fetch_basic(self, symbol: str, trade_date: str | None = None) -> dict:
        fields = "ts_code,trade_date,total_mv,circ_mv,pe_ttm,pb"
        kwargs = {"ts_code": symbol, "fields": fields}
        if trade_date:
            kwargs["trade_date"] = trade_date.replace("-", "")
        df = self.pro.daily_basic(**kwargs)
        if df is None or df.empty:
            return {}
        row = df.sort_values("trade_date").iloc[-1].to_dict()
        return {
            "pe_ttm": _num(row.get("pe_ttm")),
            "pb": _num(row.get("pb")),
            "market_cap": _num(row.get("total_mv")),
            "circ_market_cap": _num(row.get("circ_mv")),
            "source": "tushare.daily_basic",
        }

    def fetch_financials(self, symbol: str, start_date: date, end_date: date) -> dict:
        start = start_date.strftime("%Y%m%d")
        end = end_date.strftime("%Y%m%d")
        result: dict[str, Any] = {"source": "tushare", "latest": {}, "history": [], "gaps": []}

        fina = _safe_df(
            lambda: self.pro.fina_indicator(
                ts_code=symbol,
                start_date=start,
                end_date=end,
                fields="ts_code,ann_date,end_date,roe,roe_dt,or_yoy,netprofit_yoy,grossprofit_margin",
            ),
            "fina_indicator",
            result["gaps"],
        )
        income = _safe_df(
            lambda: self.pro.income(
                ts_code=symbol,
                start_date=start,
                end_date=end,
                fields="ts_code,ann_date,end_date,revenue,n_income_attr_p,total_profit",
            ),
            "income",
            result["gaps"],
        )
        latest: dict[str, Any] = {}
        if fina is not None and not fina.empty:
            row = fina.sort_values(["end_date", "ann_date"]).iloc[-1].to_dict()
            latest.update(
                {
                    "report_end_date": _fmt_trade_date(str(row.get("end_date", ""))),
                    "ann_date": _fmt_trade_date(str(row.get("ann_date", ""))),
                    "roe": _num(row.get("roe")),
                    "roe_dt": _num(row.get("roe_dt")),
                    "revenue_growth_yoy": _num(row.get("or_yoy")),
                    "net_profit_growth_yoy": _num(row.get("netprofit_yoy")),
                    "gross_margin": _num(row.get("grossprofit_margin")),
                }
            )
        if income is not None and not income.empty:
            row = income.sort_values(["end_date", "ann_date"]).iloc[-1].to_dict()
            latest.update(
                {
                    "revenue": _num(row.get("revenue")),
                    "net_profit_parent": _num(row.get("n_income_attr_p")),
                    "total_profit": _num(row.get("total_profit")),
                }
            )
        result["latest"] = latest
        return result

    def fetch_announcements(self, symbol: str, start_date: date, end_date: date) -> list[dict]:
        rows: list[dict] = []
        df = _safe_df(
            lambda: self.pro.anns_d(
                ts_code=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                fields="ts_code,ann_date,name,title,url",
            ),
            "anns_d",
            [],
        )
        if df is None or df.empty:
            return rows
        for row in df.sort_values("ann_date", ascending=False).head(10).to_dict("records"):
            rows.append(
                {
                    "date": _fmt_trade_date(str(row.get("ann_date", ""))),
                    "title": row.get("title"),
                    "type": "公告",
                    "url": row.get("url"),
                    "source": "tushare.anns_d",
                }
            )
        return rows

    def fetch_moneyflow(self, symbol: str, start_date: date, end_date: date) -> dict:
        gaps: list[str] = []
        df = _safe_df(
            lambda: self.pro.moneyflow(
                ts_code=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            ),
            "moneyflow",
            gaps,
        )
        if df is None or df.empty:
            return {"source": "tushare.moneyflow", "latest": {}, "gaps": gaps or ["moneyflow_empty"]}
        df = df.sort_values("trade_date")
        latest = df.iloc[-1].to_dict()
        net_cols = [c for c in df.columns if c.startswith("net_mf")]
        net_col = "net_mf_amount" if "net_mf_amount" in df.columns else net_cols[0] if net_cols else None
        recent = df.tail(5)
        net_5d = _num(recent[net_col].sum()) if net_col else None
        return {
            "source": "tushare.moneyflow",
            "latest": {
                "trade_date": _fmt_trade_date(str(latest.get("trade_date", ""))),
                "net_amount": _num(latest.get(net_col)) if net_col else None,
                "net_amount_5d": net_5d,
            },
            "gaps": gaps,
        }

    def fetch_market_context(self, trade_date: str | None = None, symbol: str | None = None) -> dict:
        gaps: list[str] = []
        indices = []
        end = _compact_date(trade_date) if trade_date else date.today().strftime("%Y%m%d")
        start = (date.fromisoformat(_fmt_trade_date(end)) - timedelta(days=30)).strftime("%Y%m%d")
        for ts_code, name in [("000001.SH", "上证指数"), ("000300.SH", "沪深300"), ("000905.SH", "中证500")]:
            df = _safe_df(
                lambda ts_code=ts_code: self.pro.index_daily(
                    ts_code=ts_code,
                    start_date=start,
                    end_date=end,
                    fields="ts_code,trade_date,close,pct_chg",
                ),
                f"index_daily:{ts_code}",
                gaps,
            )
            if df is not None and not df.empty:
                row = df.sort_values("trade_date").iloc[-1].to_dict()
                indices.append(
                    {
                        "ts_code": ts_code,
                        "name": name,
                        "trade_date": _fmt_trade_date(str(row.get("trade_date", ""))),
                        "close": _num(row.get("close")),
                        "pct_chg": _num(row.get("pct_chg")),
                    }
                )
        sentiment = self._fetch_market_sentiment(trade_date, gaps)
        industry = self._fetch_industry_context(symbol, end, gaps)
        return {
            "source": "tushare.index_daily/tushare.sw_daily/tushare.limit_list_d",
            "indices": indices,
            "industry": industry,
            "sentiment": sentiment,
            "gaps": gaps,
        }

    def _fetch_industry_context(self, symbol: str | None, trade_date: str, gaps: list[str]) -> dict:
        mapping = self._resolve_industry_index(symbol, gaps)
        if not mapping:
            return {
                "status": "not_configured",
                "note": "Tushare 行业分类接口未返回行业映射，且本地配置未命中。",
            }
        cache_key = f"industry_{mapping['ts_code']}_{trade_date}"
        cached = _read_cache(cache_key)
        if cached:
            return cached
        df = _safe_df(
            lambda: self.pro.sw_daily(
                ts_code=mapping["ts_code"],
                trade_date=trade_date,
                fields="ts_code,name,trade_date,close,pct_change",
            ),
            f"sw_daily:{mapping['ts_code']}",
            gaps,
        )
        if df is None or df.empty:
            return {
                "status": "failed",
                "ts_code": mapping["ts_code"],
                "name": mapping.get("name"),
                "note": "行业指数接口未返回数据，已记录到数据缺口。",
            }
        row = df.sort_values("trade_date").iloc[-1].to_dict()
        result = {
            "status": "ok",
            "ts_code": row.get("ts_code") or mapping["ts_code"],
            "name": row.get("name") or mapping.get("name"),
            "trade_date": _fmt_trade_date(str(row.get("trade_date", ""))),
            "close": _num(row.get("close")),
            "pct_chg": _num(row.get("pct_change")),
            "source": "tushare.sw_daily",
            "mapping_source": mapping.get("source"),
        }
        _write_cache(cache_key, result)
        return result

    def _resolve_industry_index(self, symbol: str | None, gaps: list[str]) -> dict[str, Any] | None:
        if not symbol:
            return None
        cache_key = f"industry_mapping_{symbol}"
        cached = _read_cache(cache_key)
        if cached:
            return cached
        df = _safe_df(
            lambda: self.pro.index_member_all(
                ts_code=symbol,
                fields="l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,ts_code,name,is_new",
            ),
            "index_member_all",
            gaps,
        )
        if df is None or df.empty:
            return _load_industry_index_map(symbol)
        current = df[df["is_new"] == "Y"] if "is_new" in df.columns else df
        if current.empty:
            current = df
        row = current.iloc[0].to_dict()
        if not row.get("l1_code"):
            return _load_industry_index_map(symbol)
        result = {
            "ts_code": row.get("l1_code"),
            "name": row.get("l1_name"),
            "source": "tushare.index_member_all",
            "stock": row.get("name"),
            "stock_code": row.get("ts_code") or symbol,
            "level2_code": row.get("l2_code"),
            "level2_name": row.get("l2_name"),
            "level3_code": row.get("l3_code"),
            "level3_name": row.get("l3_name"),
        }
        _write_cache(cache_key, result)
        return result

    def _fetch_market_sentiment(self, trade_date: str | None, gaps: list[str]) -> dict:
        if not trade_date:
            return {}
        compact = _compact_date(trade_date)
        cache_key = f"market_sentiment_{compact}"
        cached = _read_cache(cache_key)
        if cached:
            return cached
        df = _safe_df(
            lambda: self.pro.limit_list_d(
                trade_date=compact,
                fields="trade_date,ts_code,name,pct_chg,limit",
            ),
            "limit_list_d",
            gaps,
        )
        if df is None or df.empty:
            return {}
        limit_values = [str(v) for v in df.get("limit", [])]
        up = sum(1 for v in limit_values if "U" in v.upper() or "涨" in v)
        down = sum(1 for v in limit_values if "D" in v.upper() or "跌" in v)
        result = {
            "trade_date": trade_date,
            "limit_up_count": up,
            "limit_down_count": down,
            "sample_size": int(len(df)),
            "source": "tushare.limit_list_d",
        }
        _write_cache(cache_key, result)
        return result


class StaticProvider:
    def __init__(self, bars: list[DailyBar], basic: dict | None = None) -> None:
        self.bars = bars
        self.basic = basic or {}

    def fetch_daily_bars(self, symbol: str, start_date: date, end_date: date) -> list[DailyBar]:
        return [bar for bar in self.bars if start_date.isoformat() <= bar.date <= end_date.isoformat()]

    def fetch_stock_list(self) -> list[dict]:
        return list(self.basic.get("stock_list") or [])

    def fetch_basic(self, symbol: str, trade_date: str | None = None) -> dict:
        return dict(self.basic)

    def fetch_financials(self, symbol: str, start_date: date, end_date: date) -> dict:
        return dict(self.basic.get("financials") or {"source": "static", "latest": {}, "gaps": []})

    def fetch_announcements(self, symbol: str, start_date: date, end_date: date) -> list[dict]:
        return list(self.basic.get("announcements") or [])

    def fetch_moneyflow(self, symbol: str, start_date: date, end_date: date) -> dict:
        return dict(self.basic.get("moneyflow") or {"source": "static", "latest": {}, "gaps": []})

    def fetch_market_context(self, trade_date: str | None = None, symbol: str | None = None) -> dict:
        return dict(
            self.basic.get("market_context")
            or {
                "source": "static",
                "indices": [],
                "industry": {"status": "not_configured"},
                "sentiment": {},
                "gaps": [],
            }
        )


def default_provider() -> MarketDataProvider:
    return TushareProvider()


def _fmt_trade_date(value: str) -> str:
    if len(value) < 8:
        return value
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def _compact_date(value: str) -> str:
    return value.replace("-", "")


def _num(value):
    try:
        if value is None:
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _safe_df(call: Callable[[], Any], label: str, gaps: list[str]):
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 - 外部数据源失败必须降级为审计缺口
        gaps.append(_gap_code(label, exc))
        return None


def _gap_code(label: str, exc: Exception) -> str:
    message = str(exc)
    if "频率超限" in message:
        return f"{label}_rate_limited"
    if "权限" in message or "没有权限" in message:
        return f"{label}_permission_denied"
    if "接口名" in message:
        return f"{label}_invalid_interface"
    return f"{label}_failed:{exc.__class__.__name__}"


def _load_industry_index_map(symbol: str | None) -> dict[str, Any] | None:
    if not symbol or not INDUSTRY_INDEX_MAP_PATH.exists():
        return None
    try:
        data = json.loads(INDUSTRY_INDEX_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = (data.get("symbol_to_index") or {}).get(symbol)
    if isinstance(value, str):
        return {"ts_code": value, "source": "config"}
    if isinstance(value, dict) and value.get("ts_code"):
        return value
    return None


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

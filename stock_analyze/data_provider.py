from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from .models import DailyBar
from .sentiment import fetch_market_sentiment

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

    def consume_data_gaps(self) -> list[str]:
        ...


class TushareProvider:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("TUSHARE_TOKEN", "")
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN 未设置，无法使用 Tushare 拉取数据。")
        import tushare as ts

        self.pro = ts.pro_api(self.token)
        self._data_gaps: list[str] = []

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
        self._data_gaps = []
        start = start_date.strftime("%Y%m%d")
        end = end_date.strftime("%Y%m%d")
        df = self.pro.daily(
            ts_code=symbol,
            start_date=start,
            end_date=end,
        )
        if df is None or df.empty:
            raise RuntimeError(f"Tushare 未返回日线数据：{symbol}")
        df = df.sort_values("trade_date")
        adj_by_date = self._fetch_adj_factor_map(symbol, start, end)
        latest_adj = _latest_adj_factor(adj_by_date)
        limit_by_date = self._fetch_stk_limit_map(symbol, start, end)
        bars: list[DailyBar] = []
        for row in df.to_dict("records"):
            trade_date = str(row["trade_date"])
            close = _num(row.get("close"))
            adj_factor = adj_by_date.get(trade_date)
            qfq_ratio = adj_factor / latest_adj if adj_factor is not None and latest_adj else None
            limit = limit_by_date.get(trade_date) or {}
            bars.append(
                DailyBar(
                    date=_fmt_trade_date(trade_date),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("vol") or 0),
                    amount=float(row.get("amount") or 0),
                    adj_factor=adj_factor,
                    qfq_open=_qfq(row.get("open"), qfq_ratio),
                    qfq_high=_qfq(row.get("high"), qfq_ratio),
                    qfq_low=_qfq(row.get("low"), qfq_ratio),
                    qfq_close=_qfq(row.get("close"), qfq_ratio),
                    limit_up=limit.get("limit_up"),
                    limit_down=limit.get("limit_down"),
                    pct_to_limit_up=_pct_to_limit_up(close, limit.get("limit_up")),
                    pct_to_limit_down=_pct_to_limit_down(close, limit.get("limit_down")),
                )
            )
        if adj_by_date and len(adj_by_date) < len(bars):
            self._record_gap("adj_factor_partial_missing")
        if limit_by_date and len(limit_by_date) < len(bars):
            self._record_gap("stk_limit_partial_missing")
        return bars

    def _fetch_adj_factor_map(self, symbol: str, start: str, end: str) -> dict[str, float]:
        df = _safe_df(
            lambda: self.pro.adj_factor(ts_code=symbol, start_date=start, end_date=end, fields="ts_code,trade_date,adj_factor"),
            "adj_factor",
            self._data_gaps,
        )
        if df is None or df.empty:
            self._record_gap("adj_factor_empty_or_unavailable")
            return {}
        result: dict[str, float] = {}
        for row in df.to_dict("records"):
            value = _num(row.get("adj_factor"))
            if value is not None:
                result[str(row.get("trade_date"))] = value
        if not result:
            self._record_gap("adj_factor_empty_or_unavailable")
        return result

    def _fetch_stk_limit_map(self, symbol: str, start: str, end: str) -> dict[str, dict[str, float | None]]:
        df = _safe_df(
            lambda: self.pro.stk_limit(
                ts_code=symbol,
                start_date=start,
                end_date=end,
                fields="ts_code,trade_date,up_limit,down_limit",
            ),
            "stk_limit",
            self._data_gaps,
        )
        if df is None or df.empty:
            self._record_gap("stk_limit_empty_or_unavailable")
            return {}
        result: dict[str, dict[str, float | None]] = {}
        for row in df.to_dict("records"):
            result[str(row.get("trade_date"))] = {
                "limit_up": _num(row.get("up_limit")),
                "limit_down": _num(row.get("down_limit")),
            }
        return result

    def fetch_basic(self, symbol: str, trade_date: str | None = None) -> dict:
        fields = "ts_code,trade_date,total_mv,circ_mv,pe_ttm,pb"
        kwargs = {"ts_code": symbol, "fields": fields}
        if trade_date:
            kwargs["trade_date"] = trade_date.replace("-", "")
        df = self.pro.daily_basic(**kwargs)
        if df is None or df.empty:
            self._record_gap("daily_basic_empty_or_unavailable")
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
        balance = _safe_df(
            lambda: self.pro.balancesheet(
                ts_code=symbol,
                start_date=start,
                end_date=end,
                fields=(
                    "ts_code,ann_date,end_date,total_assets,total_liab,money_cap,accounts_receiv,"
                    "inventories,goodwill,st_borr,lt_borr,bond_payable,non_cur_liab_due_1y"
                ),
            ),
            "balancesheet",
            result["gaps"],
        )
        cashflow = _safe_df(
            lambda: self.pro.cashflow(
                ts_code=symbol,
                start_date=start,
                end_date=end,
                fields=(
                    "ts_code,ann_date,end_date,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,"
                    "c_pay_acq_const_fiolta"
                ),
            ),
            "cashflow",
            result["gaps"],
        )
        latest: dict[str, Any] = {}
        net_profit_parent = None
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
            net_profit_parent = latest.get("net_profit_parent")
        if balance is not None and not balance.empty:
            row = balance.sort_values(["end_date", "ann_date"]).iloc[-1].to_dict()
            total_assets = _num(row.get("total_assets"))
            total_liab = _num(row.get("total_liab"))
            interest_debt = _sum_nums(
                row.get("st_borr"), row.get("lt_borr"), row.get("bond_payable"), row.get("non_cur_liab_due_1y")
            )
            latest.update(
                {
                    "asset_liability_ratio": _ratio(total_liab, total_assets),
                    "money_cap": _num(row.get("money_cap")),
                    "accounts_receiv": _num(row.get("accounts_receiv")),
                    "inventories": _num(row.get("inventories")),
                    "goodwill": _num(row.get("goodwill")),
                    "interest_bearing_debt": interest_debt,
                    "total_assets": total_assets,
                    "total_liab": total_liab,
                }
            )
        else:
            result["gaps"].append("balancesheet_empty_or_unavailable")
        if cashflow is not None and not cashflow.empty:
            row = cashflow.sort_values(["end_date", "ann_date"]).iloc[-1].to_dict()
            operating_cashflow = _num(row.get("n_cashflow_act"))
            capex = _num(row.get("c_pay_acq_const_fiolta"))
            latest.update(
                {
                    "operating_cashflow": operating_cashflow,
                    "investing_cashflow": _num(row.get("n_cashflow_inv_act")),
                    "financing_cashflow": _num(row.get("n_cash_flows_fnc_act")),
                    "capex": capex,
                    "free_cashflow": _subtract(operating_cashflow, capex),
                    "operating_cashflow_to_net_profit": _ratio(operating_cashflow, net_profit_parent),
                }
            )
        else:
            result["gaps"].append("cashflow_empty_or_unavailable")
        result["reserved"] = _empty_tushare_reserved()
        result["latest"] = latest
        return result

    def consume_data_gaps(self) -> list[str]:
        gaps = sorted(set(getattr(self, "_data_gaps", [])))
        self._data_gaps = []
        return gaps

    def _record_gap(self, gap: str) -> None:
        if not hasattr(self, "_data_gaps"):
            self._data_gaps = []
        self._data_gaps.append(gap)

    def fetch_announcements(self, symbol: str, start_date: date, end_date: date) -> list[dict]:
        rows: list[dict] = []
        gaps: list[str] = []
        df = _safe_df(
            lambda: self.pro.anns_d(
                ts_code=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                fields="ts_code,ann_date,name,title,url",
            ),
            "anns_d",
            gaps,
        )
        if df is not None and not df.empty:
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
        if rows:
            return rows
        fallback = self._fetch_disclosure_events(symbol, start_date, end_date)
        if fallback:
            return fallback
        self._data_gaps.extend(gaps)
        return rows

    def _fetch_disclosure_events(self, symbol: str, start_date: date, end_date: date) -> list[dict]:
        gaps: list[str] = []
        df = _safe_df(
            lambda: self.pro.disclosure_date(
                ts_code=symbol,
                fields="ts_code,ann_date,end_date,pre_date,actual_date,modify_date",
            ),
            "disclosure_date",
            gaps,
        )
        if df is None or df.empty:
            self._data_gaps.extend(gaps)
            return []
        rows: list[dict] = []
        start = start_date.strftime("%Y%m%d")
        end = end_date.strftime("%Y%m%d")
        records = []
        for row in df.to_dict("records"):
            ann_date = str(row.get("ann_date") or row.get("actual_date") or row.get("pre_date") or row.get("end_date") or "")
            if not ann_date or start <= ann_date <= end:
                records.append(row)
        if not records:
            records = df.to_dict("records")
        for row in sorted(records, key=lambda item: (str(item.get("ann_date") or ""), str(item.get("end_date") or "")), reverse=True)[:10]:
            ann_date = row.get("ann_date") or row.get("actual_date") or row.get("pre_date") or row.get("end_date")
            report_end = _fmt_trade_date(str(row.get("end_date", "")))
            rows.append(
                {
                    "date": _fmt_trade_date(str(ann_date)),
                    "title": f"{report_end} 财报披露日期记录",
                    "type": "财报披露",
                    "url": None,
                    "source": "tushare.disclosure_date",
                    "data_quality": "fallback",
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
        sentiment = fetch_market_sentiment(self.pro, end)
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
        primary_gaps: list[str] = []
        df = _safe_df(
            lambda: self.pro.sw_daily(
                ts_code=mapping["ts_code"],
                trade_date=trade_date,
                fields="ts_code,name,trade_date,close,pct_change",
            ),
            f"sw_daily:{mapping['ts_code']}",
            primary_gaps,
        )
        source = "tushare.sw_daily"
        pct_col = "pct_change"
        if df is None or df.empty:
            fallback_gaps: list[str] = []
            df = _safe_df(
                lambda: self.pro.index_daily(
                    ts_code=mapping["ts_code"],
                    trade_date=trade_date,
                    fields="ts_code,trade_date,close,pct_chg",
                ),
                f"index_daily_industry:{mapping['ts_code']}",
                fallback_gaps,
            )
            source = "tushare.index_daily"
            pct_col = "pct_chg"
            if df is None or df.empty:
                cached_latest = _read_latest_cache_prefix(f"industry_{mapping['ts_code']}_")
                if cached_latest:
                    cached_latest["data_quality"] = "cached_stale"
                    cached_latest["note"] = "本次行业指数接口不可用，已使用本地历史缓存。"
                    return cached_latest
                gaps.extend(primary_gaps + fallback_gaps)
                return {
                    "status": "failed",
                    "ts_code": mapping["ts_code"],
                    "name": mapping.get("name"),
                    "note": "行业指数接口未返回数据，已记录到数据缺口。",
                }
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
            "pct_chg": _num(row.get(pct_col)),
            "source": source,
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

    def consume_data_gaps(self) -> list[str]:
        return list(self.basic.get("data_gaps") or [])


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


def _latest_adj_factor(adj_by_date: dict[str, float]) -> float | None:
    if not adj_by_date:
        return None
    latest_date = sorted(adj_by_date)[-1]
    return adj_by_date.get(latest_date)


def _qfq(value, ratio: float | None) -> float | None:
    num = _num(value)
    if num is None or ratio is None:
        return None
    return round(num * ratio, 4)


def _pct_to_limit_up(close: float | None, limit_up: float | None) -> float | None:
    if close is None or limit_up is None or close <= 0:
        return None
    return round((limit_up / close - 1) * 100, 4)


def _pct_to_limit_down(close: float | None, limit_down: float | None) -> float | None:
    if close is None or limit_down is None or limit_down <= 0:
        return None
    return round((close / limit_down - 1) * 100, 4)


def _sum_nums(*values) -> float | None:
    nums = [_num(value) for value in values]
    present = [value for value in nums if value is not None]
    if not present:
        return None
    return round(sum(present), 4)


def _subtract(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(left - right, 4)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 4)


def _empty_tushare_reserved() -> dict[str, list[dict]]:
    return {
        "fina_mainbz": [],
        "forecast": [],
        "express": [],
        "dividend": [],
        "disclosure_date": [],
        "top_list": [],
        "top_inst": [],
        "margin": [],
        "margin_detail": [],
        "moneyflow_hsgt": [],
        "hsgt_top10": [],
        "index_dailybasic": [],
        "index_classify": [],
        "index_member": [],
        "concept": [],
        "concept_detail": [],
    }


def _safe_df(call: Callable[[], Any], label: str, gaps: list[str]):
    last_exc: Exception | None = None
    for delay in _retry_schedule():
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - 外部数据源失败必须降级为审计缺口
            last_exc = exc
            if not _is_retryable_error(exc) or delay is None:
                break
            if delay > 0:
                time.sleep(delay)
    if last_exc is not None:
        gaps.append(_gap_code(label, last_exc))
        return None
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 - 外部数据源失败必须降级为审计缺口
        gaps.append(_gap_code(label, exc))
        return None


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
    non_retry_markers = ["权限", "没有权限", "permission", "接口名"]
    if any(marker in message for marker in non_retry_markers):
        return False
    return any(marker in message for marker in retry_markers)


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


def _read_latest_cache_prefix(prefix: str) -> dict[str, Any] | None:
    cache_prefix = _cache_path(prefix).name.removesuffix(".json")
    if not CACHE_DIR.exists():
        return None
    paths = sorted(CACHE_DIR.glob(f"{cache_prefix}*.json"), reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _write_cache(key: str, data: dict[str, Any]) -> None:
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

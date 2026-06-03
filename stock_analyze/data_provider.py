from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Callable, Protocol

from .models import DailyBar


class MarketDataProvider(Protocol):
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

    def fetch_market_context(self, trade_date: str | None = None) -> dict:
        ...


class TushareProvider:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("TUSHARE_TOKEN", "")
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN 未设置，无法使用 Tushare 拉取数据。")
        import tushare as ts

        self.pro = ts.pro_api(self.token)

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
            lambda: self.pro.anns(
                ts_code=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                fields="ts_code,ann_date,title,type,url",
            ),
            "anns",
            [],
        )
        if df is None or df.empty:
            return rows
        for row in df.sort_values("ann_date", ascending=False).head(10).to_dict("records"):
            rows.append(
                {
                    "date": _fmt_trade_date(str(row.get("ann_date", ""))),
                    "title": row.get("title"),
                    "type": row.get("type"),
                    "url": row.get("url"),
                    "source": "tushare.anns",
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

    def fetch_market_context(self, trade_date: str | None = None) -> dict:
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
        return {
            "source": "tushare.index_daily/tushare.limit_list_d",
            "indices": indices,
            "industry": {
                "status": "not_configured",
                "note": "行业指数需配置 symbol 到行业指数代码的映射后精确拉取。",
            },
            "sentiment": sentiment,
            "gaps": gaps,
        }

    def _fetch_market_sentiment(self, trade_date: str | None, gaps: list[str]) -> dict:
        if not trade_date:
            return {}
        compact = _compact_date(trade_date)
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
        return {
            "trade_date": trade_date,
            "limit_up_count": up,
            "limit_down_count": down,
            "sample_size": int(len(df)),
        }


class AkshareProvider:
    def fetch_daily_bars(self, symbol: str, start_date: date, end_date: date) -> list[DailyBar]:
        import akshare as ak

        code = symbol.split(".")[0]
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="qfq",
        )
        if df is None or df.empty:
            raise RuntimeError(f"Akshare 未返回日线数据：{symbol}")
        bars: list[DailyBar] = []
        for row in df.sort_values("日期").to_dict("records"):
            bars.append(
                DailyBar(
                    date=str(row["日期"]),
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=float(row["成交量"]),
                    amount=float(row.get("成交额") or 0),
                )
            )
        return bars

    def fetch_basic(self, symbol: str, trade_date: str | None = None) -> dict:
        return {"source": "akshare", "note": "Akshare fallback 未拉取估值字段"}

    def fetch_financials(self, symbol: str, start_date: date, end_date: date) -> dict:
        return {"source": "akshare", "latest": {}, "gaps": ["akshare_financials_not_configured"]}

    def fetch_announcements(self, symbol: str, start_date: date, end_date: date) -> list[dict]:
        return []

    def fetch_moneyflow(self, symbol: str, start_date: date, end_date: date) -> dict:
        return {"source": "akshare", "latest": {}, "gaps": ["akshare_moneyflow_not_configured"]}

    def fetch_market_context(self, trade_date: str | None = None) -> dict:
        return {
            "source": "akshare",
            "indices": [],
            "industry": {"status": "not_configured"},
            "sentiment": {},
            "gaps": ["akshare_market_context_not_configured"],
        }


class StaticProvider:
    def __init__(self, bars: list[DailyBar], basic: dict | None = None) -> None:
        self.bars = bars
        self.basic = basic or {}

    def fetch_daily_bars(self, symbol: str, start_date: date, end_date: date) -> list[DailyBar]:
        return [bar for bar in self.bars if start_date.isoformat() <= bar.date <= end_date.isoformat()]

    def fetch_basic(self, symbol: str, trade_date: str | None = None) -> dict:
        return dict(self.basic)

    def fetch_financials(self, symbol: str, start_date: date, end_date: date) -> dict:
        return dict(self.basic.get("financials") or {"source": "static", "latest": {}, "gaps": []})

    def fetch_announcements(self, symbol: str, start_date: date, end_date: date) -> list[dict]:
        return list(self.basic.get("announcements") or [])

    def fetch_moneyflow(self, symbol: str, start_date: date, end_date: date) -> dict:
        return dict(self.basic.get("moneyflow") or {"source": "static", "latest": {}, "gaps": []})

    def fetch_market_context(self, trade_date: str | None = None) -> dict:
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
    if os.environ.get("TUSHARE_TOKEN"):
        return TushareProvider()
    return AkshareProvider()


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
        gaps.append(f"{label}_failed:{exc.__class__.__name__}")
        return None

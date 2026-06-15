from datetime import date
from types import SimpleNamespace

import pandas as pd

import stock_analyze.data_provider as data_provider
from stock_analyze.data_provider import TushareProvider


class FakePro:
    def index_member_all(self, **kwargs):
        assert kwargs["ts_code"] == "301366.SZ"
        return pd.DataFrame(
            [
                {
                    "l1_code": "801080.SI",
                    "l1_name": "电子",
                    "l2_code": "801083.SI",
                    "l2_name": "元件",
                    "l3_code": "850822.SI",
                    "l3_name": "印制电路板",
                    "ts_code": "301366.SZ",
                    "name": "一博科技",
                    "is_new": "Y",
                }
            ]
        )

    def sw_daily(self, **kwargs):
        assert kwargs["ts_code"] == "801080.SI"
        return pd.DataFrame(
            [
                {
                    "ts_code": "801080.SI",
                    "name": "电子",
                    "trade_date": "20260602",
                    "close": 4000.12,
                    "pct_change": 1.23,
                }
            ]
        )

    def index_daily(self, **kwargs):
        raise AssertionError("sw_daily 成功时不应调用 index_daily 兜底")


def test_fetch_industry_context_auto_resolves_sw_index(tmp_path, monkeypatch):
    monkeypatch.setattr(data_provider, "CACHE_DIR", tmp_path / "data_cache")
    monkeypatch.setattr(data_provider, "INDUSTRY_INDEX_MAP_PATH", tmp_path / "missing.json")
    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = FakePro()
    gaps = []

    industry = provider._fetch_industry_context("301366.SZ", "20260602", gaps)

    assert gaps == []
    assert industry["status"] == "ok"
    assert industry["ts_code"] == "801080.SI"
    assert industry["name"] == "电子"
    assert industry["trade_date"] == "2026-06-02"
    assert industry["pct_chg"] == 1.23


class FallbackIndustryPro(FakePro):
    def sw_daily(self, **kwargs):
        raise RuntimeError("没有权限")

    def index_daily(self, **kwargs):
        assert kwargs["ts_code"] == "801080.SI"
        return pd.DataFrame(
            [
                {
                    "ts_code": "801080.SI",
                    "trade_date": "20260602",
                    "close": 3999.8,
                    "pct_chg": 0.9,
                }
            ]
        )


def test_fetch_industry_context_falls_back_to_index_daily(tmp_path, monkeypatch):
    monkeypatch.setattr(data_provider, "CACHE_DIR", tmp_path / "data_cache")
    monkeypatch.setattr(data_provider, "INDUSTRY_INDEX_MAP_PATH", tmp_path / "missing.json")
    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = FallbackIndustryPro()
    gaps = []

    industry = provider._fetch_industry_context("301366.SZ", "20260602", gaps)

    assert gaps == []
    assert industry["status"] == "ok"
    assert industry["source"] == "tushare.index_daily"
    assert industry["close"] == 3999.8
    assert industry["pct_chg"] == 0.9


class AkshareIndustryPro(FallbackIndustryPro):
    def index_daily(self, **kwargs):
        return pd.DataFrame()


def test_fetch_industry_context_falls_back_to_akshare_sw_index(tmp_path, monkeypatch):
    monkeypatch.setattr(data_provider, "CACHE_DIR", tmp_path / "data_cache")
    monkeypatch.setattr(data_provider, "INDUSTRY_INDEX_MAP_PATH", tmp_path / "missing.json")

    fake_ak = SimpleNamespace(
        index_hist_sw=lambda **kwargs: pd.DataFrame(
            [
                {"代码": "801080", "日期": date(2026, 6, 1), "收盘": 3900.0},
                {"代码": "801080", "日期": date(2026, 6, 2), "收盘": 4000.0},
            ]
        )
    )
    monkeypatch.setattr(data_provider, "_load_akshare", lambda: fake_ak)

    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = AkshareIndustryPro()
    provider._data_gaps = []
    gaps = []

    industry = provider._fetch_industry_context("301366.SZ", "20260602", gaps)

    assert gaps == []
    assert provider.consume_data_gaps() == []
    assert industry["status"] == "ok"
    assert industry["source"] == "akshare.index_hist_sw"
    assert industry["data_quality"] == "fallback"
    assert industry["close"] == 4000.0
    assert industry["pct_chg"] == 2.5641


class MarketContextFallbackPro:
    def index_daily(self, **kwargs):
        if kwargs["ts_code"] == "399001.SZ":
            raise ConnectionError("index failed")
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs["ts_code"],
                    "trade_date": "20260601",
                    "close": 100.0,
                    "pct_chg": 0.1,
                    "vol": 1000,
                    "amount": 10000,
                },
                {
                    "ts_code": kwargs["ts_code"],
                    "trade_date": "20260602",
                    "close": 101.0,
                    "pct_chg": 1.0,
                    "vol": 1100,
                    "amount": 12000,
                },
            ]
        )

    def limit_list_d(self, **kwargs):
        return pd.DataFrame([{"trade_date": kwargs["trade_date"], "ts_code": "000001.SZ", "limit": "U"}])

    def index_member_all(self, **kwargs):
        return pd.DataFrame()


def test_fetch_market_context_falls_back_to_akshare_index_without_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(data_provider, "CACHE_DIR", tmp_path / "data_cache")
    monkeypatch.setattr(data_provider, "INDUSTRY_INDEX_MAP_PATH", tmp_path / "missing.json")
    monkeypatch.setenv("TUSHARE_RETRY_DELAYS", "0")
    fake_ak = SimpleNamespace(
        stock_zh_index_daily_em=lambda **kwargs: pd.DataFrame(
            [
                {"date": date(2026, 6, 1), "close": 200.0, "amount": 20000},
                {"date": date(2026, 6, 2), "close": 202.0, "amount": 23000},
            ]
        )
    )
    monkeypatch.setattr(data_provider, "_load_akshare", lambda: fake_ak)

    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = MarketContextFallbackPro()

    context = provider.fetch_market_context("2026-06-02", "601127.SH")

    sz_index = next(item for item in context["indices"] if item["ts_code"] == "399001.SZ")
    assert sz_index["source"] == "akshare.stock_zh_index_daily_em"
    assert sz_index["data_quality"] == "fallback"
    assert sz_index["close"] == 202.0
    assert not any(str(gap).startswith("index_daily:399001.SZ") for gap in context["gaps"])


class DisclosureFallbackPro:
    def anns_d(self, **kwargs):
        raise RuntimeError("没有权限")

    def disclosure_date(self, **kwargs):
        assert "start_date" not in kwargs
        assert "end_date" not in kwargs
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs["ts_code"],
                    "ann_date": "20260420",
                    "end_date": "20260331",
                    "pre_date": "20260418",
                    "actual_date": "20260420",
                    "modify_date": None,
                }
            ]
        )


def test_fetch_announcements_falls_back_to_disclosure_date():
    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = DisclosureFallbackPro()
    provider._data_gaps = []

    rows = provider.fetch_announcements("601728.SH", date(2026, 1, 1), date(2026, 6, 2))

    assert rows[0]["source"] == "tushare.disclosure_date"
    assert rows[0]["type"] == "财报披露"
    assert provider.consume_data_gaps() == []


def test_fetch_announcements_falls_back_to_akshare(monkeypatch):
    fake_ak = SimpleNamespace(
        stock_individual_notice_report=lambda **kwargs: pd.DataFrame(
            [
                {
                    "代码": "601728",
                    "名称": "中国电信",
                    "公告标题": "中国电信年度报告",
                    "公告类型": "财务报告",
                    "公告日期": date(2026, 4, 20),
                    "网址": "https://example.com/notice",
                }
            ]
        )
    )
    monkeypatch.setattr(data_provider, "_load_akshare", lambda: fake_ak)

    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = DisclosureFallbackPro()
    provider._data_gaps = []

    rows = provider.fetch_announcements("601728.SH", date(2026, 1, 1), date(2026, 6, 2))

    assert rows[0]["source"] == "akshare.stock_individual_notice_report"
    assert rows[0]["title"] == "中国电信年度报告"
    assert rows[0]["date"] == "2026-04-20"
    assert provider.consume_data_gaps() == []


def test_safe_df_retries_rate_limited_error(monkeypatch):
    monkeypatch.setenv("TUSHARE_RETRY_DELAYS", "0,0")
    calls = {"count": 0}

    def flaky_call():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("频率超限")
        return pd.DataFrame([{"value": 1}])

    gaps = []
    df = data_provider._safe_df(flaky_call, "retryable", gaps)

    assert calls["count"] == 3
    assert gaps == []
    assert df.to_dict("records") == [{"value": 1}]


class FakeDailyPro:
    def daily(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs["ts_code"],
                    "trade_date": "20260601",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.0,
                    "pct_chg": 0.0,
                    "vol": 1000,
                    "amount": 10000,
                },
                {
                    "ts_code": kwargs["ts_code"],
                    "trade_date": "20260602",
                    "open": 20.0,
                    "high": 22.0,
                    "low": 19.0,
                    "close": 20.0,
                    "pct_chg": 100.0,
                    "vol": 1100,
                    "amount": 22000,
                },
            ]
        )

    def adj_factor(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": kwargs["ts_code"], "trade_date": "20260601", "adj_factor": 1.0},
                {"ts_code": kwargs["ts_code"], "trade_date": "20260602", "adj_factor": 2.0},
            ]
        )

    def stk_limit(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": kwargs["ts_code"], "trade_date": "20260601", "up_limit": 11.0, "down_limit": 9.0},
                {"ts_code": kwargs["ts_code"], "trade_date": "20260602", "up_limit": 22.0, "down_limit": 18.0},
            ]
        )

    def daily_basic(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": kwargs["ts_code"], "trade_date": "20260601", "turnover_rate": 1.1, "turnover_rate_f": 1.2, "volume_ratio": 0.9, "total_mv": 1000, "circ_mv": 900},
                {"ts_code": kwargs["ts_code"], "trade_date": "20260602", "turnover_rate": 1.3, "turnover_rate_f": 1.4, "volume_ratio": 1.1, "total_mv": 1100, "circ_mv": 990},
            ]
        )


def test_fetch_daily_bars_merges_adj_factor_and_stk_limit():
    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = FakeDailyPro()

    bars = provider.fetch_daily_bars("600519.SH", date(2026, 6, 1), date(2026, 6, 2))

    assert bars[0].qfq_close == 5.0
    assert bars[1].qfq_close == 20.0
    assert bars[1].limit_up == 22.0
    assert bars[1].pct_to_limit_up == 10.0
    assert bars[1].pct_to_limit_down == 11.1111
    assert provider.consume_data_gaps() == []


class EmptyOptionalDailyPro(FakeDailyPro):
    def adj_factor(self, **kwargs):
        return pd.DataFrame()

    def stk_limit(self, **kwargs):
        return pd.DataFrame()


def test_fetch_daily_bars_records_optional_interface_empty_returns():
    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = EmptyOptionalDailyPro()

    bars = provider.fetch_daily_bars("600519.SH", date(2026, 6, 1), date(2026, 6, 2))

    assert bars[0].qfq_close is None
    assert bars[0].limit_up == 11.0
    assert bars[0].limit_source == "daily.pct_chg_estimate"
    assert provider.consume_data_gaps() == ["adj_factor_empty_or_unavailable"]


class FailingOptionalDailyPro(FakeDailyPro):
    def adj_factor(self, **kwargs):
        raise RuntimeError("权限不足")

    def stk_limit(self, **kwargs):
        raise RuntimeError("频率超限")


def test_fetch_daily_bars_records_optional_interface_failures(monkeypatch):
    monkeypatch.setenv("TUSHARE_RETRY_DELAYS", "0,0")
    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = FailingOptionalDailyPro()

    bars = provider.fetch_daily_bars("600519.SH", date(2026, 6, 1), date(2026, 6, 2))

    assert len(bars) == 2
    assert bars[1].limit_up == 11.0
    assert bars[1].limit_source == "daily.pct_chg_estimate"
    gaps = provider.consume_data_gaps()
    assert "adj_factor_permission_denied" in gaps
    assert "adj_factor_empty_or_unavailable" in gaps
    assert not any(gap.startswith("stk_limit") for gap in gaps)


class FakeFinancialPro:
    def fina_indicator(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs["ts_code"],
                    "ann_date": "20260420",
                    "end_date": "20260331",
                    "roe": 10,
                    "roe_dt": 9,
                    "or_yoy": 5,
                    "netprofit_yoy": 6,
                    "grossprofit_margin": 30,
                }
            ]
        )

    def income(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs["ts_code"],
                    "ann_date": "20260420",
                    "end_date": "20260331",
                    "revenue": 1000,
                    "n_income_attr_p": 100,
                    "total_profit": 120,
                }
            ]
        )

    def balancesheet(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs["ts_code"],
                    "ann_date": "20260420",
                    "end_date": "20260331",
                    "total_assets": 1000,
                    "total_liab": 760,
                    "money_cap": 80,
                    "accounts_receiv": 120,
                    "inventories": 90,
                    "goodwill": 130,
                    "st_borr": 40,
                    "lt_borr": 50,
                    "bond_payable": 20,
                    "non_cur_liab_due_1y": 10,
                }
            ]
        )

    def cashflow(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs["ts_code"],
                    "ann_date": "20260420",
                    "end_date": "20260331",
                    "n_cashflow_act": 50,
                    "n_cashflow_inv_act": -70,
                    "n_cash_flows_fnc_act": 20,
                    "c_pay_acq_const_fiolta": 80,
                }
            ]
        )


def test_fetch_financials_adds_balance_sheet_and_cashflow_metrics():
    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = FakeFinancialPro()

    financials = provider.fetch_financials("600519.SH", date(2026, 1, 1), date(2026, 6, 2))
    latest = financials["latest"]

    assert latest["asset_liability_ratio"] == 0.76
    assert latest["interest_bearing_debt"] == 120.0
    assert latest["free_cashflow"] == -30.0
    assert latest["operating_cashflow_to_net_profit"] == 0.5
    assert financials["reserved"]["dividend"] == []


class EmptyFinancialPro(FakeFinancialPro):
    def balancesheet(self, **kwargs):
        return pd.DataFrame()

    def cashflow(self, **kwargs):
        return pd.DataFrame()


def test_fetch_financials_records_empty_extended_interfaces():
    provider = TushareProvider.__new__(TushareProvider)
    provider.pro = EmptyFinancialPro()

    financials = provider.fetch_financials("600519.SH", date(2026, 1, 1), date(2026, 6, 2))

    assert "balancesheet_empty_or_unavailable" in financials["gaps"]
    assert "cashflow_empty_or_unavailable" in financials["gaps"]

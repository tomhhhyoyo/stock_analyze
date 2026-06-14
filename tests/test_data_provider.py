from datetime import date

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
    assert bars[0].limit_up is None
    assert provider.consume_data_gaps() == ["adj_factor_empty_or_unavailable", "stk_limit_empty_or_unavailable"]


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
    gaps = provider.consume_data_gaps()
    assert "adj_factor_permission_denied" in gaps
    assert "stk_limit_rate_limited" in gaps
    assert "adj_factor_empty_or_unavailable" in gaps
    assert "stk_limit_empty_or_unavailable" in gaps


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

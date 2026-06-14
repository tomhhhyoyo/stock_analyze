import pandas as pd
from types import SimpleNamespace

import stock_analyze.sentiment as sentiment
from stock_analyze.sentiment import fetch_market_sentiment


class LimitListDPro:
    def limit_list_d(self, **kwargs):
        return pd.DataFrame(
            [
                {"trade_date": "20260602", "ts_code": "000001.SZ", "name": "A", "limit": "U", "limit_times": 2},
                {"trade_date": "20260602", "ts_code": "000002.SZ", "name": "B", "limit": "D", "limit_times": 1},
                {"trade_date": "20260602", "ts_code": "000003.SZ", "name": "C", "limit": "炸板", "limit_times": 0},
            ]
        )


class ThsFallbackPro:
    def limit_list_d(self, **kwargs):
        raise RuntimeError("limit_list_d boom")

    def limit_list_ths(self, **kwargs):
        return pd.DataFrame(
            [
                {"trade_date": "20260602", "ts_code": "000001.SZ", "name": "A", "status": "涨停", "tag": "2天2板", "limit_order": 195311120},
                {"trade_date": "20260602", "ts_code": "000002.SZ", "name": "B", "status": "炸板", "tag": "首板", "limit_order": 88888888},
            ]
        )


class PriceFallbackPro:
    def limit_list_d(self, **kwargs):
        raise RuntimeError("limit_list_d failed")

    def limit_list_ths(self, **kwargs):
        raise ValueError("limit_list_ths failed")

    def stk_limit(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "up_limit": 11.0, "down_limit": 9.0},
                {"ts_code": "000002.SZ", "up_limit": 22.0, "down_limit": 18.0},
                {"ts_code": "000003.SZ", "up_limit": 33.0, "down_limit": 27.0},
                {"ts_code": "000004.SZ", "up_limit": 44.0, "down_limit": 36.0},
            ]
        )

    def daily(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "high": 11.0, "low": 10.0, "close": 11.0},
                {"ts_code": "000002.SZ", "high": 22.0, "low": 19.0, "close": 21.0},
                {"ts_code": "000003.SZ", "high": 30.0, "low": 27.0, "close": 27.0},
                {"ts_code": "000004.SZ", "high": 42.0, "low": 36.0, "close": 37.0},
            ]
        )


class AkshareFallbackPro:
    def limit_list_d(self, **kwargs):
        raise RuntimeError("没有权限")

    def limit_list_ths(self, **kwargs):
        raise RuntimeError("没有权限")


class AllFailPro:
    def limit_list_d(self, **kwargs):
        raise RuntimeError("limit_list_d failed")

    def limit_list_ths(self, **kwargs):
        raise ValueError("limit_list_ths failed")

    def stk_limit(self, **kwargs):
        raise PermissionError("stk_limit denied")


class DailyPctFallbackPro(AllFailPro):
    def daily(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "pct_chg": 10.0},
                {"ts_code": "300001.SZ", "pct_chg": 20.0},
                {"ts_code": "688001.SH", "pct_chg": -20.0},
                {"ts_code": "600001.SH", "pct_chg": -9.9},
                {"ts_code": "600002.SH", "pct_chg": 3.0},
            ]
        )


class RetryLimitListDPro:
    def __init__(self):
        self.calls = 0

    def limit_list_d(self, **kwargs):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("频率超限")
        return pd.DataFrame(
            [
                {"trade_date": "20260602", "ts_code": "000001.SZ", "name": "A", "limit": "U", "limit_times": 1},
            ]
        )


def test_limit_list_d_success(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)

    result = fetch_market_sentiment(LimitListDPro(), "20260602")

    assert result["source"] == "tushare.limit_list_d"
    assert result["up_limit_count"] == 1
    assert result["down_limit_count"] == 1
    assert result["limit_break_count"] == 1
    assert result["highest_limit_step"] == 2
    assert result["data_quality"] == "full"


def test_limit_list_d_fails_then_ths_success(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)

    result = fetch_market_sentiment(ThsFallbackPro(), "20260602")

    assert result["source"] == "tushare.limit_list_ths"
    assert result["up_limit_count"] == 1
    assert result["limit_break_count"] == 1
    assert result["highest_limit_step"] == 2
    assert result["warnings"][0]["source"] == "tushare.limit_list_d"
    assert result["warnings"][0]["exception_type"] == "RuntimeError"
    assert result["warnings"][0]["exception_message"] == "limit_list_d boom"


def test_two_sources_fail_then_stk_limit_daily_success(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sentiment, "_load_akshare", lambda: _empty_akshare_limit_pool())

    result = fetch_market_sentiment(PriceFallbackPro(), "20260602")

    assert result["source"] == "tushare.stk_limit+tushare.daily"
    assert result["up_limit_count"] == 1
    assert result["down_limit_count"] == 1
    assert result["limit_break_count"] == 1
    assert result["down_limit_open_count"] == 1
    assert result["data_quality"] == "partial"
    assert "日线价格与涨跌停价近似计算" in result["warnings"][-1]["message"]


def test_tushare_limit_permission_denied_falls_back_to_akshare(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sentiment, "_load_akshare", lambda: _akshare_limit_pool())

    result = fetch_market_sentiment(AkshareFallbackPro(), "20260602")

    assert result["source"] == "akshare.stock_zt_pool_em+stock_zt_pool_zbgc_em+stock_zt_pool_dtgc_em"
    assert result["data_quality"] == "full"
    assert result["up_limit_count"] == 2
    assert result["down_limit_count"] == 1
    assert result["limit_break_count"] == 1
    assert result["highest_limit_step"] == 3
    assert result["warnings"] == []
    assert result["fallback_attempts"][0]["source"] == "tushare.limit_list_d"
    assert result["fallback_attempts"][1]["source"] == "tushare.limit_list_ths"


def test_all_sources_fail_returns_warning(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sentiment, "_load_akshare", lambda: _empty_akshare_limit_pool())

    result = fetch_market_sentiment(AllFailPro(), "20260602")

    assert result["source"] == "market_sentiment_unavailable"
    assert result["data_quality"] == "warning"
    assert result["sentiment_score"] == 50
    assert len(result["warnings"]) == 5
    assert result["warnings"][0]["source"] == "tushare.limit_list_d"
    assert result["warnings"][1]["source"] == "tushare.limit_list_ths"


def test_daily_pct_fallback_estimates_limit_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sentiment, "_load_akshare", lambda: _empty_akshare_limit_pool())

    result = fetch_market_sentiment(DailyPctFallbackPro(), "20260602")

    assert result["source"] == "tushare.daily_pct"
    assert result["up_limit_count"] == 2
    assert result["down_limit_count"] == 2
    assert result["limit_break_count"] == 0
    assert result["data_quality"] == "partial"
    assert "全市场日涨跌幅" in result["warnings"][-1]["message"]


def test_market_sentiment_retries_rate_limited_source(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("TUSHARE_RETRY_DELAYS", "0,0")
    pro = RetryLimitListDPro()

    result = fetch_market_sentiment(pro, "20260602")

    assert pro.calls == 3
    assert result["source"] == "tushare.limit_list_d"
    assert result["up_limit_count"] == 1


def test_partial_stk_limit_cache_refreshes_to_akshare(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)
    cache_path = tmp_path / "market_sentiment_20260602.json"
    cache_path.write_text(
        '{"source":"tushare.stk_limit+tushare.daily","data_quality":"partial","warnings":[{"exception_message":"cannot convert float NaN to integer"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(sentiment, "_load_akshare", lambda: _akshare_limit_pool())

    result = fetch_market_sentiment(AkshareFallbackPro(), "20260602")

    assert result["source"] == "akshare.stock_zt_pool_em+stock_zt_pool_zbgc_em+stock_zt_pool_dtgc_em"
    assert result["warnings"] == []


def _akshare_limit_pool():
    return SimpleNamespace(
        stock_zt_pool_em=lambda **kwargs: pd.DataFrame(
            [
                {"代码": "000001", "名称": "A", "连板数": 3},
                {"代码": "000002", "名称": "B", "连板数": float("nan"), "涨停统计": "1/1"},
            ]
        ),
        stock_zt_pool_zbgc_em=lambda **kwargs: pd.DataFrame(
            [
                {"代码": "000003", "名称": "C", "涨停统计": "2/3"},
            ]
        ),
        stock_zt_pool_dtgc_em=lambda **kwargs: pd.DataFrame(
            [
                {"代码": "000004", "名称": "D", "连续跌停": 1},
            ]
        ),
    )


def _empty_akshare_limit_pool():
    return SimpleNamespace(
        stock_zt_pool_em=lambda **kwargs: pd.DataFrame(),
        stock_zt_pool_zbgc_em=lambda **kwargs: pd.DataFrame(),
        stock_zt_pool_dtgc_em=lambda **kwargs: pd.DataFrame(),
    )

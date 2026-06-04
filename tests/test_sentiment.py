import pandas as pd

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


class AllFailPro:
    def limit_list_d(self, **kwargs):
        raise RuntimeError("limit_list_d failed")

    def limit_list_ths(self, **kwargs):
        raise ValueError("limit_list_ths failed")

    def stk_limit(self, **kwargs):
        raise PermissionError("stk_limit denied")


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

    result = fetch_market_sentiment(PriceFallbackPro(), "20260602")

    assert result["source"] == "tushare.stk_limit+tushare.daily"
    assert result["up_limit_count"] == 1
    assert result["down_limit_count"] == 1
    assert result["limit_break_count"] == 1
    assert result["down_limit_open_count"] == 1
    assert result["data_quality"] == "partial"
    assert "日线价格与涨跌停价近似计算" in result["warnings"][-1]["message"]


def test_all_sources_fail_returns_warning(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment, "CACHE_DIR", tmp_path)

    result = fetch_market_sentiment(AllFailPro(), "20260602")

    assert result["source"] == "market_sentiment_unavailable"
    assert result["data_quality"] == "warning"
    assert result["sentiment_score"] == 50
    assert len(result["warnings"]) == 4
    assert result["warnings"][0]["source"] == "tushare.limit_list_d"
    assert result["warnings"][1]["source"] == "tushare.limit_list_ths"

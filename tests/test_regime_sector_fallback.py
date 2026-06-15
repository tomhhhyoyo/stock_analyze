from datetime import date
from types import SimpleNamespace

import pandas as pd

import stock_analyze.market_regime as market_regime
import stock_analyze.sector_context as sector_context


def test_market_regime_uses_akshare_fallback_and_avoids_gaps(monkeypatch):
    rows = []
    for idx in range(1, 66):
        rows.append({"close": 100 + idx, "amount": 1000 + idx * 10})
    fake_ak = SimpleNamespace(
        stock_zh_index_daily_em=lambda **kwargs: pd.DataFrame(rows),
        stock_hsgt_north_net_flow_in_em=lambda: pd.DataFrame([{"净流入": i} for i in range(1, 25)]),
    )
    monkeypatch.setattr(market_regime, "_load_akshare", lambda: fake_ak)
    gaps = []

    result = market_regime.analyze_market_regime(
        {"indices": [{"name": "上证指数", "trade_date": "2026-06-12", "close": 3000, "pct_chg": 1.0}]},
        {"up_limit_count": 10, "down_limit_count": 2, "limit_break_count": 1, "limit_break_rate": 0.1},
        gaps,
    )

    assert "index_dailybasic_missing" not in gaps
    assert "moneyflow_hsgt_missing" not in gaps
    assert result["turnover"]["amount_ratio_5_20_avg"] is not None
    assert result["northbound"]["net_inflow_5d"] == 110.0


def test_sector_context_uses_akshare_member_and_sentiment_fallback(monkeypatch):
    def fail_spot_em():
        raise ConnectionError("eastmoney disconnected")

    fake_ak = SimpleNamespace(
        index_component_sw=lambda **kwargs: pd.DataFrame([{"代码": "300308", "名称": "中际旭创", "日期": date(2026, 6, 12)}]),
        stock_zt_pool_em=lambda: pd.DataFrame([]),
        stock_zt_pool_zbgc_em=lambda: pd.DataFrame([]),
        stock_zt_pool_dtgc_em=lambda: pd.DataFrame([]),
        stock_zh_a_spot_em=fail_spot_em,
        stock_zh_a_spot=lambda: pd.DataFrame(
            [
                {"代码": "sz300308", "名称": "中际旭创", "涨跌幅": 20.0},
                {"代码": "sh600000", "名称": "浦发银行", "涨跌幅": -10.0},
            ]
        ),
    )
    monkeypatch.setattr(sector_context, "_load_akshare", lambda: fake_ak)
    gaps = []

    result = sector_context.analyze_sector_context(
        {"industry": {"status": "ok", "name": "通信", "ts_code": "801770.SI", "close": 8500, "pct_chg": 2.5}},
        [],
        {"ret_20d_pct": 8.0},
        gaps,
    )

    assert "sector_member_missing" not in gaps
    assert "sector_sentiment_missing" not in gaps
    assert result["sector_members"]["count"] == 1
    assert result["sector_members"]["sample"][0]["日期"] == "2026-06-12"
    assert result["sector_sentiment"]["up_limit_count"] == 1
    assert result["sector_sentiment"]["down_limit_count"] == 0
    assert result["sector_sentiment"]["limit_break_count"] == 0
    assert "stock_zh_a_spot" in result["sector_sentiment"]["source"]


def test_sector_context_uses_market_sentiment_proxy_when_member_quotes_unavailable(monkeypatch):
    fake_ak = SimpleNamespace(
        index_component_sw=lambda **kwargs: pd.DataFrame([{"证券代码": "601127", "证券名称": "赛力斯"}]),
        stock_zt_pool_em=lambda: pd.DataFrame([]),
        stock_zt_pool_zbgc_em=lambda: pd.DataFrame([]),
        stock_zt_pool_dtgc_em=lambda: pd.DataFrame([]),
        stock_zh_a_spot_em=lambda: pd.DataFrame([]),
        stock_zh_a_spot=lambda: pd.DataFrame([]),
    )
    monkeypatch.setattr(sector_context, "_load_akshare", lambda: fake_ak)
    monkeypatch.setattr(sector_context, "_read_spot_cache", lambda: {})
    gaps = []

    result = sector_context.analyze_sector_context(
        {
            "industry": {"status": "ok", "name": "汽车", "ts_code": "801880.SI", "close": 7000, "pct_chg": 1.0},
            "sentiment": {"up_limit_count": 12, "down_limit_count": 3, "limit_break_count": 2, "limit_break_rate": 0.14},
        },
        [],
        {"ret_20d_pct": -5.0},
        gaps,
    )

    assert "sector_sentiment_missing" not in gaps
    assert result["sector_sentiment"]["source"] == "market_sentiment_proxy"
    assert result["sector_sentiment"]["up_limit_count"] == 12
    assert result["sector_sentiment"]["down_limit_count"] == 3
    assert result["sector_sentiment"]["data_quality"] == "proxy"

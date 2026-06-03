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

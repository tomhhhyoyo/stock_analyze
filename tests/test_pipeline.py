import json
from pathlib import Path

import pytest

from stock_analyze.data_provider import StaticProvider, default_provider
from stock_analyze.models import DailyBar
from stock_analyze.pipeline import run_analysis


def _bars():
    bars = []
    price = 10.0
    for i in range(80):
        price += 0.05 if i < 60 else -0.02
        bars.append(
            DailyBar(
                date=f"2026-03-{(i % 28) + 1:02d}" if i < 28 else f"2026-04-{(i % 28) + 1:02d}" if i < 56 else f"2026-05-{(i % 28) + 1:02d}",
                open=round(price - 0.03, 2),
                high=round(price + 0.08, 2),
                low=round(price - 0.08, 2),
                close=round(price, 2),
                volume=1000000 + i * 10000,
                amount=10000000 + i * 100000,
            )
        )
    return bars


def test_run_single_stock_analysis(tmp_path: Path):
    provider = StaticProvider(
        _bars(),
        {
            "pe_ttm": 20,
            "pb": 2,
            "market_cap": 1000000,
            "source": "static",
            "financials": {
                "source": "static",
                "latest": {
                    "report_end_date": "2026-03-31",
                    "ann_date": "2026-04-20",
                    "roe": 8.5,
                    "revenue": 1000,
                    "net_profit_parent": 100,
                    "revenue_growth_yoy": 6.2,
                    "net_profit_growth_yoy": 12.3,
                },
                "gaps": [],
            },
            "moneyflow": {
                "source": "static",
                "latest": {"trade_date": "2026-05-24", "net_amount": 10, "net_amount_5d": 50},
                "gaps": [],
            },
            "market_context": {
                "source": "static",
                "indices": [{"name": "上证指数", "trade_date": "2026-05-24", "close": 3000, "pct_chg": 0.5}],
                "industry": {"status": "not_configured"},
                "sentiment": {"limit_up_count": 30, "limit_down_count": 5, "sample_size": 35},
                "gaps": [],
            },
            "announcements": [{"date": "2026-04-20", "title": "一季度报告", "type": "定期报告"}],
        },
    )

    result = run_analysis("/股票 分析 600519.SH，最近两年", tmp_path, provider)

    assert result["results"][0]["scorecard"]["rating"] in {"watch", "neutral", "avoid"}
    assert (tmp_path / "600519.SH" / "market_pack.json").exists()
    assert (tmp_path / "600519.SH" / "raw_data.json").exists()
    assert (tmp_path / "600519.SH" / "scorecard.json").exists()
    assert (tmp_path / "600519.SH" / "report.md").exists()
    assert (tmp_path / "600519.SH" / "audit.md").exists()
    pack = json.loads((tmp_path / "600519.SH" / "market_pack.json").read_text(encoding="utf-8"))
    assert pack["fundamental"]["revenue_growth_yoy"] == 6.2
    assert pack["moneyflow"]["latest"]["net_amount_5d"] == 50
    assert pack["market_context"]["indices"][0]["name"] == "上证指数"
    assert pack["announcements"][0]["title"] == "一季度报告"
    assert "data_contract" in pack
    assert "data_audit" in pack
    assert pack["indicators"]["bollinger20"]["middle"] is not None
    raw = json.loads((tmp_path / "600519.SH" / "raw_data.json").read_text(encoding="utf-8"))
    assert "financials" in raw
    assert "moneyflow" in raw
    report = (tmp_path / "600519.SH" / "report.md").read_text(encoding="utf-8")
    assert "资金流分析" in report
    assert "公告与事件风险" in report


def test_report_uses_chinese_risk_descriptions(tmp_path: Path):
    provider = StaticProvider(
        _bars(),
        {
            "pe_ttm": 20,
            "pb": 2,
            "source": "static",
            "financials": {
                "source": "static",
                "latest": {
                    "report_end_date": "2026-03-31",
                    "ann_date": "2026-04-20",
                    "revenue_growth_yoy": -2.3,
                    "net_profit_growth_yoy": -17.1,
                },
                "gaps": [],
            },
        },
    )

    run_analysis("/股票 分析 601728.SH，最近两年", tmp_path, provider)

    report = (tmp_path / "601728.SH" / "report.md").read_text(encoding="utf-8")
    assert "归母净利润同比为负，盈利增长承压" in report
    assert "营收同比为负，收入增长承压" in report
    assert "风险码：`NET_PROFIT_GROWTH_NEGATIVE`" in report
    assert "- **NET_PROFIT_GROWTH_NEGATIVE**：需复核。" not in report


def test_run_position_analysis(tmp_path: Path):
    provider = StaticProvider(_bars(), {"source": "static"})

    run_analysis("/持仓 600519.SH，成本 10.50，持仓 100 股", tmp_path, provider)

    text = (tmp_path / "600519.SH" / "position_report.md").read_text(encoding="utf-8")
    assert "相对成本" in text


def test_run_watchlist_analysis(tmp_path: Path):
    provider = StaticProvider(_bars(), {"source": "static"})

    run_analysis("/观察池 600519.SH、300750.SZ，做多维对比", tmp_path, provider)

    text = (tmp_path / "watchlist_report.md").read_text(encoding="utf-8")
    assert "分项评分" in text
    assert "不构成买入推荐" in text


def test_default_provider_requires_tushare_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="TUSHARE_TOKEN 未设置"):
        default_provider()

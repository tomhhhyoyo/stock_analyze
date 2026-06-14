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
    output_dir = tmp_path / "贵州茅台（600519.SH）"

    assert result["results"][0]["scorecard"]["rating"] in {"strong_watch", "watch", "neutral", "cautious", "avoid"}
    assert result["results"][0]["report_path"].endswith("贵州茅台（600519.SH）/report.html")
    assert result["results"][0]["markdown_report_path"].endswith("贵州茅台（600519.SH）/report.md")
    assert (output_dir / "market_pack.json").exists()
    assert (output_dir / "raw_data.json").exists()
    assert (output_dir / "scorecard.json").exists()
    assert (output_dir / "report.md").exists()
    assert (output_dir / "report.html").exists()
    assert (output_dir / "audit.md").exists()
    pack = json.loads((output_dir / "market_pack.json").read_text(encoding="utf-8"))
    assert pack["meta"]["name"] == "贵州茅台"
    assert pack["fundamental"]["revenue_growth_yoy"] == 6.2
    assert pack["moneyflow"]["latest"]["net_amount_5d"] == 50
    assert pack["market_context"]["indices"][0]["name"] == "上证指数"
    assert pack["announcements"][0]["title"] == "一季度报告"
    assert "data_contract" in pack
    assert "data_audit" in pack
    assert "volume_price" in pack
    assert pack["data_audit"]["has_volume_price"] is True
    assert pack["indicators"]["bollinger20"]["middle"] is not None
    assert pack["indicators"]["atr14"] is not None
    assert pack["indicators"]["max_drawdown60"] is not None
    assert pack["indicators"]["volatility20"] is not None
    raw = json.loads((output_dir / "raw_data.json").read_text(encoding="utf-8"))
    assert raw["provider"] == "static"
    assert raw["generated_at"]
    assert raw["meta"]["name"] == "贵州茅台"
    assert "daily" in raw
    assert "daily_basic" in raw
    assert "basic" in raw
    assert "financials" in raw
    assert "volume_price" in raw
    assert "announcements" in raw
    assert "moneyflow" in raw
    assert "market_context" in raw
    assert "market_sentiment" in raw
    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "# 贵州茅台（600519.SH）中文多维研究报告" in report
    assert "**股票**：贵州茅台（600519.SH）" in report
    assert "资金流分析" in report
    assert "综合判断" in report
    assert "数据依据" in report
    assert "多空证据表" in report
    assert "bullish_evidence" in report
    assert "量价关系" in report
    assert "公告与事件风险" in report
    assert "市场情绪与涨跌停结构" in report
    html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in html
    assert "<title>贵州茅台（600519.SH）中文多维研究报告</title>" in html
    assert "贵州茅台（600519.SH）中文多维研究报告" in html


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
    output_dir = tmp_path / "中国电信（601728.SH）"

    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "归母净利润同比为负，盈利增长承压" in report
    assert "营收同比为负，收入增长承压" in report
    assert "NET_PROFIT_GROWTH_NEGATIVE" not in report
    audit = (output_dir / "audit.md").read_text(encoding="utf-8")
    assert "内部标记：`NET_PROFIT_GROWTH_NEGATIVE`" in audit
    assert "- **NET_PROFIT_GROWTH_NEGATIVE**：需复核。" not in report


def test_run_position_analysis(tmp_path: Path):
    provider = StaticProvider(_bars(), {"source": "static"})

    run_analysis("/持仓 600519.SH，成本 10.50，持仓 100 股", tmp_path, provider)

    text = (tmp_path / "贵州茅台（600519.SH）" / "position_report.md").read_text(encoding="utf-8")
    assert "相对成本" in text
    assert "持仓状态判断" in text
    assert "持仓视角下的量价风险" in text
    html = (tmp_path / "贵州茅台（600519.SH）" / "position_report.html").read_text(encoding="utf-8")
    assert "相对成本" in html


def test_run_watchlist_analysis(tmp_path: Path):
    provider = StaticProvider(_bars(), {"source": "static"})

    run_analysis("/观察池 600519.SH、300750.SZ，做多维对比", tmp_path, provider)

    text = (tmp_path / "watchlist_report.md").read_text(encoding="utf-8")
    assert "观察优先级排序" in text
    assert "| 股票 | 评级 | 总分 | 趋势 | 量价 | 基本面 | 估值 | 资金流 | 市场环境 | 风险 | 数据质量 |" in text
    assert "升级/降级理由" in text
    assert "量价强弱对比" in text
    assert "贵州茅台（600519.SH）" in text
    assert "宁德时代（300750.SZ）" in text
    assert "不构成买入推荐" in text
    html = (tmp_path / "watchlist_report.html").read_text(encoding="utf-8")
    assert "<table>" in html
    assert "观察池对比报告" in html


def test_pipeline_keeps_running_when_market_sentiment_warns(tmp_path: Path):
    provider = StaticProvider(
        _bars(),
        {
            "source": "static",
            "market_context": {
                "source": "static",
                "indices": [{"name": "上证指数", "trade_date": "2026-05-24", "close": 3000, "pct_chg": 0.5}],
                "industry": {"status": "not_configured"},
                "sentiment": {
                    "trade_date": "2026-05-24",
                    "source": "market_sentiment_unavailable",
                    "sentiment_score": 50,
                    "sentiment_label": "数据不足",
                    "data_quality": "warning",
                    "warnings": [{"source": "market_sentiment", "message": "多源数据均未返回"}],
                },
                "gaps": [],
            },
        },
    )

    result = run_analysis("/股票 分析 600519.SH，最近两年", tmp_path, provider)

    pack = result["results"][0]["pack"]
    scores = result["results"][0]["scorecard"]["scores"]
    assert pack["market_sentiment"]["data_quality"] == "warning"
    assert pack["data_audit"]["optional_fields_missing"][0]["field"] == "market_sentiment"
    assert scores["trend"] is not None
    assert scores["valuation"] is not None
    assert scores["fundamental"] is not None


def test_market_pack_records_extended_financial_and_limit_risks(tmp_path: Path):
    bars = _bars()
    bars[-1] = DailyBar(
        date=bars[-1].date,
        open=bars[-1].open,
        high=bars[-1].high,
        low=bars[-1].low,
        close=10.0,
        volume=bars[-1].volume,
        amount=bars[-1].amount,
        adj_factor=2.0,
        qfq_open=9.8,
        qfq_high=10.3,
        qfq_low=9.7,
        qfq_close=10.0,
        limit_up=10.05,
        limit_down=9.0,
        pct_to_limit_up=0.5,
        pct_to_limit_down=11.1111,
    )
    provider = StaticProvider(
        bars,
        {
            "source": "static",
            "financials": {
                "source": "static",
                "latest": {
                    "report_end_date": "2026-03-31",
                    "ann_date": "2026-04-20",
                    "asset_liability_ratio": 0.76,
                    "money_cap": 80,
                    "accounts_receiv": 120,
                    "inventories": 90,
                    "goodwill": 130,
                    "interest_bearing_debt": 120,
                    "total_assets": 1000,
                    "total_liab": 760,
                    "operating_cashflow": 50,
                    "investing_cashflow": -70,
                    "financing_cashflow": 20,
                    "free_cashflow": -30,
                    "operating_cashflow_to_net_profit": 0.5,
                },
                "reserved": {"dividend": []},
                "gaps": [],
            },
        },
    )

    result = run_analysis("/股票 分析 600519.SH，最近两年", tmp_path, provider)

    pack = result["results"][0]["pack"]
    assert pack["quote"]["qfq_close"] == 10.0
    assert pack["quote"]["pct_to_limit_up"] == 0.5
    assert pack["fundamental"]["asset_liability_ratio"] == 0.76
    assert pack["fundamental"]["free_cashflow"] == -30
    assert pack["data_audit"]["has_balancesheet"] is True
    assert pack["data_audit"]["has_cashflow"] is True
    assert pack["data_audit"]["has_stk_limit"] is True
    assert pack["tushare_extensions"]["reserved"]["second_batch"]["dividend"] == []
    assert "ASSET_LIABILITY_RATIO_HIGH" in pack["risk_flags"]
    assert "INTEREST_BEARING_DEBT_ABOVE_CASH" in pack["risk_flags"]
    assert "GOODWILL_RATIO_HIGH" in pack["risk_flags"]
    assert "FREE_CASHFLOW_NEGATIVE" in pack["risk_flags"]
    assert "CASHFLOW_TO_PROFIT_WEAK" in pack["risk_flags"]
    assert "NEAR_LIMIT_UP" in pack["risk_flags"]


def test_default_provider_requires_tushare_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="AkShare 只能作为 Tushare 权限不足后的兜底源"):
        default_provider()


def test_readme_and_skill_rating_and_fallback_contract_are_consistent():
    readme = Path("README.md").read_text(encoding="utf-8")
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    combined = readme + "\n" + skill

    assert "当前数据全部通过 Tushare 获取" not in combined
    assert "strong_watch`：明显偏强，重点跟踪" in combined
    assert "watch`：偏强，继续观察" in combined
    assert "cautious`：偏弱，谨慎观察" in combined
    assert "avoid`：明显偏弱，优先规避风险" in combined
    assert "TUSHARE_TOKEN" in combined
    assert "AkShare 仅作为" in readme

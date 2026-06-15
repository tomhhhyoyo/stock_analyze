from stock_analyze.regime_adjuster import apply_regime_adjustment
from stock_analyze.scoring import _rating, build_scorecard, load_scoring_config


def test_load_scoring_config():
    config = load_scoring_config()

    assert round(sum(config["weights"].values()), 6) == 1
    assert config["weights"]["volume_price"] == 0.23
    assert config["weights"]["risk"] == 0.13
    assert config["rating_thresholds"]["strong_watch"] == 80
    assert config["rating_thresholds"]["watch"] == 68
    assert config["rating_thresholds"]["neutral"] == 54
    assert config["rating_thresholds"]["cautious"] == 42


def _pack(
    *,
    close: float = 12,
    ma: float = 10,
    ret20: float = 8,
    volume_score: int = 80,
    revenue_growth: float = 8,
    profit_growth: float = 15,
    roe: float = 12,
    pe: float = 20,
    pb: float = 2,
    net_5d: float = 10,
    risk_flags=None,
    data_gaps=None,
) -> dict:
    return {
        "meta": {"symbol": "600519.SH", "trade_date": "2026-06-12"},
        "quote": {"close": close},
        "indicators": {"ma5": ma, "ma10": ma, "ma20": ma, "ma60": ma, "ma120": ma, "ret_20d_pct": ret20, "vol_ratio_5_20": 1.2},
        "volume_price": {"verdict": "偏强", "metrics": {"score": volume_score}, "signals": ["放量突破"], "risks": ["换手率显著高于 20 日均值"]},
        "fundamental": {
            "revenue_growth_yoy": revenue_growth,
            "net_profit_growth_yoy": profit_growth,
            "roe": roe,
            "pe_ttm": pe,
            "pb": pb,
        },
        "moneyflow": {"latest": {"net_amount_5d": net_5d}},
        "market_context": {"indices": [{"pct_chg": 0.2}]},
        "market_sentiment": {"sentiment_score": 55, "data_quality": "full"},
        "risk_flags": risk_flags or [],
        "data_gaps": data_gaps or [],
    }


def test_rating_can_upgrade_from_neutral_to_watch_or_strong_watch():
    scorecard = build_scorecard(_pack())

    assert scorecard["rating_code"] in {"watch", "strong_watch"}
    assert scorecard["rating"] == scorecard["rating_label"]
    assert scorecard["scores"]["volume_price"] == 80
    assert scorecard["evidence"]["volume_price_signals"] == ["放量突破"]
    assert scorecard["evidence"]["volume_price_risks"] == ["换手率显著高于 20 日均值"]
    assert "bullish_evidence" in scorecard["evidence"]
    assert "bearish_evidence" in scorecard["evidence"]
    assert "neutral_evidence" in scorecard["evidence"]


def test_rating_can_downgrade_from_neutral_to_cautious_or_avoid():
    scorecard = build_scorecard(
        _pack(
            close=8,
            ma=10,
            ret20=-12,
            volume_score=25,
            revenue_growth=-5,
            profit_growth=-20,
            roe=3,
            pe=80,
            pb=10,
            net_5d=-10,
            risk_flags=["TREND_WEAK", "FUNDAMENTAL_PRESSURE"],
            data_gaps=["moneyflow_unavailable", "financials_unavailable"],
        )
    )

    assert scorecard["rating_code"] in {"cautious", "avoid"}


def test_five_rating_outputs_are_supported():
    thresholds = {"strong_watch": 80, "watch": 68, "neutral": 54, "cautious": 42}

    assert _rating(80, thresholds) == "strong_watch"
    assert _rating(70, thresholds) == "watch"
    assert _rating(55, thresholds) == "neutral"
    assert _rating(45, thresholds) == "cautious"
    assert _rating(35, thresholds) == "avoid"


def test_market_risk_off_caps_visible_rating_to_watch():
    pack = _pack()
    pack["market_regime"] = {
        "stage": "risk_off",
        "sentiment": {"up_limit_count": 3, "down_limit_count": 8},
    }
    pack["sector_context"] = {"stage": "修复", "relative_strength": {}}

    scorecard = apply_regime_adjustment(pack, build_scorecard(pack))

    assert scorecard["rating_code"] in {"neutral", "watch", "cautious", "avoid"}
    assert scorecard["rating_label"] != "偏强，重点跟踪"
    assert scorecard["rating"] == scorecard["rating_label"]
    assert scorecard["rating_adjustments"]


def test_sector_fade_and_volume_stall_downgrades_rating():
    pack = _pack(volume_score=72)
    pack["volume_price"]["signals"] = ["高位放量滞涨"]
    pack["market_regime"] = {"stage": "neutral", "sentiment": {"up_limit_count": 10, "down_limit_count": 5}}
    pack["sector_context"] = {"stage": "退潮", "relative_strength": {"outperformed_sector": False, "underperformed_sector": False}}

    scorecard = apply_regime_adjustment(pack, build_scorecard(pack))

    assert scorecard["rating_code"] in {"cautious", "neutral", "avoid"}
    assert any("板块退潮" in item["message"] for item in scorecard["rating_adjustments"])


def test_relative_strength_updates_evidence():
    pack = _pack()
    pack["market_regime"] = {"stage": "neutral", "sentiment": {"up_limit_count": 10, "down_limit_count": 5}}
    pack["sector_context"] = {"stage": "修复", "relative_strength": {"outperformed_sector": True, "underperformed_sector": False}}

    scorecard = apply_regime_adjustment(pack, build_scorecard(pack))

    assert "个股明显跑赢所属板块，具备相对强势" in scorecard["bullish_evidence"]

    pack["sector_context"] = {"stage": "修复", "relative_strength": {"outperformed_sector": False, "underperformed_sector": True}}
    scorecard = apply_regime_adjustment(pack, build_scorecard(pack))

    assert "个股明显跑输所属板块，弱于行业表现" in scorecard["bearish_evidence"]

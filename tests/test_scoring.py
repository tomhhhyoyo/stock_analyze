from stock_analyze.scoring import build_scorecard, load_scoring_config


def test_load_scoring_config():
    config = load_scoring_config()

    assert round(sum(config["weights"].values()), 6) == 1
    assert config["weights"]["volume_price"] == 0.2
    assert config["rating_thresholds"]["strong_watch"] == 78
    assert config["rating_thresholds"]["cautious"] == 40


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
        "volume_price": {"verdict": "偏强", "metrics": {"score": volume_score}},
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

    assert scorecard["rating"] in {"watch", "strong_watch"}
    assert scorecard["scores"]["volume_price"] == 80


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

    assert scorecard["rating"] in {"cautious", "avoid"}

from stock_analyze.scoring import load_scoring_config


def test_load_scoring_config():
    config = load_scoring_config()

    assert round(sum(config["weights"].values()), 6) == 1
    assert config["rating_thresholds"]["watch"] == 72

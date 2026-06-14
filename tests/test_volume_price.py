from stock_analyze.volume_price import analyze_volume_price


def _bars(prices, volumes, *, qfq=True, limit=True):
    rows = []
    for idx, (price, volume) in enumerate(zip(prices, volumes), 1):
        row = {
            "date": f"2026-05-{idx:02d}",
            "open": round(price * 0.99, 4),
            "high": round(price * 1.01, 4),
            "low": round(price * 0.98, 4),
            "close": round(price, 4),
            "volume": volume,
            "amount": round(price * volume, 4),
            "turnover_rate": 1 + idx * 0.01,
        }
        if qfq:
            row.update({"qfq_open": row["open"], "qfq_high": row["high"], "qfq_low": row["low"], "qfq_close": row["close"]})
        if limit:
            row.update({"limit_up": round(price * 1.1, 4), "limit_down": round(price * 0.9, 4)})
        rows.append(row)
    return rows


def _run(prices, volumes, **kwargs):
    gaps = []
    result = analyze_volume_price(
        _bars(prices, volumes, qfq=kwargs.get("qfq", True), limit=kwargs.get("limit", True)),
        {"turnover_rate": 1.2, "volume_ratio": 1.1},
        kwargs.get("moneyflow", {"latest": {"net_amount_5d": 10}}),
        kwargs.get("sentiment", {"source": "fake", "up_limit_count": 20, "down_limit_count": 5}),
        gaps,
    )
    return result, gaps


def test_volume_price_insufficient_daily_bars():
    gaps = []
    result = analyze_volume_price(_bars([10] * 19, [100] * 19), {}, {"latest": {}}, {}, gaps)

    assert result["confidence"] == "low"
    assert "volume_price_insufficient_daily_bars" in gaps


def test_volume_price_records_missing_adj_factor_moneyflow_and_stk_limit():
    result, gaps = _run([10 + i * 0.1 for i in range(20)], [1000] * 20, qfq=False, limit=False, moneyflow={"latest": {}})

    assert result["metrics"]["score"] is not None
    assert "volume_price_adj_factor_missing_using_raw_price" in gaps
    assert "volume_price_moneyflow_missing" in gaps
    assert "volume_price_stk_limit_missing" in gaps


def test_volume_price_detects_volume_breakout():
    prices = [10 + i * 0.05 for i in range(19)] + [12]
    volumes = [1000] * 15 + [1200, 1300, 1400, 1500, 4000]
    result, _ = _run(prices, volumes)

    assert "放量突破" in result["signals"]
    assert result["verdict"] in {"偏强", "中性偏强"}


def test_volume_price_detects_shrinking_volume_rise():
    prices = [10 + i * 0.03 for i in range(20)]
    volumes = [2000] * 15 + [900, 850, 820, 800, 780]
    result, _ = _run(prices, volumes)

    assert "缩量上涨" in result["signals"]


def test_volume_price_detects_high_volume_stall():
    prices = [10 + i * 0.12 for i in range(15)] + [11.7, 11.72, 11.73, 11.74, 11.75]
    volumes = [1000] * 15 + [3500, 3600, 3700, 3800, 3900]
    result, _ = _run(prices, volumes)

    assert "高位放量滞涨" in result["signals"]


def test_volume_price_detects_high_volume_drop():
    prices = [12 - i * 0.04 for i in range(19)] + [10.5]
    volumes = [1000] * 15 + [3000, 3200, 3400, 3600, 3800]
    result, _ = _run(prices, volumes)

    assert "放量下跌" in result["signals"]
    assert result["verdict"] in {"中性偏弱", "偏弱", "中性"}


def test_volume_price_detects_low_volume_pullback():
    prices = [10 + i * 0.08 for i in range(15)] + [11.0, 10.9, 10.8, 10.75, 10.7]
    volumes = [2000] * 15 + [900, 850, 800, 780, 760]
    result, _ = _run(prices, volumes)

    assert "缩量回调" in result["signals"]

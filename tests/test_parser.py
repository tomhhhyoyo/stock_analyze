from datetime import date

from stock_analyze.parser import normalize_symbol, parse_user_request


def test_parse_single_stock_request():
    req = parse_user_request("/股票 分析 600519.SH，最近一年，重点看技术面和估值", today=date(2026, 6, 2))

    assert req.command == "/股票"
    assert req.mode == "single_stock_analysis"
    assert req.symbols == ["600519.SH"]
    assert req.period.raw == "最近一年"
    assert "技术面" in req.focus
    assert "估值" in req.focus


def test_parse_position_request():
    req = parse_user_request("/持仓 300750.SZ，成本 185.30，持仓 200 股，中线", today=date(2026, 6, 2))

    assert req.mode == "position_check"
    assert req.position is not None
    assert req.position.cost_price == 185.30
    assert req.position.shares == 200


def test_parse_watchlist_request_with_names():
    req = parse_user_request("/观察池 贵州茅台、宁德时代、平安银行，做对比", today=date(2026, 6, 2))

    assert req.mode == "watchlist_review"
    assert req.symbols == ["600519.SH", "300750.SZ", "000001.SZ"]


def test_normalize_symbol():
    assert normalize_symbol("600519") == "600519.SH"
    assert normalize_symbol("300750") == "300750.SZ"


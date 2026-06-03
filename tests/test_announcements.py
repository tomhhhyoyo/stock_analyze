from stock_analyze.announcements import classify_announcement


def test_classify_high_risk_announcement():
    result = classify_announcement("关于收到监管函和业绩预亏的公告")

    assert result["risk_level"] == "high"
    assert "regulatory" in result["categories"]
    assert "earnings_warning" in result["categories"]

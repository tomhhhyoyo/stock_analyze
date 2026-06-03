from __future__ import annotations

import re
from datetime import date, timedelta

from .models import AnalysisRequest, Period, Position
from .symbols import extract_symbols, normalize_symbol

COMMANDS = {
    "/股票": "single_stock_analysis",
    "/持仓": "position_check",
    "/观察池": "watchlist_review",
}

def parse_user_request(text: str, today: date | None = None) -> AnalysisRequest:
    today = today or date.today()
    raw = text.strip()
    command = _parse_command(raw)
    mode = COMMANDS[command]
    symbols = _parse_symbols(raw)
    if not symbols:
        raise ValueError("未识别到股票代码或已知股票名称，请输入如 600519.SH、600519 或 贵州茅台。")
    if command == "/股票" and len(symbols) > 1:
        mode = "single_stock_analysis"
    period = _parse_period(raw, today)
    horizon = _parse_horizon(raw)
    focus = _parse_focus(raw)
    position = _parse_position(raw) if command == "/持仓" else None
    return AnalysisRequest(
        command=command,
        mode=mode,  # type: ignore[arg-type]
        symbols=symbols,
        period=period,
        analysis_horizon=horizon,
        focus=focus,
        position=position,
    )


def _parse_command(text: str) -> str:
    for command in COMMANDS:
        if text.startswith(command):
            return command
    if "持仓" in text or "成本" in text:
        return "/持仓"
    if "观察池" in text or "对比" in text:
        return "/观察池"
    return "/股票"


def _parse_symbols(text: str) -> list[str]:
    return extract_symbols(text)


def _parse_period(text: str, today: date) -> Period:
    range_match = re.search(
        r"(\d{4})[-年]?(\d{2})[-月]?(\d{2})日?\s*(?:到|至|-|~)\s*(\d{4})[-年]?(\d{2})[-月]?(\d{2})日?",
        text,
    )
    if range_match:
        y1, m1, d1, y2, m2, d2 = map(int, range_match.groups())
        return Period(date(y1, m1, d1), date(y2, m2, d2), range_match.group(0))
    year_since = re.search(r"(\d{4})\s*年?以来", text)
    if year_since:
        year = int(year_since.group(1))
        return Period(date(year, 1, 1), today, year_since.group(0))
    if "最近半年" in text:
        return Period(today - timedelta(days=183), today, "最近半年")
    if "最近三年" in text or "近三年" in text:
        return Period(today - timedelta(days=365 * 3), today, "最近三年")
    if "最近一年" in text or "近一年" in text:
        return Period(today - timedelta(days=365), today, "最近一年")
    return Period(today - timedelta(days=365 * 2), today, "最近两年")


def _parse_horizon(text: str):
    if "短线" in text:
        return "short"
    if "长线" in text:
        return "long"
    return "medium"


def _parse_focus(text: str) -> list[str]:
    focus_words = [
        "技术面",
        "量价",
        "资金面",
        "基本面",
        "估值",
        "公告",
        "解禁",
        "减持",
        "财务",
        "风险",
        "指数环境",
        "行业环境",
        "事件",
        "趋势",
        "复盘",
    ]
    return [word for word in focus_words if word in text]


def _parse_position(text: str) -> Position:
    cost = None
    shares = None
    weight = None
    holding_period = None
    pnl_description = None
    cost_match = re.search(r"成本(?:价)?\s*([0-9]+(?:\.[0-9]+)?)", text)
    if cost_match:
        cost = float(cost_match.group(1))
    shares_match = re.search(r"(?:持仓|持有)?\s*([0-9]+)\s*股", text)
    if shares_match:
        shares = int(shares_match.group(1))
    weight_match = re.search(r"仓位\s*([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if weight_match:
        weight = float(weight_match.group(1))
    period_match = re.search(r"(短线|中线|长线|持有\s*[0-9]+天|持有\s*[0-9]+个月|持有\s*[0-9]+年)", text)
    if period_match:
        holding_period = period_match.group(1).replace(" ", "")
    pnl_match = re.search(r"(浮盈|浮亏|盈利|亏损|套牢|回本)", text)
    if pnl_match:
        pnl_description = pnl_match.group(1)
    return Position(cost_price=cost, shares=shares, portfolio_weight=weight, holding_period=holding_period, pnl_description=pnl_description)

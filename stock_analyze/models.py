from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

Mode = Literal["single_stock_analysis", "position_check", "watchlist_review"]
Horizon = Literal["short", "medium", "long"]
Rating = Literal["watch", "neutral", "avoid"]


@dataclass(frozen=True)
class Period:
    start_date: date
    end_date: date
    raw: str

    def to_dict(self) -> dict[str, str]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "raw": self.raw,
        }


@dataclass(frozen=True)
class Position:
    cost_price: float | None = None
    shares: int | None = None
    portfolio_weight: float | None = None
    holding_period: str | None = None
    pnl_description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_price": self.cost_price,
            "shares": self.shares,
            "portfolio_weight": self.portfolio_weight,
            "holding_period": self.holding_period,
            "pnl_description": self.pnl_description,
        }


@dataclass(frozen=True)
class AnalysisRequest:
    command: str
    mode: Mode
    symbols: list[str]
    period: Period
    analysis_horizon: Horizon = "medium"
    focus: list[str] = field(default_factory=list)
    position: Position | None = None
    language: str = "zh-CN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "mode": self.mode,
            "symbols": self.symbols,
            "language": self.language,
            "period": self.period.to_dict(),
            "analysis_horizon": self.analysis_horizon,
            "focus": self.focus,
            "position": self.position.to_dict() if self.position else None,
            "constraints": {
                "no_fabricated_data": True,
                "no_realtime_claim": True,
                "no_direct_buy_sell": True,
                "no_target_price": True,
            },
        }


@dataclass(frozen=True)
class DailyBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
        }

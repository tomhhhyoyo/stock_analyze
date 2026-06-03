from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_provider import MarketDataProvider, default_provider
from .io import write_json, write_text
from .pack import build_market_pack
from .parser import parse_user_request
from .report import render_audit, render_dossier, render_report, render_watchlist_report
from .scoring import build_scorecard


def run_analysis(text: str, out_dir: Path = Path("output"), provider: MarketDataProvider | None = None) -> dict[str, Any]:
    request = parse_user_request(text)
    provider = provider or default_provider()
    results: list[dict[str, Any]] = []
    for symbol in request.symbols:
        pack = build_market_pack(request, symbol, provider)
        scorecard = build_scorecard(pack)
        symbol_dir = out_dir / symbol
        write_json(symbol_dir / "request.json", request.to_dict())
        write_json(symbol_dir / "raw_data.json", {"daily_bars": pack["daily_bars"]})
        write_json(symbol_dir / "market_pack.json", pack)
        write_json(symbol_dir / "scorecard.json", scorecard)
        write_text(symbol_dir / "audit.md", render_audit(pack, scorecard))
        write_text(symbol_dir / "decision_dossier.md", render_dossier(pack, scorecard))
        report_name = "position_report.md" if request.mode == "position_check" else "report.md"
        position = request.position.to_dict() if request.position else None
        write_text(symbol_dir / report_name, render_report(pack, scorecard, position))
        results.append({"pack": pack, "scorecard": scorecard, "report_path": str(symbol_dir / report_name)})
    if request.mode == "watchlist_review" or len(results) > 1:
        write_text(out_dir / "watchlist_report.md", render_watchlist_report(results))
    return {"request": request.to_dict(), "results": results}


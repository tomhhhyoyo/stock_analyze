from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_provider import MarketDataProvider, default_provider
from .io import write_json, write_text
from .pack import build_market_pack
from .parser import parse_user_request
from .report import render_audit, render_dossier, render_html_document, render_report, render_watchlist_report
from .scoring import build_scorecard
from .symbols import ensure_symbol_cache


def run_analysis(text: str, out_dir: Path = Path("output"), provider: MarketDataProvider | None = None) -> dict[str, Any]:
    if provider is None:
        provider = default_provider()
        ensure_symbol_cache(provider)
    request = parse_user_request(text)
    results: list[dict[str, Any]] = []
    for symbol in request.symbols:
        pack = build_market_pack(request, symbol, provider)
        scorecard = build_scorecard(pack)
        symbol_dir = out_dir / _output_dir_name(pack)
        write_json(symbol_dir / "request.json", request.to_dict())
        write_json(symbol_dir / "raw_data.json", _build_raw_data(pack))
        write_json(symbol_dir / "market_pack.json", pack)
        write_json(symbol_dir / "scorecard.json", scorecard)
        write_text(symbol_dir / "audit.md", render_audit(pack, scorecard))
        write_text(symbol_dir / "decision_dossier.md", render_dossier(pack, scorecard))
        report_name = "position_report.md" if request.mode == "position_check" else "report.md"
        html_report_name = report_name.removesuffix(".md") + ".html"
        position = request.position.to_dict() if request.position else None
        report_markdown = render_report(pack, scorecard, position)
        write_text(symbol_dir / report_name, report_markdown)
        write_text(symbol_dir / html_report_name, render_html_document(report_markdown, _html_title(pack, report_name)))
        results.append(
            {
                "pack": pack,
                "scorecard": scorecard,
                "report_path": str(symbol_dir / html_report_name),
                "markdown_report_path": str(symbol_dir / report_name),
            }
        )
    if request.mode == "watchlist_review" or len(results) > 1:
        watchlist_markdown = render_watchlist_report(results)
        write_text(out_dir / "watchlist_report.md", watchlist_markdown)
        write_text(out_dir / "watchlist_report.html", render_html_document(watchlist_markdown, "观察池对比报告"))
    return {"request": request.to_dict(), "results": results}


def _output_dir_name(pack: dict[str, Any]) -> str:
    symbol = str(pack["meta"]["symbol"])
    name = pack["meta"].get("name")
    if not name:
        return symbol
    return f"{_sanitize_path_part(str(name))}（{symbol}）"


def _sanitize_path_part(value: str) -> str:
    return "".join("_" if char in '/\\:*?"<>|' else char for char in value).strip() or "unknown"


def _html_title(pack: dict[str, Any], report_name: str) -> str:
    name = pack["meta"].get("name")
    symbol = pack["meta"]["symbol"]
    display = f"{name}（{symbol}）" if name else str(symbol)
    return f"{display}持仓风险快检" if report_name.startswith("position_") else f"{display}中文多维研究报告"


def _build_raw_data(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": pack["meta"].get("source"),
        "generated_at": pack["meta"].get("as_of"),
        "meta": {
            "symbol": pack["meta"]["symbol"],
            "name": pack["meta"].get("name"),
            "trade_date": pack["meta"]["trade_date"],
            "as_of": pack["meta"]["as_of"],
            "note": "raw_data.json 保存规范化后的原始数据响应快照，用于审计；不包含 token 或密钥。",
        },
        "daily": pack.get("daily_bars") or [],
        "daily_bars": pack.get("daily_bars") or [],
        "daily_basic": {
            "pe_ttm": (pack.get("fundamental") or {}).get("pe_ttm"),
            "pb": (pack.get("fundamental") or {}).get("pb"),
            "market_cap": (pack.get("fundamental") or {}).get("market_cap"),
            "circ_market_cap": (pack.get("fundamental") or {}).get("circ_market_cap"),
            "turnover_rate": (pack.get("fundamental") or {}).get("turnover_rate"),
            "turnover_rate_f": (pack.get("fundamental") or {}).get("turnover_rate_f"),
            "volume_ratio": (pack.get("fundamental") or {}).get("volume_ratio"),
        },
        "basic": {
            "pe_ttm": (pack.get("fundamental") or {}).get("pe_ttm"),
            "pb": (pack.get("fundamental") or {}).get("pb"),
            "market_cap": (pack.get("fundamental") or {}).get("market_cap"),
            "circ_market_cap": (pack.get("fundamental") or {}).get("circ_market_cap"),
        },
        "financials": pack.get("fundamental") or {},
        "volume_price": pack.get("volume_price") or {},
        "tushare_extensions": pack.get("tushare_extensions") or {},
        "announcements": pack.get("announcements") or [],
        "moneyflow": pack.get("moneyflow") or {},
        "market_context": pack.get("market_context") or {},
        "market_sentiment": pack.get("market_sentiment") or {},
        "data_gaps": pack.get("data_gaps") or [],
    }

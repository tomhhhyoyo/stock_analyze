from __future__ import annotations

from typing import Any

RISK_KEYWORDS = {
    "share_reduce": ("减持", "拟减持", "股东减持"),
    "unlock": ("解禁", "限售股上市"),
    "regulatory": ("处罚", "立案", "问询函", "监管函", "警示函"),
    "earnings_warning": ("预亏", "亏损", "业绩预告", "业绩快报", "修正"),
    "delisting": ("退市", "暂停上市", "终止上市"),
    "pledge": ("质押", "冻结"),
}


def classify_announcement(title: str | None, ann_type: str | None = None) -> dict[str, Any]:
    text = f"{title or ''} {ann_type or ''}"
    categories = [key for key, words in RISK_KEYWORDS.items() if any(word in text for word in words)]
    risk_level = "high" if any(key in categories for key in ["regulatory", "delisting", "earnings_warning"]) else "medium" if categories else "low"
    return {
        "categories": categories,
        "risk_level": risk_level,
    }


def enrich_announcements(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for item in rows:
        classified = classify_announcement(item.get("title"), item.get("type"))
        enriched.append({**item, **classified})
    return enriched


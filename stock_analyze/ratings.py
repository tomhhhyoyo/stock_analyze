from __future__ import annotations

RATING_ORDER = ["avoid", "cautious", "neutral", "watch", "strong_watch"]

RATING_LABELS = {
    "strong_watch": "偏强，重点跟踪",
    "watch": "中性偏强，继续观察",
    "neutral": "中性，等待确认",
    "cautious": "中性偏弱，谨慎观察",
    "avoid": "偏弱，优先规避风险",
}


def rating_label(code: str | None) -> str:
    return RATING_LABELS.get(str(code or "neutral"), RATING_LABELS["neutral"])


def clamp_rating(code: str, max_code: str) -> str:
    return RATING_ORDER[min(_idx(code), _idx(max_code))]


def shift_rating(code: str, steps: int) -> str:
    idx = max(0, min(len(RATING_ORDER) - 1, _idx(code) + steps))
    return RATING_ORDER[idx]


def _idx(code: str) -> int:
    try:
        return RATING_ORDER.index(code)
    except ValueError:
        return RATING_ORDER.index("neutral")

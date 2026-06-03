from __future__ import annotations

from statistics import mean


def moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(mean(values[-window:]), 4)


def rsi(values: list[float], window: int = 14) -> float | None:
    if len(values) <= window:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, cur in zip(values[-window - 1 : -1], values[-window:]):
        delta = cur - prev
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def ema(values: list[float], span: int) -> float | None:
    if not values:
        return None
    alpha = 2 / (span + 1)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1 - alpha) * current
    return current


def macd(values: list[float]) -> dict[str, float | None]:
    if len(values) < 35:
        return {"dif": None, "dea": None, "hist": None}
    dif_series: list[float] = []
    for i in range(1, len(values) + 1):
        subset = values[:i]
        e12 = ema(subset, 12)
        e26 = ema(subset, 26)
        if e12 is not None and e26 is not None:
            dif_series.append(e12 - e26)
    dea = ema(dif_series, 9)
    dif = dif_series[-1] if dif_series else None
    hist = None if dif is None or dea is None else (dif - dea) * 2
    return {
        "dif": round(dif, 4) if dif is not None else None,
        "dea": round(dea, 4) if dea is not None else None,
        "hist": round(hist, 4) if hist is not None else None,
    }


def pct_change(values: list[float], window: int) -> float | None:
    if len(values) <= window or values[-window - 1] == 0:
        return None
    return round((values[-1] / values[-window - 1] - 1) * 100, 2)


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


def bollinger(values: list[float], window: int = 20) -> dict[str, float | None]:
    if len(values) < window:
        return {"upper": None, "middle": None, "lower": None, "width": None}
    sample = values[-window:]
    middle = mean(sample)
    variance = mean([(value - middle) ** 2 for value in sample])
    std = variance**0.5
    upper = middle + 2 * std
    lower = middle - 2 * std
    width = (upper - lower) / middle if middle else None
    return {
        "upper": round(upper, 4),
        "middle": round(middle, 4),
        "lower": round(lower, 4),
        "width": round(width, 4) if width is not None else None,
    }


def atr(highs: list[float], lows: list[float], closes: list[float], window: int = 14) -> float | None:
    if len(highs) <= window or len(lows) <= window or len(closes) <= window:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return round(mean(trs[-window:]), 4)


def max_drawdown(values: list[float], window: int = 60) -> float | None:
    if len(values) < 2:
        return None
    sample = values[-window:] if len(values) >= window else values
    peak = sample[0]
    worst = 0.0
    for value in sample:
        peak = max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1)
    return round(worst * 100, 2)


def volatility(values: list[float], window: int = 20) -> float | None:
    if len(values) <= window:
        return None
    returns = [(cur / prev - 1) for prev, cur in zip(values[-window - 1 : -1], values[-window:]) if prev]
    if not returns:
        return None
    avg = mean(returns)
    variance = mean([(item - avg) ** 2 for item in returns])
    return round((variance**0.5) * 100, 4)

"""
Step 1 — WAIT condition checks.

check_wait_conditions(df, cfg) -> list[str]
    Returns a list of reasons to WAIT. Empty list means no WAIT conditions triggered.
    Caller should emit WAIT immediately if the list is non-empty.
"""

import pandas as pd


def _ema_flat(last: pd.Series, ema_flat_pct: float) -> bool:
    """EMAs are considered flat if their difference is below threshold_pct %."""
    mid = (last['ema9'] + last['ema21']) / 2
    diff_pct = abs(last['ema9'] - last['ema21']) / mid * 100
    return diff_pct < ema_flat_pct


def check_wait_conditions(df: pd.DataFrame, cfg) -> list[str]:
    """
    Check all WAIT conditions (Step 1 from CLAUDE.md).

    Conditions (any one triggers WAIT):
      - RSI 45–55 AND EMAs flat (< cfg.EMA_FLAT_PCT %)
      - volume < cfg.VOLUME_WAIT_RATIO × volume_ma20
      - BB squeeze active

    Args:
        df:  OHLCV DataFrame with computed indicators (ema9, ema21, rsi, volume_ma20, bb_squeeze).
        cfg: config module (config_lowliq or config_highliq) with WAIT-related constants.

    Returns:
        List of human-readable reason strings. Empty → no WAIT conditions.
    """
    last = df.iloc[-1]
    rsi = last['rsi']
    volume = last['volume']
    volume_ma20 = last['volume_ma20']

    reasons: list[str] = []

    if pd.notna(rsi) and 45 <= rsi <= 55 and _ema_flat(last, cfg.EMA_FLAT_PCT):
        reasons.append(f'RSI={rsi:.1f} нейтральный и EMAs плоские')

    if pd.notna(volume_ma20) and volume < volume_ma20 * cfg.VOLUME_WAIT_RATIO:
        reasons.append(
            f'объём {volume:.1f} < {cfg.VOLUME_WAIT_RATIO}x avg ({volume_ma20 * cfg.VOLUME_WAIT_RATIO:.1f})'
        )

    return reasons

"""
Step 2 — Directional scoring and level computation.

score_direction(df, cfg) -> dict
    Scores LONG vs SHORT and computes entry/stop/target/rr.
    Returns direction='WAIT' if scores are tied or R/R is invalid.

momentum_direction(df, n) -> str
    Public helper also used by analyze.py for the indicators block.
"""

import pandas as pd


def momentum_direction(df: pd.DataFrame, n: int = 3) -> str:
    """Determine momentum direction weighted by candle body size over last n candles.

    A large bullish body outweighs multiple small bearish ones.
    Returns 'up', 'down', or 'mixed'.
    """
    slice_ = df.iloc[-n:]
    bodies = (slice_['close'] - slice_['open']).values
    up_weight = sum(b for b in bodies if b > 0)
    down_weight = sum(-b for b in bodies if b < 0)
    if up_weight > down_weight:
        return 'up'
    if down_weight > up_weight:
        return 'down'
    return 'mixed'


def _recent_swing_low(df: pd.DataFrame, lookback: int) -> float:
    return df['low'].iloc[-lookback:].min()


def _recent_swing_high(df: pd.DataFrame, lookback: int) -> float:
    return df['high'].iloc[-lookback:].max()


def score_direction(df: pd.DataFrame, cfg) -> dict:
    """
    Score LONG vs SHORT and compute trade levels (Step 2 from CLAUDE.md).

    Assumes WAIT conditions (Step 1) have already been cleared.

    Scoring factors (each factor adds to running score):
      +2  price vs VWAP
      +1  EMA9 vs EMA21
      +1  RSI > 55 / < 45
      +1  momentum (body-weighted, last 3 candles)
      +2  volume spike + directional candle
      +1  wick rejection (upper/lower)

    Tie → WAIT "mixed signals".
    Invalid R/R → WAIT.

    Returns dict:
      direction      'LONG' | 'SHORT' | 'WAIT'
      entry          float | None
      stop           float | None
      target         float | None
      rr             float | None
      signal_reasons list[str]   — warnings (opposing wick, etc.) or WAIT explanation
      effective_slip float | None
      long_score     int
      short_score    int
      momentum       str
    """
    last = df.iloc[-1]
    price = last['close']
    rsi = last['rsi']
    ema9 = last['ema9']
    ema21 = last['ema21']
    vwap = last['vwap']
    atr = last['atr']
    volume_spike = bool(last['volume_spike'])
    bb_squeeze = bool(last['bb_squeeze'])
    bb_upper = last['bb_upper']
    bb_lower = last['bb_lower']

    candle_range = last['high'] - last['low']
    if candle_range > 0:
        upper_wick_ratio = (last['high'] - max(last['close'], last['open'])) / candle_range
        lower_wick_ratio = (min(last['close'], last['open']) - last['low']) / candle_range
    else:
        upper_wick_ratio = lower_wick_ratio = 0.0

    momentum = momentum_direction(df)

    # ── Scoring ───────────────────────────────────────────────────────────────
    long_score = 0
    short_score = 0

    if price > vwap:
        long_score += 2
    else:
        short_score += 2

    if ema9 > ema21:
        long_score += 1
    else:
        short_score += 1

    # ── Momentum group: RSI + 3-candle body, capped at +1 total ─────────────
    # Both agree on direction → +1 (avoids double-counting the same move)
    # Contradiction (sticky RSI vs reversing candles) → 0 + conflict flag
    rsi_long  = pd.notna(rsi) and rsi > 55
    rsi_short = pd.notna(rsi) and rsi < 45
    mom_long  = momentum == 'up'
    mom_short = momentum == 'down'
    momentum_conflict = False

    if rsi_long and mom_long:
        long_score += 1
    elif rsi_short and mom_short:
        short_score += 1
    elif (rsi_long and mom_short) or (rsi_short and mom_long):
        momentum_conflict = True   # RSI залипает / ранний разворот → 0 + предупреждение

    if volume_spike:
        if last['close'] > last['open']:
            long_score += 2
        elif last['close'] < last['open']:
            short_score += 2
        # doji + spike → no directional confirmation

    if upper_wick_ratio > cfg.WICK_REJECTION_RATIO:
        short_score += 1
    if lower_wick_ratio > cfg.WICK_REJECTION_RATIO:
        long_score += 1

    def _wait(reasons: list[str]) -> dict:
        return {
            'direction': 'WAIT',
            'entry': None, 'stop': None, 'target': None, 'rr': None,
            'signal_reasons': reasons,
            'effective_slip': None,
            'long_score': long_score, 'short_score': short_score,
            'momentum': momentum,
        }

    if long_score == short_score:
        return _wait(['Смешанные сигналы — нет чёткого преимущества'])

    direction = 'LONG' if long_score > short_score else 'SHORT'

    # ── Dynamic slippage: ATR-based market impact + bid-ask spread per leg ────
    if pd.notna(atr) and price > 0:
        market_slip = min(max(atr / price * 0.1, 0.0002), 0.002)
        effective_slip = round(market_slip + cfg.SPREAD_PCT, 6)
    else:
        effective_slip = cfg.SLIPPAGE_PCT + cfg.SPREAD_PCT

    # ── Entry / Stop ──────────────────────────────────────────────────────────
    if direction == 'LONG':
        entry = round(price * (1 + effective_slip), 4)
        stop = (
            round(_recent_swing_low(df, cfg.SWING_LOOKBACK) - atr * cfg.ATR_STOP_MULT, 4)
            if pd.notna(atr)
            else round(_recent_swing_low(df, cfg.SWING_LOOKBACK), 4)
        )
        risk = entry - stop * (1 - effective_slip)
    else:
        entry = round(price * (1 - effective_slip), 4)
        stop = (
            round(_recent_swing_high(df, cfg.SWING_LOOKBACK) + atr * cfg.ATR_STOP_MULT, 4)
            if pd.notna(atr)
            else round(_recent_swing_high(df, cfg.SWING_LOOKBACK), 4)
        )
        risk = stop * (1 + effective_slip) - entry

    if risk <= 0:
        return _wait(['Стоп слишком близко к цене — некорректный R/R'])

    # ── Smart target: snap to structural level if R/R holds ──────────────────
    if direction == 'LONG':
        fixed_target = round((entry + risk * cfg.RR_MIN) / (1 - effective_slip), 4)
        candidates = [lvl for lvl in (bb_upper, _recent_swing_high(df, cfg.SWING_LOOKBACK)) if lvl > entry]
        if candidates:
            struct_target = round(min(candidates), 4)
            struct_rr = (struct_target * (1 - effective_slip) - entry) / risk
            target = struct_target if struct_rr >= cfg.RR_MIN else fixed_target
            rr = round(struct_rr, 2) if struct_rr >= cfg.RR_MIN else cfg.RR_MIN
        else:
            target, rr = fixed_target, cfg.RR_MIN
    else:
        fixed_target = round((entry - risk * cfg.RR_MIN) / (1 + effective_slip), 4)
        candidates = [lvl for lvl in (bb_lower, _recent_swing_low(df, cfg.SWING_LOOKBACK)) if lvl < entry]
        if candidates:
            struct_target = round(max(candidates), 4)
            struct_rr = (entry - struct_target * (1 + effective_slip)) / risk
            target = struct_target if struct_rr >= cfg.RR_MIN else fixed_target
            rr = round(struct_rr, 2) if struct_rr >= cfg.RR_MIN else cfg.RR_MIN
        else:
            target, rr = fixed_target, cfg.RR_MIN

    if rr < cfg.RR_MIN:
        return _wait([f'R/R={rr:.1f} ниже минимального {cfg.RR_MIN}'])

    # ── Warnings ──────────────────────────────────────────────────────────────
    signal_reasons: list[str] = []
    if direction == 'LONG' and upper_wick_ratio > cfg.WICK_REJECTION_RATIO:
        signal_reasons.append(f'⚠ верхний wick {upper_wick_ratio:.0%} — rejection от хаёв')
    elif direction == 'SHORT' and lower_wick_ratio > cfg.WICK_REJECTION_RATIO:
        signal_reasons.append(f'⚠ нижний wick {lower_wick_ratio:.0%} — rejection от лоёв')

    if momentum_conflict:
        signal_reasons.append('⚠ RSI и моментум противоречат — RSI залипает или ранний разворот')

    # ── BB squeeze: signal allowed but flag it as breakout setup ─────────────
    if bb_squeeze:
        signal_reasons.append('⚠ BB squeeze — торгуем пробой, стоп плотнее')

    return {
        'direction': direction,
        'entry': entry,
        'stop': stop,
        'target': target,
        'rr': rr,
        'signal_reasons': signal_reasons,
        'effective_slip': effective_slip,
        'long_score': long_score,
        'short_score': short_score,
        'momentum': momentum,
    }

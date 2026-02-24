# High-liquidity pair tuning (BTC/USDT, ETH/USDT — top-2 by OI on Binance)
# Edit these values to adjust signal sensitivity.

# Stop placement: multiplier applied to ATR beyond swing high/low
# Tighter than lowliq — BTC/ETH move more predictably
ATR_STOP_MULT = 0.1        # lowliq: 0.5

# Volume: ratio below which the candle is considered low-liquidity → WAIT
VOLUME_WAIT_RATIO = 0.7    # lowliq: 0.6

# EMA flatness: % difference between ema9/ema21 below which trend is "flat"
# Tighter threshold — BTC/ETH trends are cleaner
EMA_FLAT_PCT = 0.015       # lowliq: 0.045

# Candles to look back for swing high/low
SWING_LOOKBACK = 10        # lowliq: 12

# Minimum R/R ratio to emit a signal (otherwise WAIT)
RR_MIN = 1.5

# Volume spike: percentile + follow-through (more robust than single-bar mean mult)
# Slightly lower percentile than lowliq — BTC/ETH volume is more normally distributed
VOLUME_SPIKE_PERCENTILE = 0.85   # top-15% threshold; lowliq: 0.90
VOLUME_SPIKE_WINDOW     = 30     # rolling window for percentile calculation
VOLUME_SPIKE_FOLLOW_PCT = 0.70   # 3-bar mean must exceed this percentile (follow-through)

# BB squeeze: rolling window for detecting band narrowing
BB_SQUEEZE_WINDOW = 10     # lowliq: 20

# Slippage: market order fill is worse than last price by this fraction
# Applied to all legs: entry fill, stop exit fill, target exit fill
SLIPPAGE_PCT = 0.0002      # 0.02% — tight for BTC/ETH (top liquidity on Binance)

# Bid-ask spread: half-spread cost per leg (close = last trade, not mid-price)
# BTC/ETH spreads ~0.01-0.02% total; 0.0002 per leg is conservative
SPREAD_PCT = 0.0002        # lowliq: 0.0005

# Wick rejection: upper/lower wick as fraction of full candle range above which
# the candle is considered a rejection
WICK_REJECTION_RATIO = 0.6  # same as lowliq

# MTF: filter 1m signals against 5m trend (bearish 5m blocks LONG, bullish 5m blocks SHORT)
MTF_FILTER = True

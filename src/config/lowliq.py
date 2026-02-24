# Low-liquidity pair tuning (e.g. SUI/USDT, ~18th by OI on Binance)
# Edit these values to adjust signal sensitivity.

# Stop placement: multiplier applied to ATR beyond swing high/low
# Higher = wider stop, more breathing room vs noise
ATR_STOP_MULT = 0.5        # BTC/ETH equivalent: 0.1

# Volume: ratio below which the candle is considered low-liquidity → WAIT
VOLUME_WAIT_RATIO = 0.6    # BTC/ETH equivalent: 0.7

# EMA flatness: % difference between ema9/ema21 below which trend is "flat"
EMA_FLAT_PCT = 0.045       # BTC/ETH equivalent: 0.015; was 0.08 (too wide for SUI on 1m)

# Candles to look back for swing high/low
SWING_LOOKBACK = 12        # BTC/ETH equivalent: 10; was 25 (too wide for 1m scalping)

# Minimum R/R ratio to emit a signal (otherwise WAIT)
RR_MIN = 1.5

# Volume spike: multiplier above rolling median to flag as spike
# Median is more robust to outliers than mean (used in get_data.py)
VOLUME_SPIKE_MULT = 2.0    # get_data.py default: 1.5x mean

# BB squeeze: rolling window for detecting band narrowing
BB_SQUEEZE_WINDOW = 20     # get_data.py default: 5

# Slippage: market order fill is worse than last price by this fraction
# Applied to all legs: entry fill, stop exit fill, target exit fill
SLIPPAGE_PCT = 0.0005      # 0.05% — typical Binance market order on mid-cap pairs

# Bid-ask spread: half-spread cost per leg (close = last trade, not mid-price)
# For low-liq pairs spread 0.03-0.10% total; 0.05% default = 0.10% round-trip
# Added on top of slippage for each leg
SPREAD_PCT = 0.0005        # 0.05% per leg — adjust upward for wider-spread pairs

# Wick rejection: upper/lower wick as fraction of full candle range above which
# the candle is considered a rejection (price tried to move but was rejected)
WICK_REJECTION_RATIO = 0.6  # wick > 60% of candle range = strong rejection

# MTF: filter 1m signals against 5m trend (bearish 5m blocks LONG, bullish 5m blocks SHORT)
# 5m trend = bullish if ema9>ema21 AND price>vwap; bearish if both below; else neutral
MTF_FILTER = True

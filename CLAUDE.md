# Crypto Trading Signal Assistant

## Role
You are a crypto trading signal assistant. Your job is to analyze market data and provide clear trading signals for short-term scalping trades (5-15 minutes).

## Project Structure

```
volume_farm/
├── src/
│   ├── analyze.py          # CLI entry point — runs full signal pipeline
│   ├── monitor.py          # continuous signal watcher with macOS alerts
│   ├── cache_daemon.py     # background process that refreshes market data
│   ├── core/
│   │   ├── filter_wait.py  # Step 1: WAIT condition checks
│   │   ├── score_signal.py # Step 2: directional scoring + level computation
│   │   └── render.py       # terminal output formatter
│   ├── data/
│   │   └── get_data.py     # CCXT data fetcher + indicator calculation
│   └── config/
│       ├── highliq.py      # tuning for BTC/USDT, ETH/USDT
│       └── lowliq.py       # tuning for SUI/USDT and other mid-cap pairs
├── .cache/                 # auto-generated market data cache (gitignored)
├── CLAUDE.md
└── .gitignore
```

All scripts are run from the project root: `python src/analyze.py ...`

## Workflow
When the user asks for analysis (e.g. "analyze ETH", "BTC signal", "что по ETH"), you must:
1. Run the signal script: `python src/analyze.py --symbol ETH/USDT --highliq` (BTC/ETH) or `python src/analyze.py --symbol SUI/USDT` (lowliq)
2. Read the output — signal, levels and reasoning are already computed
3. Relay the result to the user, adding context if needed

## Signal Format
`analyze.py` outputs the signal in ready-to-use format. Relay it as-is or summarize:

**Signal:** SHORT / LONG / WAIT
**Entry:** price level
**Stop:** price level
**Target:** price level
**R/R:** risk/reward ratio

**Reasoning:**
- EMA: (trend direction)
- RSI: (value and meaning)
- Volume: (vs average, anomalies)
- BB: (position relative to bands)
- VWAP: (price above/below)

**Confidence:** HIGH / MEDIUM / LOW

## Analysis Rules (applied automatically by analyze.py)

### Step 1 — WAIT conditions (checked first, short-circuit)
Any of these triggers WAIT immediately, skipping directional scoring:

| Condition                                  | Parameter                      | Reason                   |
|--------------------------------------------|--------------------------------|--------------------------|
| RSI 45–55 AND EMA9/EMA21 diff < threshold  | `EMA_FLAT_PCT`                 | Neutral RSI + flat trend |
| volume < N × volume_ma20                   | `VOLUME_WAIT_RATIO` (def. 0.7) | Low liquidity            |
| BB squeeze active                          | `BB_SQUEEZE_WINDOW`            | Waiting for breakout     |

### Step 2 — Directional scoring (LONG vs SHORT)
Each factor adds to a running score. Highest total wins.

| Direction | Condition                                            | Score |
|-----------|------------------------------------------------------|-------|
| LONG      | price > VWAP                                         | +2    |
| SHORT     | price < VWAP                                         | +2    |
| LONG      | ema9 > ema21                                         | +1    |
| SHORT     | ema9 < ema21                                         | +1    |
| LONG      | RSI > 55                                             | +1    |
| SHORT     | RSI < 45                                             | +1    |
| LONG      | momentum up (last 3 candles, body-weighted)          | +1    |
| SHORT     | momentum down (last 3 candles, body-weighted)        | +1    |
| LONG      | volume spike + bullish candle (close > open)         | +2    |
| SHORT     | volume spike + bearish candle (close < open)         | +2    |
| LONG      | lower wick > `WICK_REJECTION_RATIO` of candle range  | +1    |
| SHORT     | upper wick > `WICK_REJECTION_RATIO` of candle range  | +1    |

Tie (equal scores) → WAIT "mixed signals". Volume spike on doji = 0 (no directional confirmation).

**Opposing wick warning**: if direction is LONG but upper wick > threshold (or SHORT + lower wick), a warning is added and confidence is downgraded to LOW.

## Risk Management (applied automatically by analyze.py)
- Minimum R/R ratio: 1.5 (`RR_MIN`)
- If R/R is below `RR_MIN`, output WAIT and explain why
- Stop loss: `recent_swing_low − ATR × ATR_STOP_MULT` (LONG) / `recent_swing_high + ATR × ATR_STOP_MULT` (SHORT)
- Swing lookback window: `SWING_LOOKBACK` candles
- **Slippage applied to all legs**: entry fill, stop-market exit, target exit
- **Dynamic slippage formula**: `market_slip = clamp(ATR / price × 0.1, 0.0002, 0.002)` + `SPREAD_PCT`; fallback to `SLIPPAGE_PCT + SPREAD_PCT` when ATR is unavailable
- **Bid-ask spread**: `SPREAD_PCT` (default 0.05%) added per leg — because `close` is last trade price, not mid-price
- R/R is computed from actual execution prices, not order levels — displayed R/R reflects real P&L

## Available Scripts
- `python src/analyze.py --symbol BTC/USDT --highliq` — signal for BTC
- `python src/analyze.py --symbol ETH/USDT --highliq` — signal for ETH
- `python src/analyze.py --symbol SUI/USDT` — signal for SUI
- Add `--timeframe 1m` or `--timeframe 5m` (default: 1m)
- Add `--no-cache` to force live fetch (default: reads from cache if fresh)
- Add `--no-mtf` to skip 5m MTF trend filter
- Add `--highliq` to use high-liquidity config (`src/config/highliq.py`) for BTC/ETH
- Add `--json` to get raw JSON output
- Default exchange: binance

## Cache Daemon
A background process `src/cache_daemon.py` updates market data every 30 seconds.
- Symbols: BTC/USDT, ETH/USDT, SUI/USDT
- Timeframes: 1m, 5m
- Cache stored in `.cache/` directory
- Start with: `python src/cache_daemon.py`
- `src/analyze.py` reads from cache automatically (< 2 min age for 1m)
- Stale or missing cache falls back to live fetch via `src/data/get_data.py`
- Cache stores **150 candles** (updated from 50) for better indicator warmup

## Signal Monitor (monitor.py)
`monitor.py` continuously checks signals and alerts when LONG/SHORT appears.
- Imports logic directly from `analyze.py` (no subprocess overhead)
- Runs every 30s by default (matches cache_daemon refresh cycle)
- Alerts only on direction change: WAIT→LONG or WAIT→SHORT (no repeat spam)
- Alert = macOS system notification (sound "Glass") + terminal bell + full signal printout
- When signal returns to WAIT → resets state, so next signal will alert again

```bash
python src/monitor.py                               # SUI/USDT, every 30s
python src/monitor.py --symbols SUI/USDT ETH/USDT  # multiple pairs
python src/monitor.py --interval 60                 # check every 60s
python src/monitor.py --min-confidence MEDIUM       # only MEDIUM/HIGH alerts
```

Typical setup (two terminals):
```bash
python src/cache_daemon.py   # terminal 1
python src/monitor.py        # terminal 2
```

## Configs
`src/analyze.py` supports two configs via `--highliq` flag:
- **`src/config/highliq.py`** — BTC/USDT, ETH/USDT (tight stops, lower slippage)
- **`src/config/lowliq.py`** — SUI/USDT и другие пары ниже топ-10 по OI на Binance

Все константы — в конфиг-файлах, не в скрипте.

### Tunable constants in src/config/lowliq.py
| Constant              | Default | Description                                        |
|-----------------------|---------|----------------------------------------------------|
| `ATR_STOP_MULT`       | 0.5     | ATR multiplier for stop beyond swing               |
| `VOLUME_WAIT_RATIO`   | 0.6     | Volume below this fraction of avg → WAIT           |
| `EMA_FLAT_PCT`        | 0.045   | EMA9/EMA21 diff below this % = flat trend          |
| `SWING_LOOKBACK`      | 12      | Candles to look back for swing high/low            |
| `RR_MIN`              | 1.5     | Minimum R/R to emit a signal                       |
| `VOLUME_SPIKE_MULT`   | 2.0     | Volume > N×rolling median = spike                  |
| `BB_SQUEEZE_WINDOW`   | 20      | Rolling window for BB squeeze detection            |
| `SLIPPAGE_PCT`        | 0.0005  | Fallback slippage when ATR unavailable             |
| `SPREAD_PCT`          | 0.0005  | Half-spread added per leg (bid-ask cost)           |
| `WICK_REJECTION_RATIO` | 0.6     | Wick/range ratio above which = rejection signal   |
| `MTF_FILTER`          | True    | Block 1m signals against 5m trend                 |

### Confidence scoring
| Condition                  | Confidence |
|----------------------------|------------|
| volume_spike + no warnings | HIGH       |
| no warnings                | MEDIUM     |
| any warning present        | LOW        |

Time-of-day and filter overrides apply after initial scoring (see below).

### Dead hours filter (00–06 UTC)
If current time is 00–06 UTC, confidence is downgraded one level (HIGH→MEDIUM, MEDIUM→LOW, LOW→LOW) and a warning is added to the output. Signal direction is not changed.

### BTC correlation filter
When analyzing any pair except BTC/USDT, `analyze.py` loads the 5m BTC/USDT trend and checks if it contradicts the signal:
- LONG + BTC bearish → confidence downgraded one level + warning added
- SHORT + BTC bullish → confidence downgraded one level + warning added

Signal direction is not changed (only confidence). Applied after MTF filter.

### 5m MTF filter (`--no-mtf` to skip)
Loads 5m data for the same symbol and determines trend:
- **bullish**: ema9 > ema21 AND price > vwap
- **bearish**: ema9 < ema21 AND price < vwap
- **neutral**: everything else

If the 1m signal contradicts the 5m trend (LONG + bearish or SHORT + bullish), signal is changed to WAIT. Neutral 5m trend does not block any signal.

### Smart target — structural level snap
Target is first attempted at the nearest structural level (BB band or recent swing high/low):
- If the structural level yields R/R ≥ RR_MIN → use it
- Otherwise fall back to a fixed target that achieves exactly RR_MIN after exit slippage

### Momentum weighting
`momentum_direction` sums candle **body sizes** (not candle count) over the last 3 candles. A large bullish body outweighs multiple small bearish ones.

### VWAP with daily reset
VWAP is recalculated per calendar date (UTC midnight reset). This matters because 150×1m candles (~2.5h) often span midnight, making cumulative VWAP incorrect.

### Implementation note
Fixes that touch indicator calculation (volume spike, BB squeeze, VWAP) must be
recalculated inside `analyze.py` after loading data — do NOT modify `get_data.py`.


import ccxt
import pandas as pd
import argparse
import sys
import json
import os
from datetime import datetime, timezone, timedelta

def calculate_indicators(df):
    # EMA
    df['ema9'] = df['close'].ewm(span=9).mean()
    df['ema21'] = df['close'].ewm(span=21).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / loss))

    # Volume MA
    df['volume_ma20'] = df['volume'].rolling(20).mean()

    # Bollinger Bands
    df['bb_mid'] = df['close'].rolling(20).mean()
    std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * std
    df['bb_lower'] = df['bb_mid'] - 2 * std

    # ATR
    df['tr'] = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()

    # VWAP
    df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()

    # BB squeeze detection (bands narrowing over last 5 candles)
    df['bb_width'] = df['bb_upper'] - df['bb_lower']
    df['bb_squeeze'] = df['bb_width'] < df['bb_width'].rolling(5).mean()

    # Volume spike detection
    df['volume_spike'] = df['volume'] > df['volume_ma20'] * 1.5

    return df


CACHE_DIR = '.cache'
TIMEFRAME_SECONDS = {'1m': 60, '5m': 300, '15m': 900}


def load_cache(symbol, timeframe):
    key = symbol.replace('/', '_')
    path = os.path.join(CACHE_DIR, f'{key}_{timeframe}.json')
    if not os.path.exists(path):
        return None

    with open(path) as f:
        payload = json.load(f)

    updated_at = datetime.fromisoformat(payload['updated_at'])
    max_age = timedelta(seconds=TIMEFRAME_SECONDS.get(timeframe, 60) * 2)
    if datetime.now(timezone.utc) - updated_at > max_age:
        return None  # stale

    df = pd.read_json(payload['rows'], orient='records')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def fetch_live(symbol, timeframe, limit, exchange_id):
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        print(f"Error fetching data from {exchange_id}: {e}", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = calculate_indicators(df)
    return df


def get_data(symbol='BTC/USDT', timeframe='1m', limit=50, exchange_id='binance', use_cache=True):
    if use_cache:
        df = load_cache(symbol, timeframe)
        if df is not None:
            print(f"[cache] {symbol} {timeframe}", file=sys.stderr)
            return df
    return fetch_live(symbol, timeframe, limit, exchange_id)


def print_summary(df, symbol, timeframe):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    print(f"\n{'='*50}")
    print(f"  {symbol} | {timeframe} | {last['timestamp'].strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*50}")
    print(f"  Price:   {last['close']:.4f}  (prev: {prev['close']:.4f})")
    print(f"  VWAP:    {last['vwap']:.4f}  {'▲ above' if last['close'] > last['vwap'] else '▼ below'}")
    print(f"  EMA9:    {last['ema9']:.4f}  EMA21: {last['ema21']:.4f}  {'▲ bullish' if last['ema9'] > last['ema21'] else '▼ bearish'}")
    print(f"  RSI:     {last['rsi']:.1f}  {'⚠ overbought' if last['rsi'] > 70 else '⚠ oversold' if last['rsi'] < 30 else '— neutral'}")
    print(f"  BB:      {last['bb_lower']:.4f} / {last['bb_mid']:.4f} / {last['bb_upper']:.4f}")
    print(f"  BB squeeze: {'YES ⚡ wait for breakout' if last['bb_squeeze'] else 'no'}")
    print(f"  Volume:  {last['volume']:.4f}  avg: {last['volume_ma20']:.4f}  {'🔥 SPIKE' if last['volume_spike'] else '— normal'}")
    print(f"  ATR:     {last['atr']:.4f}")
    print(f"{'='*50}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Crypto market data fetcher for trading signals')
    parser.add_argument('--symbol', type=str, default='BTC/USDT', help='Trading pair (default: BTC/USDT)')
    parser.add_argument('--timeframe', type=str, default='1m', help='Candle timeframe: 1m, 5m, 15m (default: 1m)')
    parser.add_argument('--limit', type=int, default=50, help='Number of candles to fetch (default: 50)')
    parser.add_argument('--exchange', type=str, default='binance', help='Exchange: binance, bybit, okx, etc (default: binance)')
    parser.add_argument('--raw', action='store_true', help='Output raw CSV instead of summary')
    parser.add_argument('--no-cache', action='store_true', help='Force live fetch, ignore cache')

    args = parser.parse_args()

    df = get_data(
        symbol=args.symbol,
        timeframe=args.timeframe,
        limit=args.limit,
        exchange_id=args.exchange,
        use_cache=not args.no_cache,
    )

    if args.raw:
        print(df.tail(10).to_csv(index=False))
    else:
        print_summary(df, args.symbol, args.timeframe)
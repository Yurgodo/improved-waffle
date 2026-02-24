import time
import json
import os
import sys
from datetime import datetime, timezone

import ccxt
import pandas as pd

from get_data import calculate_indicators

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SUI/USDT']
TIMEFRAMES = ['1m', '5m']
EXCHANGE_ID = 'binance'
LIMIT = 150
CACHE_DIR = '.cache'
UPDATE_INTERVAL = 30  # seconds


def cache_path(symbol, timeframe):
    key = symbol.replace('/', '_')
    return os.path.join(CACHE_DIR, f'{key}_{timeframe}.json')


def fetch_and_cache(exchange, symbol, timeframe):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=LIMIT)
    except Exception as e:
        print(f'[{now()}] ERROR {symbol} {timeframe}: {e}', file=sys.stderr)
        return

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = calculate_indicators(df)

    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'symbol': symbol,
        'timeframe': timeframe,
        'rows': df.to_json(orient='records', date_format='iso'),
    }

    path = cache_path(symbol, timeframe)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(payload, f)
    os.replace(tmp_path, path)  # atomic write

    print(f'[{now()}] cached {symbol} {timeframe}  close={df.iloc[-1]["close"]:.2f}')


def now():
    return datetime.now(timezone.utc).strftime('%H:%M:%S')


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)

    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange = exchange_class()

    print(f'Cache daemon started — updating every {UPDATE_INTERVAL}s')
    print(f'Symbols: {SYMBOLS}  Timeframes: {TIMEFRAMES}')

    while True:
        for symbol in SYMBOLS:
            for timeframe in TIMEFRAMES:
                fetch_and_cache(exchange, symbol, timeframe)

        time.sleep(UPDATE_INTERVAL)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nDaemon stopped.')

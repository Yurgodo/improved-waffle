import asyncio
import json
import os
import sys
from collections import deque
from datetime import datetime, timezone

import ccxt.pro as ccxtpro
import pandas as pd

from data.get_data import calculate_indicators

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SUI/USDT', 'UNI/USDT']
TIMEFRAMES = ['1m', '5m']
EXCHANGE_ID = 'binance'
LIMIT = 150
CACHE_DIR = '.cache'

# Rolling candle buffers: {(symbol, timeframe): deque of [ts, o, h, l, c, v]}
_buffers: dict[tuple, deque] = {}


def cache_path(symbol, timeframe):
    key = symbol.replace('/', '_')
    return os.path.join(CACHE_DIR, f'{key}_{timeframe}.json')


def write_cache(symbol, timeframe, rows: list):
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
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

    print(f'[{now()}] {symbol} {timeframe}  close={df.iloc[-1]["close"]:.2f}')


def now():
    return datetime.now(timezone.utc).strftime('%H:%M:%S')


async def watch_symbol_timeframe(exchange, symbol, timeframe):
    buf = _buffers.setdefault((symbol, timeframe), deque(maxlen=LIMIT))

    # Pre-populate buffer with historical candles via REST before WebSocket loop.
    # watch_ohlcv returns only the current live candle (no history), so without
    # this prefetch the 50-candle threshold would not be reached for ~50 minutes.
    try:
        history = await exchange.fetch_ohlcv(symbol, timeframe, limit=LIMIT)
        for candle in history:
            buf.append(candle)
        print(f'[{now()}] {symbol} {timeframe}  prefetched {len(history)} candles')
        if len(buf) >= 50:
            write_cache(symbol, timeframe, list(buf))
    except Exception as e:
        print(f'[{now()}] WARN {symbol} {timeframe} prefetch failed: {e}', file=sys.stderr)

    while True:
        try:
            candles = await exchange.watch_ohlcv(symbol, timeframe, limit=LIMIT)
            for candle in candles:
                if buf and buf[-1][0] == candle[0]:
                    buf[-1] = candle   # update in-progress candle
                else:
                    buf.append(candle) # new candle

            if len(buf) >= 50:  # need enough rows for indicators
                write_cache(symbol, timeframe, list(buf))

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f'[{now()}] ERROR {symbol} {timeframe}: {e}', file=sys.stderr)
            await asyncio.sleep(5)


async def main():
    os.makedirs(CACHE_DIR, exist_ok=True)

    exchange = ccxtpro.binance({'enableRateLimit': True})

    print('Cache daemon started — WebSocket mode')
    print(f'Symbols: {SYMBOLS}  Timeframes: {TIMEFRAMES}')

    tasks = [
        asyncio.create_task(watch_symbol_timeframe(exchange, symbol, timeframe))
        for symbol in SYMBOLS
        for timeframe in TIMEFRAMES
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nDaemon stopped.')

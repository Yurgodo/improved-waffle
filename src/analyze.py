#!/usr/bin/env python3
"""
Fast crypto signal analyzer.
Reads data from cache, applies rule-based logic, renders formatted output instantly.
No AI calls — just pure technical analysis from CLAUDE.md rules.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from io import StringIO

import importlib

import pandas as pd

from core.filter_wait import check_wait_conditions
from core.score_signal import score_direction, momentum_direction
from core.render import render

_cfg_name = 'config.highliq' if '--highliq' in sys.argv else 'config.lowliq'
_cfg = importlib.import_module(_cfg_name)
ATR_STOP_MULT = _cfg.ATR_STOP_MULT
VOLUME_WAIT_RATIO = _cfg.VOLUME_WAIT_RATIO
EMA_FLAT_PCT = _cfg.EMA_FLAT_PCT
SWING_LOOKBACK = _cfg.SWING_LOOKBACK
RR_MIN = _cfg.RR_MIN
VOLUME_SPIKE_MULT = _cfg.VOLUME_SPIKE_MULT
BB_SQUEEZE_WINDOW = _cfg.BB_SQUEEZE_WINDOW
SLIPPAGE_PCT = _cfg.SLIPPAGE_PCT
SPREAD_PCT = _cfg.SPREAD_PCT
WICK_REJECTION_RATIO = _cfg.WICK_REJECTION_RATIO
MTF_FILTER = _cfg.MTF_FILTER

CACHE_DIR = '.cache'
TIMEFRAME_SECONDS = {'1m': 60, '5m': 300}


def load_cache(symbol: str, timeframe: str) -> pd.DataFrame | None:
    key = symbol.replace('/', '_')
    path = os.path.join(CACHE_DIR, f'{key}_{timeframe}.json')
    if not os.path.exists(path):
        return None

    with open(path) as f:
        payload = json.load(f)

    updated_at = datetime.fromisoformat(payload['updated_at'])
    max_age = timedelta(seconds=TIMEFRAME_SECONDS.get(timeframe, 60) * 2)
    if datetime.now(timezone.utc) - updated_at > max_age:
        print(f'[warn] cache is stale ({updated_at.strftime("%H:%M:%S")} UTC), fetching live...', file=sys.stderr)
        return None

    df = pd.read_json(StringIO(payload['rows']), orient='records')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def fetch_live(symbol: str, timeframe: str) -> pd.DataFrame:
    from data.get_data import get_data
    return get_data(symbol=symbol, timeframe=timeframe, use_cache=False)


def recalculate_lowliq_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Recalculate volume_spike, bb_squeeze, and vwap with lowliq-tuned parameters.
    Called after loading data to override get_data.py defaults.
    """
    # Volume spike: 2.0x rolling median (robust to outliers vs 1.5x mean in get_data.py)
    vol_median = df['volume'].rolling(20).median()
    df['volume_spike'] = df['volume'] > vol_median * VOLUME_SPIKE_MULT

    # BB squeeze: wider window = less false squeezes on noisy pairs
    df['bb_width'] = df['bb_upper'] - df['bb_lower']
    df['bb_squeeze'] = df['bb_width'] < df['bb_width'].rolling(BB_SQUEEZE_WINDOW).mean()

    # VWAP with daily reset (get_data.py uses cumulative without reset)
    # With 150×1m candles (~2.5h) data often spans midnight UTC — cumulative VWAP is wrong
    df['_date'] = df['timestamp'].dt.date
    df['_tp_vol'] = (df['high'] + df['low'] + df['close']) / 3 * df['volume']
    df['vwap'] = (
        df.groupby('_date')['_tp_vol'].cumsum() /
        df.groupby('_date')['volume'].cumsum()
    )
    df.drop(columns=['_date', '_tp_vol'], inplace=True)

    return df


def get_5m_trend(symbol: str, no_cache: bool = False) -> dict | None:
    """Load 5m data and determine trend direction for MTF filtering.
    Returns {'trend': 'bullish'/'bearish'/'neutral', 'ema9', 'ema21', 'vwap'} or None on error.
    Trend is bullish if ema9>ema21 AND price>vwap; bearish if both below; neutral otherwise.
    """
    df5 = None
    if not no_cache:
        df5 = load_cache(symbol, '5m')
    if df5 is None:
        try:
            df5 = fetch_live(symbol, '5m')
        except Exception:
            return None
    if df5 is None or df5.empty:
        return None

    df5 = recalculate_lowliq_indicators(df5)
    last = df5.iloc[-1]
    ema9, ema21 = last['ema9'], last['ema21']
    vwap, price = last['vwap'], last['close']

    if ema9 > ema21 and price > vwap:
        trend = 'bullish'
    elif ema9 < ema21 and price < vwap:
        trend = 'bearish'
    else:
        trend = 'neutral'

    return {
        'trend': trend,
        'ema9': round(ema9, 4),
        'ema21': round(ema21, 4),
        'vwap': round(vwap, 4),
    }


def apply_btc_filter(result: dict, btc_trend: dict) -> dict:
    """Downgrade confidence if BTC trend opposes the signal (correlation filter).
    LONG + BTC bearish → confidence drops one level; SHORT + BTC bullish → same.
    Does not change the signal itself — just adds a warning and reduces confidence.
    """
    signal = result['signal']
    trend = btc_trend['trend']
    contradicts = (signal == 'LONG' and trend == 'bearish') or \
                  (signal == 'SHORT' and trend == 'bullish')

    if contradicts:
        conf_map = {'HIGH': 'MEDIUM', 'MEDIUM': 'LOW', 'LOW': 'LOW'}
        old_conf = result.get('confidence')
        result['confidence'] = conf_map.get(old_conf, old_conf)
        direction_label = 'медвежий' if trend == 'bearish' else 'бычий'
        result.setdefault('wait_reasons', [])
        result['wait_reasons'].append(f'⚠ BTC тренд {direction_label} — против {signal}, confidence понижен')

    return result


def apply_mtf_filter(result: dict, trend_5m: dict) -> dict:
    """Downgrade 1m signal to WAIT if it contradicts the 5m trend.
    LONG + bearish 5m → WAIT; SHORT + bullish 5m → WAIT.
    Neutral 5m trend does not block any signal.
    """
    signal = result['signal']
    trend = trend_5m['trend']
    contradicts = (signal == 'LONG' and trend == 'bearish') or \
                  (signal == 'SHORT' and trend == 'bullish')

    if contradicts:
        direction_label = 'медвежий' if trend == 'bearish' else 'бычий'
        result['wait_reasons'] = [f'5m тренд {direction_label} — против {signal} на 1m']
        result['signal'] = 'WAIT'
        result['entry'] = result['stop'] = result['target'] = result['rr'] = None
        result['slippage_pct'] = None
        result['confidence'] = None

    return result


def analyze(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]

    utc_hour = datetime.now(timezone.utc).hour
    dead_hours = 0 <= utc_hour < 6  # 00-06 UTC — low liquidity window

    volume_spike = bool(last['volume_spike'])
    bb_squeeze = bool(last['bb_squeeze'])
    volume = last['volume']
    volume_ma20 = last['volume_ma20']
    atr = last['atr']

    # ── Step 1: WAIT conditions ───────────────────────────────────────────────
    wait_reasons = check_wait_conditions(df, _cfg)
    if wait_reasons:
        momentum = momentum_direction(df)
        return _build_result(last, 'WAIT', None, None, None, None, wait_reasons,
                             momentum, volume_spike, bb_squeeze, volume, volume_ma20, atr, dead_hours)

    # ── Step 2: Directional scoring and level computation ─────────────────────
    scored = score_direction(df, _cfg)
    momentum = scored['momentum']

    if scored['direction'] == 'WAIT':
        return _build_result(last, 'WAIT', None, None, None, None, scored['signal_reasons'],
                             momentum, volume_spike, bb_squeeze, volume, volume_ma20, atr, dead_hours)

    return _build_result(
        last, scored['direction'], scored['entry'], scored['stop'],
        scored['target'], scored['rr'], scored['signal_reasons'],
        momentum, volume_spike, bb_squeeze, volume, volume_ma20, atr, dead_hours,
        scored['effective_slip'],
    )


def _build_result(last, signal, entry, stop, target, rr, signal_reasons,
                  momentum, volume_spike, bb_squeeze, volume, volume_ma20, atr, dead_hours=False,
                  effective_slip=None):
    price = last['close']
    rsi = last['rsi']
    ema9 = last['ema9']
    ema21 = last['ema21']
    vwap = last['vwap']

    # Confidence
    if signal == 'WAIT':
        confidence = None
    elif volume_spike and len(signal_reasons) == 0:
        confidence = 'HIGH'
    elif len(signal_reasons) == 0:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW'

    # Time-of-day filter: dead hours 00-06 UTC → downgrade confidence one level
    if dead_hours and confidence is not None:
        conf_map = {'HIGH': 'MEDIUM', 'MEDIUM': 'LOW', 'LOW': 'LOW'}
        confidence = conf_map[confidence]
        signal_reasons = list(signal_reasons) + ['⚠ мёртвые часы 00-06 UTC — пониженная ликвидность']

    return {
        'timestamp': last['timestamp'].strftime('%Y-%m-%d %H:%M') if hasattr(last['timestamp'], 'strftime') else str(last['timestamp']),
        'price': price,
        'signal': signal,
        'entry': entry,
        'stop': stop,
        'target': target,
        'rr': rr,
        'slippage_pct': (effective_slip if effective_slip is not None else SLIPPAGE_PCT) if signal in ('LONG', 'SHORT') else None,
        'confidence': confidence,
        'indicators': {
            'ema9': round(ema9, 4),
            'ema21': round(ema21, 4),
            'ema_trend': 'bullish' if ema9 > ema21 else 'bearish',
            'rsi': round(rsi, 1) if pd.notna(rsi) else None,
            'vwap': round(vwap, 4),
            'price_vs_vwap': 'above' if price > vwap else 'below',
            'volume': round(volume, 2),
            'volume_ma20': round(volume_ma20, 2) if pd.notna(volume_ma20) else None,
            'volume_ratio': round(volume / volume_ma20, 2) if pd.notna(volume_ma20) and volume_ma20 > 0 else None,
            'volume_spike': volume_spike,
            'bb_squeeze': bb_squeeze,
            'atr': round(atr, 4) if pd.notna(atr) else None,
            'momentum': momentum,
            'upper_wick_ratio': round((last['high'] - max(last['close'], last['open'])) / (last['high'] - last['low']), 2) if last['high'] > last['low'] else 0.0,
            'lower_wick_ratio': round((min(last['close'], last['open']) - last['low']) / (last['high'] - last['low']), 2) if last['high'] > last['low'] else 0.0,
        },
        'wait_reasons': signal_reasons,
    }


def main():
    parser = argparse.ArgumentParser(description='Fast rule-based signal analyzer')
    parser.add_argument('--symbol', default='BTC/USDT', help='Trading pair (default: BTC/USDT)')
    parser.add_argument('--timeframe', default='1m', help='Timeframe: 1m or 5m (default: 1m)')
    parser.add_argument('--no-cache', action='store_true', help='Force live fetch')
    parser.add_argument('--no-mtf', action='store_true', help='Skip 5m MTF trend filter')
    parser.add_argument('--json', action='store_true', help='Output raw JSON instead of formatted text')
    parser.add_argument('--highliq', action='store_true', help='Use high-liquidity config (BTC/ETH)')
    args = parser.parse_args()

    # Load 1m data
    df = None
    if not args.no_cache:
        df = load_cache(args.symbol, args.timeframe)

    if df is None:
        print('[info] fetching live data...', file=sys.stderr)
        df = fetch_live(args.symbol, args.timeframe)

    if df is None or df.empty:
        print('Error: no data available', file=sys.stderr)
        sys.exit(1)

    df = recalculate_lowliq_indicators(df)
    result = analyze(df)

    # MTF confirmation: load 5m trend, block signals that contradict it
    use_mtf = MTF_FILTER and not args.no_mtf
    trend_5m = None
    if use_mtf:
        trend_5m = get_5m_trend(args.symbol, args.no_cache)
        if trend_5m is not None and result['signal'] in ('LONG', 'SHORT'):
            result = apply_mtf_filter(result, trend_5m)
    result['mtf'] = trend_5m

    # BTC correlation filter: downgrade confidence if BTC trend opposes signal
    btc_trend = None
    if args.symbol != 'BTC/USDT' and result['signal'] in ('LONG', 'SHORT'):
        btc_trend = get_5m_trend('BTC/USDT', args.no_cache)
        if btc_trend is not None:
            result = apply_btc_filter(result, btc_trend)
    result['btc_trend'] = btc_trend

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result, args.symbol, args.timeframe, VOLUME_WAIT_RATIO))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Continuous signal monitor.
Checks analyze_lowliq signals on a loop and alerts when LONG/SHORT appears.
Uses macOS system notifications + terminal bell.

Usage:
    python monitor.py                              # SUI/USDT, every 30s
    python monitor.py --symbols SUI/USDT ETH/USDT # multiple pairs
    python monitor.py --interval 60               # check every 60s
    python monitor.py --min-confidence MEDIUM     # only MEDIUM/HIGH alerts
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone

# Import logic directly from analyze_lowliq (no subprocess overhead)
from analyze import (
    analyze,
    apply_btc_filter,
    apply_mtf_filter,
    fetch_live,
    get_5m_trend,
    load_cache,
    recalculate_lowliq_indicators,
)
from config.lowliq import MTF_FILTER, VOLUME_WAIT_RATIO
from core.render import render

CONF_RANK = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}


def notify_macos(title: str, message: str) -> None:
    """Send macOS system notification with sound."""
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    subprocess.run(['osascript', '-e', script], capture_output=True)


def check_signal(symbol: str) -> dict | None:
    df = load_cache(symbol, '1m')
    if df is None:
        df = fetch_live(symbol, '1m')
    if df is None or df.empty:
        return None

    df = recalculate_lowliq_indicators(df)
    result = analyze(df)

    if MTF_FILTER and result['signal'] in ('LONG', 'SHORT'):
        trend_5m = get_5m_trend(symbol)
        if trend_5m is not None:
            result = apply_mtf_filter(result, trend_5m)
        result['mtf'] = trend_5m
    else:
        result.setdefault('mtf', None)

    if symbol != 'BTC/USDT' and result['signal'] in ('LONG', 'SHORT'):
        btc_trend = get_5m_trend('BTC/USDT')
        if btc_trend is not None:
            result = apply_btc_filter(result, btc_trend)
        result['btc_trend'] = btc_trend
    else:
        result.setdefault('btc_trend', None)

    return result


def fmt_price(price: float) -> str:
    return f"{price:.4f}" if price < 10 else f"{price:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description='Continuous signal monitor using analyze_lowliq')
    parser.add_argument('--symbols', nargs='+', default=['SUI/USDT'],
                        help='Symbols to watch (default: SUI/USDT)')
    parser.add_argument('--interval', type=int, default=30,
                        help='Check interval in seconds (default: 30)')
    parser.add_argument('--min-confidence', default='LOW', choices=['LOW', 'MEDIUM', 'HIGH'],
                        help='Minimum confidence to trigger alert (default: LOW)')
    args = parser.parse_args()

    min_rank = CONF_RANK[args.min_confidence]
    # symbol -> last alerted direction ('LONG' | 'SHORT' | None)
    last_direction: dict[str, str | None] = {s: None for s in args.symbols}

    print(f"[monitor] Watching: {', '.join(args.symbols)}")
    print(f"[monitor] Interval: {args.interval}s  |  Min confidence: {args.min_confidence}")
    print("[monitor] Press Ctrl+C to stop\n")

    while True:
        now = datetime.now(timezone.utc).strftime('%H:%M:%S')

        for symbol in args.symbols:
            try:
                result = check_signal(symbol)
                if result is None:
                    print(f"[{now}] {symbol}: нет данных")
                    continue

                sig = result['signal']
                conf = result.get('confidence')
                price = result['price']
                conf_str = conf or '—'

                # Status line (always printed)
                print(f"[{now}] {symbol}: {sig:<5}  {fmt_price(price)}  conf={conf_str}")

                if sig in ('LONG', 'SHORT'):
                    rank = CONF_RANK.get(conf, 0)
                    direction_changed = last_direction[symbol] != sig

                    if direction_changed and rank >= min_rank:
                        last_direction[symbol] = sig

                        # Terminal bell
                        sys.stdout.write('\a')
                        sys.stdout.flush()

                        # Full signal printout
                        print(render(result, symbol, '1m', VOLUME_WAIT_RATIO))

                        # macOS notification
                        icon = '🟢' if sig == 'LONG' else '🔴'
                        title = f"{icon} {sig} — {symbol}"
                        body = (
                            f"Entry: {fmt_price(result['entry'])}  "
                            f"Stop: {fmt_price(result['stop'])}  "
                            f"R/R: 1:{result['rr']}  [{conf}]"
                        )
                        notify_macos(title, body)

                    elif direction_changed and rank < min_rank:
                        # Signal appeared but below confidence threshold
                        last_direction[symbol] = sig
                        print(f"  ↳ сигнал {sig} (conf={conf_str}) — ниже порога {args.min_confidence}, пропускаем")

                else:
                    # Back to WAIT — reset so next LONG/SHORT will alert again
                    last_direction[symbol] = None

            except Exception as e:
                print(f"[{now}] {symbol}: ошибка — {e}")

        time.sleep(args.interval)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n[monitor] Остановлен.')

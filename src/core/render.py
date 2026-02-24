"""
Rendering logic for signal output.
Accepts a result dict produced by analyze.py and formats it for terminal display.
"""


def fmt_price(price: float) -> str:
    """Format price with appropriate precision: 4dp if < 10, else 2dp."""
    return f"{price:.4f}" if price < 10 else f"{price:.2f}"


def render(result: dict, symbol: str, timeframe: str, volume_wait_ratio: float) -> str:
    ind = result['indicators']
    lines = []

    # Header
    lines.append(f"\n{'─'*52}")
    lines.append(f"  {symbol}  |  {timeframe}  |  {result['timestamp']} UTC")
    lines.append(f"  Цена: {fmt_price(result['price'])}")
    lines.append(f"{'─'*52}")

    # Signal block
    signal = result['signal']
    signal_label = {'LONG': '🟢 LONG', 'SHORT': '🔴 SHORT', 'WAIT': '⏸  WAIT'}.get(signal, signal)
    lines.append(f"\n  Signal:  {signal_label}")

    if signal != 'WAIT' and result['entry'] is not None:
        slip = result.get('slippage_pct')
        slip_note = f"  (+{slip*100:.2f}% slip)" if slip else ""
        lines.append(f"  Entry:   {fmt_price(result['entry'])}{slip_note}")
        lines.append(f"  Stop:    {fmt_price(result['stop'])}")
        lines.append(f"  Target:  {fmt_price(result['target'])}")
        lines.append(f"  R/R:     1:{result['rr']:.1f}")
    elif result['wait_reasons']:
        lines.append(f"\n  Причины WAIT:")
        for r in result['wait_reasons']:
            lines.append(f"    • {r}")

    # Indicators
    rsi_val = ind['rsi']
    rsi_note = ''
    if rsi_val is not None:
        if rsi_val > 70:
            rsi_note = ' ⚠ перекуплен'
        elif rsi_val < 30:
            rsi_note = ' ⚠ перепродан'
        elif 45 <= rsi_val <= 55:
            rsi_note = ' — нейтральный'

    vol_ratio = ind['volume_ratio']
    vol_note = ''
    if vol_ratio is not None:
        if ind['volume_spike']:
            vol_note = ' 🔥 SPIKE'
        elif vol_ratio < volume_wait_ratio:
            vol_note = ' ⚠ низкий'

    bb_note = ' ⚡ squeeze' if ind['bb_squeeze'] else ''

    lines.append(f"\n  Reasoning:")
    lines.append(f"    EMA:     {fmt_price(ind['ema9'])} / {fmt_price(ind['ema21'])}  — {ind['ema_trend']}")
    lines.append(f"    RSI:     {rsi_val:.1f}{rsi_note}" if rsi_val is not None else "    RSI:     —")
    vol_str = f"{ind['volume']:.1f}"
    if ind['volume_ma20']:
        vol_str += f" / avg {ind['volume_ma20']:.1f} ({vol_ratio:.2f}x)"
    lines.append(f"    Volume:  {vol_str}{vol_note}")
    lines.append(f"    BB:      {'squeeze' if ind['bb_squeeze'] else 'normal'}{bb_note}")
    lines.append(f"    VWAP:    {fmt_price(ind['vwap'])}  — цена {ind['price_vs_vwap']}")
    lines.append(f"    Момент.: {ind['momentum']}")

    mtf = result.get('mtf')
    if mtf:
        trend_icon = {'bullish': '↑', 'bearish': '↓', 'neutral': '→'}.get(mtf['trend'], '?')
        lines.append(
            f"    5m MTF:  {trend_icon} {mtf['trend']}"
            f"  EMA {fmt_price(mtf['ema9'])}/{fmt_price(mtf['ema21'])}"
            f"  VWAP {fmt_price(mtf['vwap'])}"
        )

    btc = result.get('btc_trend')
    if btc:
        btc_icon = {'bullish': '↑', 'bearish': '↓', 'neutral': '→'}.get(btc['trend'], '?')
        lines.append(f"    BTC:     {btc_icon} {btc['trend']}  VWAP {fmt_price(btc['vwap'])}")

    if result['confidence']:
        conf_label = {'HIGH': '🔥 HIGH', 'MEDIUM': 'MEDIUM', 'LOW': 'LOW'}.get(result['confidence'])
        lines.append(f"\n  Confidence: {conf_label}")

    lines.append(f"{'─'*52}\n")
    return '\n'.join(lines)

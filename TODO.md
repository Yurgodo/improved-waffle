# TODO: analyze_lowliq.py improvements

## P0 — Critical (affect signal accuracy)

- [x] **Slippage на обе ноги сделки** — сейчас slippage применяется только к entry, но stop и target тоже подвержены slippage. R/R завышен, что приводит к ложным сигналам. Нужно учитывать slippage при расчёте risk и reward.

- [x] **Volume spike + candle body check** — spike без проверки характера свечи даёт ложные подтверждения. Spike на длинном верхнем wick (rejection) не должен подтверждать LONG. Проверять: spike на bullish candle → long confirmation, spike на bearish candle → short confirmation.

## P1 — Important (значительно улучшат точность)

- [x] **Bid-ask spread учёт** — для low-liq пар спред 0.03-0.10% сопоставим со slippage. Close — это last trade, не mid-price. Как минимум удвоить slippage для компенсации, в идеале — подтягивать spread из API.

- [x] **Wick ratio фильтр** — длинные тени = rejection. Для low-liq пар это ключевой паттерн, который скрипт полностью игнорирует. Добавить анализ upper/lower wick vs candle body.

## P2 — Improvements (повысят качество сигналов)

- [ ] **Градация scoring** — RSI 44 и RSI 20 дают одинаковый score +1. Нужна нелинейная шкала: RSI < 30 → +2, RSI 30-45 → +1. То же для volume ratio и других факторов.

- [ ] **Post-squeeze breakout detection** — BB squeeze корректно даёт WAIT, но первая свеча после выхода из squeeze — сильный сигнал, который теряется. Добавить детекцию направления пробоя.

## P3 — Minor (nice to have)

- [ ] **Momentum window 5-7 свечей** — 3 свечи на 1m = 3 минуты, одна аномальная свеча (ликвидация, fat finger) перевешивает. Увеличить окно + decay-веса для устойчивости к шуму.

## Баги / мёртвый код

- [ ] **Мёртвый код строка 318-321** — проверка `if rr < RR_MIN` недостижима (логика выше гарантирует rr >= RR_MIN). Убрать или переписать как assert.

- [ ] **VWAP reset по UTC-дате** — Binance Futures VWAP считается непрерывно, reset в полночь расходится с тем, что видят другие участники. Рассмотреть cumulative VWAP или session-based reset.

- [ ] **Dead hours filter слишком мягкий** — 00-06 UTC для low-liq пар = manipulation zone. Downgrade на один уровень confidence недостаточен. Расширять stop (ATR_STOP_MULT * 1.5) или давать WAIT.

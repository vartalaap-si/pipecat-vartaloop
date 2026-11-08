# Vartaloop TTS bench — Pipecat service — 2026-11-08 01:51 — https://api.vartaloop.ai

## Latency (8 interleaved iterations, warm)

| path | text | TTFA p50 ms | TTFA p95 ms | E2E p50 ms | audio s | service − raw TTFA p50 ms |
|---|---|---|---|---|---|---|
| ws/raw | 1s | 40.2 | 53.0 | 326 | 2.92 |  |
| pipecat/ws | 1s | 41.9 | 49.9 | 343 | 3.12 | +1.6 |
| ws/raw | 3s | 46.1 | 50.4 | 1610 | 15.00 |  |
| pipecat/ws | 3s | 41.1 | 43.3 | 1555 | 14.88 | -2.6 |

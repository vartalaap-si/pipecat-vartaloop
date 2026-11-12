# Changelog

## 0.1.1 — 2026-11-12

- First release on PyPI: `uv add pipecat-vartaloop`. Same code as 0.1.0; the sdist no longer carries the demo recording and the benchmark.

## 0.1.0 — 2026-11-07

- Published as the community package `pipecat-vartaloop`, imported as `pipecat_vartaloop`.
- `VartaloopTTSService` (WebSocket, one connection per session, one utterance per sentence, audio tagged with the turn's context) and `VartaloopHttpTTSService` (HTTP, chunked body forwarded as it arrives).
- Settings: `voice`, `expression`, `digits`, `speed`, `temperature`, `seed`, `postfx`, `profile`, `raw`; all runtime-updatable with `TTSUpdateSettingsFrame`.

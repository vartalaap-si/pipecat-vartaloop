# Changelog

## 0.1.0 — 2026-11-07

- `VartalaapTTSService` (WebSocket, one connection per session, one utterance per sentence, audio tagged with the turn's context) and `VartalaapHttpTTSService` (HTTP, chunked body forwarded as it arrives).
- Settings: `voice`, `expression`, `digits`, `speed`, `temperature`, `seed`, `postfx`, `profile`, `raw`; all runtime-updatable with `TTSUpdateSettingsFrame`.

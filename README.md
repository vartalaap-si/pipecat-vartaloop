# pipecat-ai-vartaloop

[Vartaloop](https://vartaloop.ai) text-to-speech for [Pipecat](https://github.com/pipecat-ai/pipecat): Hinglish and
Indian-language voices (model `narad`), streamed from the first 80 ms frame. This repository is the development home of
`pipecat.services.vartaloop`, proposed to Pipecat core; it is also installable on its own.

Tested with Pipecat 1.15 (`main`, 2026-11-07). Maintained by Vartaloop, the company behind the service.

```bash
uv add pipecat-ai-vartaloop          # or: uv add "pipecat-ai[vartaloop]" once merged upstream
export VARTALOOP_API_KEY=vt_live_…    # from https://tts.vartaloop.ai
```

```python
from pipecat.services.vartaloop.tts import VartaloopTTSService

tts = VartaloopTTSService(
    api_key=os.environ["VARTALOOP_API_KEY"],
    settings=VartaloopTTSService.Settings(voice="saanvi", expression="neutral", digits="auto"),
)
pipeline = Pipeline([transport.input(), stt, user_aggregator, llm, tts, transport.output(), assistant_aggregator])
```

## Services

| class | base | transport | use when |
|---|---|---|---|
| `VartaloopTTSService` | `WebsocketTTSService` | one `WS /v1/tts/stream` per session | conversational agents: every sentence of a turn is its own utterance, sent as soon as it is aggregated; audio frames carry the turn's `context_id`, so an interrupted turn's leftovers are dropped, and the socket is reopened to cancel what the server was still synthesising |
| `VartaloopHttpTTSService` | `TTSService` | `POST /v1/tts`, chunked | pipelines without interruptions; the body is forwarded chunk by chunk |

Frames: `TTSStartedFrame` → `TTSAudioRawFrame` (16-bit PCM, 24 kHz, resampled to the pipeline rate when it differs) →
`TTSStoppedFrame`, with `TTSTextFrame` for the spoken text. TTFB metrics stop on the server's `first_audio_ms` event
(WebSocket) or the first body chunk (HTTP).

## Settings

`VartaloopTTSService.Settings` (a `TTSSettings`); every field can be changed at runtime with `TTSUpdateSettingsFrame`
and applies from the next sentence without reconnecting.

| field | default | API field | notes |
|---|---|---|---|
| `voice` | `saanvi` | `voice` | any id from `GET /v1/voices`; the voice decides the language and the normaliser |
| `model` | `narad` | — | the model family; the server picks the model from the voice |
| `expression` (alias `style`) | `neutral` | `style` | `excited`, `sad`, `whisper` on the voices that carry them |
| `digits` | `auto` | `digits` | `hi`, `mixed`, `en`, `auto` |
| `speed` (alias `pace`) | voice's pace | `speed` | 0.5–2.0 |
| `temperature` | server 0.3 | `temperature` | 0–2 |
| `seed` | random | `seed` | |
| `postfx` | server on | `postfx` | |
| `profile` | `default` | `profile` | `telephony` |
| `raw` | `False` | `raw` | skip the normaliser |
| `language` | `None` | — | not a parameter: the voice decides |

## Example

`examples/voice-vartaloop.py` is a complete voice agent (`uv run python examples/voice-vartaloop.py` with the Pipecat
runner; `--transport webrtc` opens a browser client). `examples/voice-vartaloop-http.py` is the HTTP variant.

## Benchmark

`bench/bench.py` times the service through a real pipeline (TTSStartedFrame to the first TTSAudioRawFrame, then to
TTSStoppedFrame) against raw WebSocket calls to the same API, interleaved so network drift hits both alike. From a Mac
on a home connection to `api.vartaloop.ai` (Mumbai), 2026-11-08, 8 iterations, warm prefill cache:

| path | text | TTFA p50 ms | TTFA p95 ms | E2E p50 ms | audio s | service − raw TTFA p50 ms |
|---|---|---|---|---|---|---|
| ws/raw | 1s | 40.2 | 53.0 | 326 | 2.92 |  |
| pipecat/ws | 1s | 41.9 | 49.9 | 343 | 3.12 | +1.6 |
| ws/raw | 3s | 46.1 | 50.4 | 1610 | 15.00 |  |
| pipecat/ws | 3s | 41.1 | 43.3 | 1555 | 14.88 | -2.6 |

The service adds about 2 ms to time-to-first-audio over a raw WebSocket call (within the run-to-run noise); the
3-sentence turn is three utterances sent back to back, so its audio flows without a gap between sentences. Raw numbers:
`bench/RESULTS.md`.

## Tests

```bash
uv run pytest tests/test_vartaloop_tts.py -n 0     # a fake Vartaloop WebSocket server speaks the real protocol
```

## Docs

`docs/vartaloop.mdx` is the service page for [pipecat-ai/docs](https://github.com/pipecat-ai/docs).

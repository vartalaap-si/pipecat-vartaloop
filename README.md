# pipecat-ai-vartalaap

[Vartalaap](https://vartalaap.si) text-to-speech for [Pipecat](https://github.com/pipecat-ai/pipecat): Hinglish and
Indian-language voices (model `narad`), streamed from the first 80 ms frame. This repository is the development home of
`pipecat.services.vartalaap`, proposed to Pipecat core; it is also installable on its own.

Tested with Pipecat 1.15 (`main`, 2026-11-07). Maintained by Vartalaap, the company behind the service.

```bash
uv add pipecat-ai-vartalaap          # or: uv add "pipecat-ai[vartalaap]" once merged upstream
export VARTALAAP_API_KEY=vt_live_…    # from https://tts.vartaloop.ai
```

```python
from pipecat.services.vartalaap.tts import VartalaapTTSService

tts = VartalaapTTSService(
    api_key=os.environ["VARTALAAP_API_KEY"],
    settings=VartalaapTTSService.Settings(voice="saanvi", expression="neutral", digits="auto"),
)
pipeline = Pipeline([transport.input(), stt, user_aggregator, llm, tts, transport.output(), assistant_aggregator])
```

## Services

| class | base | transport | use when |
|---|---|---|---|
| `VartalaapTTSService` | `WebsocketTTSService` | one `WS /v1/tts/stream` per session | conversational agents: every sentence of a turn is its own utterance, sent as soon as it is aggregated; audio frames carry the turn's `context_id`, so an interrupted turn's leftovers are dropped, and the socket is reopened to cancel what the server was still synthesising |
| `VartalaapHttpTTSService` | `TTSService` | `POST /v1/tts`, chunked | pipelines without interruptions; the body is forwarded chunk by chunk |

Frames: `TTSStartedFrame` → `TTSAudioRawFrame` (16-bit PCM, 24 kHz, resampled to the pipeline rate when it differs) →
`TTSStoppedFrame`, with `TTSTextFrame` for the spoken text. TTFB metrics stop on the server's `first_audio_ms` event
(WebSocket) or the first body chunk (HTTP).

## Settings

`VartalaapTTSService.Settings` (a `TTSSettings`); every field can be changed at runtime with `TTSUpdateSettingsFrame`
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

`examples/voice-vartalaap.py` is a complete voice agent (`uv run python examples/voice-vartalaap.py` with the Pipecat
runner; `--transport webrtc` opens a browser client). `examples/voice-vartalaap-http.py` is the HTTP variant.

## Benchmark

`bench/bench.py` times the service through a real pipeline against raw WebSocket calls, interleaved. Results:
`bench/RESULTS.md` (pending the first run with a key).

## Tests

```bash
uv run pytest tests/test_vartalaap_tts.py -n 0     # a fake Vartalaap WebSocket server speaks the real protocol
```

## Docs

`docs/vartalaap.mdx` is the service page for [pipecat-ai/docs](https://github.com/pipecat-ai/docs).

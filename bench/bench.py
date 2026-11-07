"""Latency of Vartalaap TTS through the Pipecat services vs the raw API, from this machine.

    VARTALAAP_API_KEY=... uv run python bench/bench.py [--iters 8] [--concurrency 8,16] [--seconds 20]

The Pipecat path drives a real pipeline (``run_test`` harness): a TTSSpeakFrame goes in, the
time from the TTSStartedFrame to the first TTSAudioRawFrame is the service's TTFA, to the
TTSStoppedFrame its E2E. The raw path sends the same text over one WebSocket and times the
first binary frame. Audio is pcm16 at 24 kHz (48000 bytes per second of speech).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field

import aiohttp

ONE = "नमस्ते, आपका loan approve हो गया है।"
THREE = (
    "नमस्ते, आपका loan approve हो गया है। "
    "पहली EMI 5 नवंबर को 12,450 रुपये की होगी। "
    "कोई सवाल हो तो हमें 1800 123 4567 पर call करें।"
)
BYTES_PER_S = 24000 * 2


@dataclass
class Sample:
    ttfa_ms: float
    e2e_ms: float
    audio_s: float


@dataclass
class Series:
    name: str
    samples: list[Sample] = field(default_factory=list)

    def p(self, attr: str, q: float) -> float:
        xs = sorted(getattr(s, attr) for s in self.samples)
        k = min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))
        return xs[k]

    def median(self, attr: str) -> float:
        return statistics.median(getattr(s, attr) for s in self.samples)


class RawWS:
    def __init__(self, session: aiohttp.ClientSession, base: str, key: str) -> None:
        self._session, self._base, self._key = session, base, key
        self._ws = None

    async def connect(self) -> None:
        self._ws = await self._session.ws_connect(
            self._base.replace("http", "ws", 1) + "/v1/tts/stream",
            headers={"Authorization": f"Bearer {self._key}"},
        )

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()

    async def speak(self, sentences: list[str]) -> Sample:
        t0 = time.perf_counter()
        for i, s in enumerate(sentences):
            await self._ws.send_str(
                json.dumps(
                    {
                        "text": s,
                        "voice": "saanvi",
                        "format": "pcm16",
                        "digits": "auto",
                        "request_id": f"b{i}",
                    }
                )
            )
        first, n, ended = None, 0, 0
        while ended < len(sentences):
            msg = await self._ws.receive(timeout=30)
            if msg.type == aiohttp.WSMsgType.BINARY:
                first = first or time.perf_counter()
                n += len(msg.data)
            elif msg.type == aiohttp.WSMsgType.TEXT:
                ev = json.loads(msg.data)
                if ev.get("type") == "end":
                    ended += 1
                elif ev.get("type") == "error":
                    raise RuntimeError(f"WS error: {ev}")
            else:
                raise RuntimeError(f"WS closed: {msg.type}")
        return Sample((first - t0) * 1e3, (time.perf_counter() - t0) * 1e3, n / BYTES_PER_S)


def sentences_of(text: str) -> list[str]:
    return [s.strip() + "।" for s in text.split("।") if s.strip()]


class _TurnTimer:
    """Times TTSStartedFrame -> first TTSAudioRawFrame -> TTSStoppedFrame for the current turn."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.t_start = self.t_first = self.t_stop = None
        self.n = 0
        self.done = asyncio.Event()


class _Sink:
    """One running pipeline per service: the WebSocket stays connected across turns."""

    def __init__(self, tts) -> None:
        from pipecat.frames.frames import Frame, TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.worker import PipelineParams, PipelineWorker
        from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
        from pipecat.workers.runner import WorkerRunner

        timer = self.timer = _TurnTimer()

        class Sink(FrameProcessor):
            async def process_frame(self, frame: Frame, direction: FrameDirection):
                await super().process_frame(frame, direction)
                if isinstance(frame, TTSStartedFrame):
                    timer.t_start = time.perf_counter()
                elif isinstance(frame, TTSAudioRawFrame):
                    timer.t_first = timer.t_first or time.perf_counter()
                    timer.n += len(frame.audio)
                elif isinstance(frame, TTSStoppedFrame):
                    timer.t_stop = time.perf_counter()
                    timer.done.set()
                await self.push_frame(frame, direction)

        self.worker = PipelineWorker(
            Pipeline([tts, Sink()]), params=PipelineParams(enable_metrics=False)
        )
        self.runner = WorkerRunner(handle_sigint=False)
        self.task = None

    async def start(self) -> None:
        await self.runner.add_workers(self.worker)
        self.task = asyncio.create_task(self.runner.run(auto_end=False))
        await asyncio.sleep(0.5)  # setup + WebSocket connect

    async def stop(self) -> None:
        try:
            await asyncio.wait_for(self.runner.cancel(), 5)
        except Exception:  # noqa: BLE001, S110
            pass
        if self.task:
            self.task.cancel()

    async def turn(self, text: str) -> Sample:
        """Speak ``text`` as one LLM turn; TTFA counts from the first utterance being sent."""
        from pipecat.frames.frames import (
            LLMFullResponseEndFrame,
            LLMFullResponseStartFrame,
            LLMTextFrame,
        )

        self.timer.reset()
        await self.worker.queue_frames(
            [LLMFullResponseStartFrame(), LLMTextFrame(text), LLMFullResponseEndFrame()]
        )
        await asyncio.wait_for(self.timer.done.wait(), 60)
        t = self.timer
        return Sample(
            (t.t_first - t.t_start) * 1e3, (t.t_stop - t.t_start) * 1e3, t.n / BYTES_PER_S
        )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base-url", default=os.environ.get("VARTALAAP_BASE_URL", "https://api.vartaloop.ai")
    )
    ap.add_argument("--iters", type=int, default=8)
    args = ap.parse_args()
    key = os.environ.get("VARTALAAP_API_KEY") or sys.exit("set VARTALAAP_API_KEY")
    base = args.base_url.rstrip("/")

    from pipecat.services.vartalaap.tts import VartalaapTTSService

    print(f"# Vartalaap TTS bench — Pipecat service — {time.strftime('%Y-%m-%d %H:%M')} — {base}\n")
    series = {k: Series(k) for k in ("ws/raw/1s", "pipecat/ws/1s", "ws/raw/3s", "pipecat/ws/3s")}
    async with aiohttp.ClientSession() as session:
        raw = RawWS(session, base, key)
        await raw.connect()
        tts = VartalaapTTSService(api_key=key, url=base.replace("http", "ws", 1) + "/v1/tts/stream")
        pipe = _Sink(tts)
        await pipe.start()
        await raw.speak([ONE])
        await pipe.turn(ONE)  # warm
        for _ in range(args.iters):
            series["ws/raw/1s"].samples.append(await raw.speak([ONE]))
            series["pipecat/ws/1s"].samples.append(await pipe.turn(ONE))
            series["ws/raw/3s"].samples.append(await raw.speak(sentences_of(THREE)))
            series["pipecat/ws/3s"].samples.append(await pipe.turn(THREE))
        await raw.close()

    print(f"## Latency ({args.iters} interleaved iterations, warm)\n")
    print(
        "| path | text | TTFA p50 ms | TTFA p95 ms | E2E p50 ms | audio s | service − raw TTFA p50 ms |"
    )
    print("|---|---|---|---|---|---|---|")
    for text in ("1s", "3s"):
        r, p = series[f"ws/raw/{text}"], series[f"pipecat/ws/{text}"]
        for s, label in ((r, "ws/raw"), (p, "pipecat/ws")):
            delta = f"{p.median('ttfa_ms') - r.median('ttfa_ms'):+.1f}" if s is p else ""
            print(
                f"| {label} | {text} | {s.p('ttfa_ms', 0.5):.1f} | {s.p('ttfa_ms', 0.95):.1f} | {s.p('e2e_ms', 0.5):.0f} | {s.median('audio_s'):.2f} | {delta} |"
            )
    sys.stdout.flush()
    try:
        await asyncio.wait_for(pipe.stop(), 5)
    finally:
        # the pipeline's transport-less teardown can linger; the numbers are out, leave
        os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())

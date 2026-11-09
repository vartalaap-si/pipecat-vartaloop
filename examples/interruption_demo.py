#
# Copyright (c) 2026, Vartaloop
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Record a scripted call: a greeting, a barge-in mid-answer, the new answer, an expression change.

The sink keeps a playback clock, as an output transport would: audio is laid out in
real time from its arrival, and an interruption cuts everything not yet played.

    VARTALOOP_API_KEY=... python examples/interruption_demo.py out.wav events.json
"""

import array
import asyncio
import json
import math
import sys
import time
import wave

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InterruptionFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.workers.runner import WorkerRunner

from pipecat_vartaloop import VartaloopTTSService

RATE = 24000

GREETING = (
    "नमस्ते राहुल जी, मैं प्रिया बोल रही हूँ, आपके loan application के बारे में update देने के लिए call किया है।"
)
FIRST = (
    "आपका होम loan approve हो गया है। EMI हर महीने की पाँच तारीख को कटेगी, "
    "और पहली EMI अगले महीने से शुरू होगी। अगर आप चाहें तो मैं आपको पूरा repayment "
    "schedule SMS पर भेज सकती हूँ, जिसमें हर महीने का principal और interest अलग से दिखेगा।"
)
SECOND = (
    "बिल्कुल, आप loan की पूरी amount कभी भी prepay कर सकते हैं। Floating rate loan पर कोई "
    "prepayment charge नहीं लगता, और part payment भी कर सकते हैं, minimum पच्चीस हज़ार रुपये।"
)
CLOSING = "बहुत बधाई हो! आपका नया घर आपको ढेर सारी खुशियाँ दे। कोई और सवाल हो तो इसी नंबर पर call कीजिए।"


class PlaybackSink(FrameProcessor):
    """Lays audio out on a real-time playback clock and cuts it on interruption."""

    def __init__(self):
        super().__init__()
        self.t0 = time.perf_counter()
        self.pcm = array.array("h")
        self.events: list[dict] = []
        self.turn_started = asyncio.Event()
        self._dropped_context: str | None = None
        self._context: str | None = None
        self.late_frames = 0  # frames of the interrupted turn that still reached the sink

    def now(self) -> float:
        return time.perf_counter() - self.t0

    def _pad_to(self, seconds: float) -> None:
        n = int(seconds * RATE)
        if len(self.pcm) < n:
            self.pcm.extend([0] * (n - len(self.pcm)))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSStartedFrame):
            self._context = getattr(frame, "context_id", None)
            self.turn_started.set()
        elif isinstance(frame, InterruptionFrame):
            t = self.now()
            del self.pcm[int(t * RATE) :]  # what was not played yet is never heard
            self._dropped_context = self._context
            self.events.append({"t": round(t, 3), "event": "interruption"})
        elif isinstance(frame, TTSAudioRawFrame):
            ctx = getattr(frame, "context_id", None)
            if ctx is None or ctx != self._dropped_context:
                self._pad_to(self.now())  # playback can't start before the audio arrives
                if not any(e["event"] == "audio" and e.get("ctx") == ctx for e in self.events):
                    self.events.append(
                        {
                            "t": round(len(self.pcm) / RATE, 3),
                            "arrived": round(self.now(), 3),
                            "event": "audio",
                            "ctx": ctx,
                        }
                    )
                self.pcm.frombytes(frame.audio)
            else:
                self.late_frames += 1
        await self.push_frame(frame, direction)


def beep(sink: PlaybackSink, at: float, ms: int = 120) -> None:
    """A short tone where the user barges in, so the cut is easy to hear."""
    start = int(at * RATE)
    sink._pad_to(at + ms / 1000)
    for i in range(int(RATE * ms / 1000)):
        sink.pcm[start + i] = int(6000 * math.sin(2 * math.pi * 880 * i / RATE))


async def main(wav_path: str, events_path: str) -> None:
    tts = VartaloopTTSService(sample_rate=RATE)  # key from VARTALOOP_API_KEY
    sink = PlaybackSink()
    worker = PipelineWorker(Pipeline([tts, sink]), params=PipelineParams(enable_metrics=True))
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    run = asyncio.create_task(runner.run())
    await asyncio.sleep(0.8)

    async def say(text: str, wait: float, label: str = "agent") -> None:
        sink.events.append({"t": round(sink.now(), 3), "event": label, "text": text})
        await worker.queue_frames([TTSSpeakFrame(text)])
        await asyncio.sleep(wait)

    await say(GREETING, 9.0)
    await say(FIRST, 4.5)  # the user speaks over the agent here

    t_int = sink.now()
    await worker.queue_frames([InterruptionFrame()])
    await asyncio.sleep(0.05)
    beep(sink, t_int)
    sink.events.append(
        {"t": round(t_int, 3), "event": "user", "text": "क्या मैं loan जल्दी चुका सकता हूँ?"}
    )
    await asyncio.sleep(1.6)  # the user finishes the question

    await say(SECOND, 11.5)

    # a runtime settings change applies from the next sentence, on the same socket
    await worker.queue_frames(
        [TTSUpdateSettingsFrame(delta=VartaloopTTSService.Settings(expression="excited"))]
    )
    sink.events.append(
        {"t": round(sink.now(), 3), "event": "settings", "text": "expression=excited"}
    )
    await say(CLOSING, 8.5, label="agent-excited")

    await worker.queue_frames([EndFrame()])
    try:
        await asyncio.wait_for(run, 10)
    except TimeoutError:
        run.cancel()

    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(sink.pcm.tobytes())
    with open(events_path, "w") as f:
        json.dump(
            {"duration": len(sink.pcm) / RATE, "events": sink.events},
            f,
            ensure_ascii=False,
            indent=1,
        )
    print(
        "wrote",
        wav_path,
        f"{len(sink.pcm) / RATE:.1f} s,",
        sink.late_frames,
        "late frames of the interrupted turn",
    )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))

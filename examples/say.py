"""Speak one Hinglish sentence through a minimal Pipecat pipeline and write it to a WAV.

    VARTALAAP_API_KEY=... python examples/say.py "नमस्ते, आपका loan approve हो गया है।" out.wav

The pipeline is just the service and a sink: TTSStartedFrame, the TTSAudioRawFrames as the
server streams them, TTSStoppedFrame. The time from the first to the second is the TTFA.
"""

import asyncio
import sys
import time
import wave

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.workers.runner import WorkerRunner

from pipecat.services.vartalaap.tts import VartalaapTTSService


class WavSink(FrameProcessor):
    def __init__(self, path: str, sample_rate: int):
        super().__init__()
        self._wav = wave.open(path, "wb")  # noqa: SIM115 (closed on TTSStoppedFrame)
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(sample_rate)
        self._t0 = None
        self._first = None
        self.done = asyncio.Event()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSStartedFrame):
            self._t0 = time.perf_counter()
        elif isinstance(frame, TTSAudioRawFrame):
            if self._first is None and self._t0 is not None:
                self._first = time.perf_counter()
                print(f"first audio after {1e3 * (self._first - self._t0):.1f} ms")
            self._wav.writeframes(frame.audio)
        elif isinstance(frame, TTSStoppedFrame):
            print(f"done after {1e3 * (time.perf_counter() - self._t0):.0f} ms")
            self._wav.close()
            self.done.set()
        await self.push_frame(frame, direction)


async def main(text: str, path: str) -> None:
    tts = VartalaapTTSService(sample_rate=24000)  # key from VARTALAAP_API_KEY
    sink = WavSink(path, 24000)
    worker = PipelineWorker(Pipeline([tts, sink]), params=PipelineParams(enable_metrics=True))
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    run = asyncio.create_task(runner.run())
    await asyncio.sleep(0.5)  # setup: the WebSocket is opened here
    await worker.queue_frames([TTSSpeakFrame(text)])
    await asyncio.wait_for(sink.done.wait(), 60)
    await worker.queue_frames([EndFrame()])
    try:
        await asyncio.wait_for(run, 10)
    except TimeoutError:
        run.cancel()
    print("wrote", path)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out.wav"))

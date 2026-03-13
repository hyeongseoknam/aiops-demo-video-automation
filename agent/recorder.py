"""Screen recorder using ffmpeg x11grab on XWayland display."""

import asyncio
import logging
import signal

log = logging.getLogger(__name__)


class ScreenRecorder:
    def __init__(self, config: dict):
        rec = config.get("recording", {})
        self.display = rec.get("display", ":0")
        self.x = rec.get("x", 0)
        self.y = rec.get("y", 0)
        self.width = rec.get("width", 1920)
        self.height = rec.get("height", 1080)
        self.framerate = rec.get("framerate", 30)
        self.crf = rec.get("crf", 18)
        self.process: asyncio.subprocess.Process | None = None
        self.output_path: str | None = None

    async def start(self, output_path: str):
        self.output_path = output_path
        cmd = [
            "ffmpeg", "-y",
            "-f", "x11grab",
            "-framerate", str(self.framerate),
            "-video_size", f"{self.width}x{self.height}",
            "-i", f"{self.display}+{self.x},{self.y}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        log.info("Starting screen recording: %s (%dx%d)", output_path, self.width, self.height)
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def stop(self):
        if self.process and self.process.returncode is None:
            log.info("Stopping screen recording...")
            self.process.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                log.warning("ffmpeg did not exit gracefully, terminating")
                self.process.terminate()
                await self.process.wait()
            log.info("Recording saved: %s", self.output_path)
        self.process = None

    @property
    def is_recording(self) -> bool:
        return self.process is not None and self.process.returncode is None

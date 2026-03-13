"""K6 load generator subprocess management."""

import asyncio
import logging

log = logging.getLogger(__name__)


class K6Runner:
    def __init__(self, config: dict):
        k6_cfg = config["k6"]
        self.binary = k6_cfg["binary"]
        self.script = k6_cfg["script"]
        self.scripts_dir = k6_cfg.get("scripts_dir", "")
        self.duration = k6_cfg.get("duration", "5m")
        self.vus = k6_cfg.get("vus", 10)
        self.process: asyncio.subprocess.Process | None = None
        self.output_lines: list[str] = []
        self._reader_task: asyncio.Task | None = None

    async def start(self):
        cmd = [
            self.binary, "run",
            "--duration", self.duration,
            "--vus", str(self.vus),
            self.script,
        ]
        log.info("Starting k6: %s (duration=%s, vus=%d)", self.script, self.duration, self.vus)
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.scripts_dir or None,
        )
        self._reader_task = asyncio.create_task(self._read_output())

    async def _read_output(self):
        while self.process and self.process.stdout:
            line = await self.process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            self.output_lines.append(decoded)
            if len(self.output_lines) % 20 == 0:
                log.debug("k6 output: %d lines captured", len(self.output_lines))

    async def stop(self):
        if self.process and self.process.returncode is None:
            log.info("Stopping k6...")
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=15)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            log.info("k6 stopped (%d output lines captured)", len(self.output_lines))

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        self.process = None
        self._reader_task = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def get_output_text(self) -> str:
        return "\n".join(self.output_lines)

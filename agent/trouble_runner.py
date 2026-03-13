"""Chaos trouble scenario start/stop management."""

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class TroubleRunner:
    def __init__(self, config: dict):
        tc = config["trouble"]
        self.base_dir = tc["base_dir"]
        self.default_scenario = tc.get("scenario", "05_downstream_delay")
        self.default_port = tc.get("port", 8083)
        self.default_params = tc.get("params", ["5"])
        self.ssh_host = tc.get("ssh_host")
        self.output_lines: list[str] = []

    def _script_path(self, scenario: str, action: str) -> str:
        return str(Path(self.base_dir) / scenario / f"{action}.sh")

    async def _run_script(self, cmd: list[str], desc: str) -> tuple[bool, str]:
        log.info("Running %s: %s", desc, " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        self.output_lines.extend(output.strip().splitlines())

        if proc.returncode != 0:
            log.warning("%s exited with code %d", desc, proc.returncode)
        else:
            log.info("%s completed successfully", desc)

        return proc.returncode == 0, output

    async def start(
        self,
        scenario: str | None = None,
        port: int | None = None,
        params: list[str] | None = None,
    ) -> tuple[bool, str]:
        scenario = scenario or self.default_scenario
        port = port or self.default_port
        params = params if params is not None else self.default_params

        script = self._script_path(scenario, "start")
        if self.ssh_host:
            remote_cmd = f"bash {script} {port} {' '.join(params)}"
            cmd = ["ssh", self.ssh_host, remote_cmd]
        else:
            if not Path(script).exists():
                log.error("start.sh not found: %s", script)
                return False, f"Script not found: {script}"
            cmd = ["bash", script, str(port)] + params
        return await self._run_script(cmd, f"trouble start ({scenario})")

    async def stop(
        self,
        scenario: str | None = None,
        port: int | None = None,
    ) -> tuple[bool, str]:
        scenario = scenario or self.default_scenario
        port = port or self.default_port

        script = self._script_path(scenario, "stop")
        if self.ssh_host:
            remote_cmd = f"bash {script} {port}"
            cmd = ["ssh", self.ssh_host, remote_cmd]
        else:
            if not Path(script).exists():
                log.error("stop.sh not found: %s", script)
                return False, f"Script not found: {script}"
            cmd = ["bash", script, str(port)]
        return await self._run_script(cmd, f"trouble stop ({scenario})")

    async def stop_all(self) -> bool:
        """Stop all running troubles to ensure clean starting state."""
        log.info("Stopping all troubles to ensure clean state...")
        # Stop the configured scenario
        success, _ = await self.stop()
        # Give it time to fully stop
        await asyncio.sleep(3)
        return success

    def get_output_text(self) -> str:
        return "\n".join(self.output_lines)

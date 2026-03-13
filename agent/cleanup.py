"""Pre-recording cleanup to ensure clean baseline state."""

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class SystemCleanup:
    def __init__(self, config: dict):
        tc = config["trouble"]
        self.base_dir = tc["base_dir"]
        self.ssh_host = tc.get("ssh_host")
        self.default_port = tc.get("port", 8083)

    async def stop_all_scenarios(self) -> bool:
        """Stop ALL trouble scenarios (01-12), not just the configured one."""
        log.info("Stopping ALL trouble scenarios to ensure clean state...")

        # List of all known scenarios
        scenarios = [
            ("01_cpu_spike", 8081),
            ("02_memory_leak", 8082),
            ("03_db_timeout", 8083),
            ("04_slow_query", 8083),
            ("05_downstream_delay", 8083),
            ("06_downstream_error", 8083),
            ("07_pool_exhaustion", 8083),
            ("08_thread_deadlock", 8083),
            ("09_network_delay", 8083),
            ("10_random_crash", 8083),
            ("11_mysql_dblock", 3306),
            ("12_mysql_column_error", 3306),
        ]

        success_count = 0
        for scenario, port in scenarios:
            script = f"{self.base_dir}/{scenario}/stop.sh"

            if self.ssh_host:
                remote_cmd = f"bash {script} {port} 2>/dev/null || true"
                cmd = ["ssh", self.ssh_host, remote_cmd]
            else:
                cmd = ["bash", script, str(port)]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if proc.returncode == 0:
                success_count += 1
                log.info("  ✓ Stopped: %s", scenario)
            else:
                log.debug("  - Skipped: %s (not running or doesn't exist)", scenario)

        log.info("Stopped %d scenarios", success_count)
        return True

    async def wait_for_stabilization(self, minutes: int = 10) -> bool:
        """Wait for metrics to stabilize with periodic status updates."""
        log.info("=" * 60)
        log.info("WAITING FOR SYSTEM STABILIZATION")
        log.info("=" * 60)
        log.info("Duration: %d minutes", minutes)
        log.info("This ensures clean baseline metrics before recording.")
        log.info("")

        total_seconds = minutes * 60
        check_interval = 30  # Check every 30 seconds

        for elapsed in range(0, total_seconds, check_interval):
            remaining = total_seconds - elapsed
            mins = remaining // 60
            secs = remaining % 60

            log.info("  ⏳ Stabilizing... %dm %ds remaining", mins, secs)
            await asyncio.sleep(check_interval)

        log.info("✓ System should be stable now")
        log.info("=" * 60)
        return True

    async def full_cleanup(self, wait_minutes: int = 10) -> bool:
        """Complete cleanup: stop all + wait for stabilization."""
        await self.stop_all_scenarios()
        await self.wait_for_stabilization(wait_minutes)
        return True

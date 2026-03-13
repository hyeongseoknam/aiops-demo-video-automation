#!/usr/bin/env python3
"""AIOps Demo Video Automation Agent — CLI entry point.

K6 load generation is managed externally by the user.
Start k6 before running this agent.
"""

import argparse
import asyncio
import os
import sys

from agent.orchestrator import Orchestrator
from agent.utils import load_config, setup_logging


def main():
    parser = argparse.ArgumentParser(
        description="AIOps Demo Video Automation Agent"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/scenario.yaml",
        help="Path to scenario YAML config (default: config/scenario.yaml)",
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Output directory (default: output)",
    )
    parser.add_argument(
        "--skip-trouble",
        action="store_true",
        help="Skip trouble scenario injection/recovery",
    )
    parser.add_argument(
        "--skip-postprocess",
        action="store_true",
        help="Skip post-processing (raw recording only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pre-flight checks only",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continue even if pre-flight checks fail",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Run cleanup and stabilization, then exit (no recording)",
    )
    parser.add_argument(
        "--scenario",
        help="Override trouble scenario (e.g., 01_cpu_spike, 05_downstream_delay)",
    )
    parser.add_argument(
        "--scenario-port",
        type=int,
        help="Override trouble scenario port (e.g., 8081, 8083)",
    )
    parser.add_argument(
        "--copilot-timeout",
        type=int,
        help="Override copilot response timeout in seconds (default: from config)",
    )

    args = parser.parse_args()

    # Setup
    import logging
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)
    log = logging.getLogger("main")

    # Resolve config path relative to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(script_dir, config_path)

    if not os.path.exists(config_path):
        log.error("Config file not found: %s", config_path)
        sys.exit(1)

    config = load_config(config_path)
    log.info("Loaded config: %s", config_path)

    # Apply CLI overrides
    if args.scenario:
        config["trouble"]["scenario"] = args.scenario
        log.info("Override scenario: %s", args.scenario)
    if args.scenario_port:
        config["trouble"]["port"] = args.scenario_port
        log.info("Override scenario port: %d", args.scenario_port)
    if args.copilot_timeout:
        config["browser"]["copilot"]["response_timeout"] = args.copilot_timeout
        log.info("Override copilot timeout: %ds", args.copilot_timeout)

    # Resolve output dir
    output_dir = args.output
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(script_dir, output_dir)

    # Create and configure orchestrator
    orch = Orchestrator(config, output_dir=output_dir)
    orch.skip_trouble = args.skip_trouble
    orch.skip_postprocess = args.skip_postprocess
    orch.dry_run = args.dry_run

    if args.force:
        original_preflight = orch.pre_flight_checks

        async def forced_preflight():
            await original_preflight()
            return True

        orch.pre_flight_checks = forced_preflight

    # Cleanup-only mode
    if args.cleanup_only:
        from agent.cleanup import SystemCleanup
        cleanup = SystemCleanup(config)
        log.info("=" * 60)
        log.info("Running cleanup-only mode...")
        log.info("=" * 60)
        asyncio.run(cleanup.full_cleanup(wait_minutes=10))
        log.info("=" * 60)
        log.info("Cleanup complete. System should be ready for recording.")
        log.info("=" * 60)
        sys.exit(0)

    # Run
    log.info("=" * 60)
    log.info("AIOps Demo Video Automation Agent")
    log.info("=" * 60)
    log.info("NOTE: K6 load generation must be started externally before running.")

    asyncio.run(orch.run())


if __name__ == "__main__":
    main()

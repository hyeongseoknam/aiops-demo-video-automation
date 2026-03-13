#!/usr/bin/env python3
"""Test runner for all 12 trouble scenarios.

Systematically tests each scenario with proper cleanup and wait times.
Generates individual videos for each scenario.
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agent.cleanup import SystemCleanup
from agent.orchestrator import Orchestrator
from agent.utils import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# All 12 trouble scenarios
SCENARIOS = [
    {"id": "01_cpu_spike", "port": 8081, "params": [], "name": "CPU Spike"},
    {"id": "02_memory_leak", "port": 8082, "params": [], "name": "Memory Leak"},
    {"id": "03_db_timeout", "port": 8083, "params": [], "name": "DB Timeout"},
    {"id": "04_slow_query", "port": 8083, "params": [], "name": "Slow Query"},
    {"id": "05_downstream_delay", "port": 8083, "params": ["5"], "name": "Downstream Delay 5s"},
    {"id": "06_downstream_error", "port": 8083, "params": [], "name": "Downstream Error"},
    {"id": "07_pool_exhaustion", "port": 8083, "params": [], "name": "Connection Pool Exhaustion"},
    {"id": "08_thread_deadlock", "port": 8083, "params": [], "name": "Thread Deadlock"},
    {"id": "09_network_delay", "port": 8083, "params": [], "name": "Network Delay"},
    {"id": "10_random_crash", "port": 8083, "params": [], "name": "Random Crash"},
    {"id": "11_mysql_dblock", "port": 3306, "params": [], "name": "MySQL DB Lock"},
    {"id": "12_mysql_column_error", "port": 3306, "params": [], "name": "MySQL Column Error"},
]


async def test_scenario(config: dict, scenario: dict, output_dir: str, wait_minutes: int = 10):
    """Test a single scenario."""
    log.info("=" * 80)
    log.info("TESTING SCENARIO: %s (%s)", scenario["name"], scenario["id"])
    log.info("=" * 80)

    # Update config for this scenario
    config["trouble"]["scenario"] = scenario["id"]
    config["trouble"]["port"] = scenario["port"]
    config["trouble"]["params"] = scenario["params"]

    # Create scenario-specific output directory
    scenario_output = os.path.join(output_dir, scenario["id"])
    os.makedirs(scenario_output, exist_ok=True)

    # Update output paths
    config["output"] = {
        "video_dir": scenario_output,
        "final_video": os.path.join(scenario_output, f"aiops_demo_{scenario['id']}.mp4"),
    }

    # Step 1: Full cleanup (stop all scenarios + wait)
    cleanup = SystemCleanup(config)
    log.info("Step 1/3: Running comprehensive cleanup...")
    await cleanup.full_cleanup(wait_minutes=wait_minutes)

    # Step 2: Run orchestrator for this scenario
    log.info("Step 2/3: Recording demo for scenario: %s", scenario["name"])
    orchestrator = Orchestrator(config)
    start_time = time.time()

    try:
        await orchestrator.run()
        elapsed = time.time() - start_time
        log.info("✓ Scenario %s completed in %.1f minutes", scenario["id"], elapsed / 60)
        return True
    except Exception as e:
        log.error("✗ Scenario %s failed: %s", scenario["id"], e)
        return False
    finally:
        # Step 3: Cleanup after this scenario
        log.info("Step 3/3: Cleaning up after scenario...")
        await cleanup.stop_all_scenarios()


async def test_all_scenarios(config_path: str, output_base: str, scenarios_to_test: list = None):
    """Test all scenarios sequentially."""
    config = load_config(config_path)

    # Create base output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(output_base, f"batch_test_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    # If no specific scenarios provided, test all
    if scenarios_to_test is None:
        scenarios_to_test = SCENARIOS
    else:
        # Filter by IDs
        scenarios_to_test = [s for s in SCENARIOS if s["id"] in scenarios_to_test]

    results = []
    total_start = time.time()

    log.info("=" * 80)
    log.info("BATCH TEST: Testing %d scenarios", len(scenarios_to_test))
    log.info("Output directory: %s", output_dir)
    log.info("=" * 80)

    for i, scenario in enumerate(scenarios_to_test, 1):
        log.info("\n[%d/%d] Testing: %s", i, len(scenarios_to_test), scenario["name"])

        success = await test_scenario(
            config.copy(),
            scenario,
            output_dir,
            wait_minutes=10  # Wait 10 minutes between scenarios
        )

        results.append({
            "scenario": scenario,
            "success": success,
        })

    # Summary
    total_elapsed = time.time() - total_start
    log.info("=" * 80)
    log.info("BATCH TEST COMPLETE")
    log.info("=" * 80)
    log.info("Total time: %.1f hours", total_elapsed / 3600)
    log.info("Results:")

    success_count = 0
    for result in results:
        status = "✓ PASS" if result["success"] else "✗ FAIL"
        log.info("  %s - %s (%s)", status, result["scenario"]["name"], result["scenario"]["id"])
        if result["success"]:
            success_count += 1

    log.info("")
    log.info("Summary: %d/%d scenarios passed", success_count, len(results))
    log.info("Output directory: %s", output_dir)
    log.info("=" * 80)

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test all 12 trouble scenarios")
    parser.add_argument(
        "--config",
        default="config/scenario.yaml",
        help="Path to config file",
    )
    parser.add_argument(
        "--output",
        default="output/batch_tests",
        help="Base output directory for test results",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        help="Specific scenario IDs to test (e.g., 01_cpu_spike 05_downstream_delay)",
    )
    args = parser.parse_args()

    asyncio.run(test_all_scenarios(args.config, args.output, args.scenarios))


if __name__ == "__main__":
    main()

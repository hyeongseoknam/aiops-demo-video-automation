"""Async scene orchestrator — coordinates all demo components.

K6 load generation is managed externally by the user.
This orchestrator handles: trouble injection → browser automation → trouble recovery.

Recording strategy: Playwright's built-in record_video captures page content
directly from the rendering engine. No x11grab / display server dependency.
"""

import asyncio
import logging
import os
import shutil
import time

from .browser_auto import BrowserAutomation
from .cleanup import SystemCleanup
from .post_processor import PostProcessor
from .terminal_renderer import render_terminal_video
from .trouble_runner import TroubleRunner
from .utils import Timer, resolve_font

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, config: dict, output_dir: str = "output"):
        self.config = config
        self.output_dir = output_dir
        self.temp_dir = os.path.join(output_dir, "temp")

        self.browser = BrowserAutomation(config)
        self.trouble = TroubleRunner(config)
        self.post = PostProcessor(config)
        self.cleanup = SystemCleanup(config)

        self.scene_markers: dict[str, float] = {}
        self.terminal_videos: dict[str, str] = {}
        self.recording_start_time: float = 0.0
        self.browser_video_path: str | None = None

        # Epoch timestamps for hitmap time range calculation
        self.epoch_timestamps: dict[str, int] = {}

        # Response analysis data (screenshots + text for post-processing)
        self.response_screenshots: list[str] = []
        self.response_text: str = ""

        self.skip_trouble = False
        self.skip_postprocess = False
        self.dry_run = False

    def _mark(self, scene_id: str, phase: str):
        """Record timestamp for scene start/end relative to recording start."""
        t = time.monotonic() - self.recording_start_time
        key = f"{scene_id}_{phase}"
        self.scene_markers[key] = t
        log.debug("Marker: %s = %.2fs", key, t)

    def _mark_epoch(self, event_name: str):
        """Record epoch timestamp (milliseconds) for hitmap time range."""
        epoch_ms = int(time.time() * 1000)
        self.epoch_timestamps[event_name] = epoch_ms
        log.debug("Epoch timestamp: %s = %d ms", event_name, epoch_ms)

    async def pre_flight_checks(self) -> bool:
        """Verify services and tools are available."""
        log.info("=" * 50)
        log.info("Pre-flight checks")
        log.info("=" * 50)
        checks_passed = True

        # Check trouble scripts
        tc = self.config["trouble"]
        base = tc["base_dir"]
        scenario = tc.get("scenario", "05_downstream_delay")
        ssh_host = tc.get("ssh_host")
        start_sh = os.path.join(base, scenario, "start.sh")
        stop_sh = os.path.join(base, scenario, "stop.sh")
        for p in [start_sh, stop_sh]:
            if ssh_host:
                proc = await asyncio.create_subprocess_exec(
                    "ssh", ssh_host, f"test -f {p} && echo OK",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if stdout and stdout.decode().strip() == "OK":
                    log.info("[OK] trouble script (remote): %s", p)
                else:
                    log.error("[FAIL] trouble script not found (remote): %s", p)
                    checks_passed = False
            else:
                if os.path.exists(p):
                    log.info("[OK] trouble script: %s", p)
                else:
                    log.error("[FAIL] trouble script not found: %s", p)
                    checks_passed = False

        # Check ffmpeg
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            log.info("[OK] ffmpeg available")
        else:
            log.error("[FAIL] ffmpeg not available")
            checks_passed = False

        # Check fonts (auto-resolve per OS)
        font = resolve_font(bold=True)
        if font and os.path.exists(font):
            log.info("[OK] Font available: %s", font)
        else:
            log.warning("[WARN] No CJK font found. Install Noto Sans CJK.")

        # Check target service
        bc = self.config["browser"]
        base_url = bc["base_url"]
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            "--connect-timeout", "5", base_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        code = stdout.decode().strip() if stdout else ""
        if code and code != "000":
            log.info("[OK] Web service reachable: %s (HTTP %s)", base_url, code)
        else:
            log.error("[FAIL] Web service unreachable: %s", base_url)
            checks_passed = False

        log.info("=" * 50)
        log.info("Pre-flight: %s", "PASSED" if checks_passed else "FAILED")
        log.info("=" * 50)
        return checks_passed

    async def run(self):
        """Execute the full demo recording pipeline."""
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        raw_recording = os.path.join(self.temp_dir, "raw_recording.webm")

        # Support scenario-specific output naming for batch processing
        scenario_id = self.config.get("trouble", {}).get("scenario", "default")
        final_output_name = self.config.get("output", {}).get("final_video")
        if final_output_name:
            final_output = final_output_name
        else:
            final_output = os.path.join(self.output_dir, f"aiops_demo_{scenario_id}.mp4")

        # Pre-flight
        passed = await self.pre_flight_checks()
        if self.dry_run:
            log.info("Dry run complete.")
            return
        if not passed:
            log.error("Pre-flight checks failed. Use --force to continue anyway.")
            return

        try:
            await self._execute_scenes()
        except Exception:
            log.exception("Error during scene execution")
        finally:
            await self._cleanup()

        # Copy browser video to expected location
        if self.browser_video_path and os.path.exists(self.browser_video_path):
            # Validate video duration before copying to detect truncation
            from .utils import get_video_duration

            source_duration = get_video_duration(self.browser_video_path)
            expected_duration = time.monotonic() - self.recording_start_time

            log.info(
                "Video validation: source=%.1fs, expected=%.1fs (diff=%.1fs)",
                source_duration,
                expected_duration,
                source_duration - expected_duration,
            )

            # Check for significant truncation (>5s missing)
            if source_duration < expected_duration - 5:
                log.error("=" * 60)
                log.error("WARNING: Video appears TRUNCATED!")
                log.error("  Source duration:   %.1fs", source_duration)
                log.error("  Expected duration: %.1fs", expected_duration)
                log.error("  Missing content:   %.1fs", expected_duration - source_duration)
                log.error("")
                log.error("This will cause scenes after %.1fs to have no content!", source_duration)

                # Find which scenes will be affected
                affected_scenes = []
                for key, timestamp in sorted(self.scene_markers.items()):
                    if timestamp > source_duration and "_start" in key:
                        scene_id = key.replace("_start", "")
                        affected_scenes.append(f"{scene_id} ({timestamp:.1f}s)")

                if affected_scenes:
                    log.error("  Affected scenes: %s", ", ".join(affected_scenes))

                log.error("=" * 60)

            shutil.copy2(self.browser_video_path, raw_recording)
            log.info("Browser recording copied: %s (%.1fs)", raw_recording, source_duration)

        # Post-processing
        if not self.skip_postprocess:
            # Process response analysis (screenshots + summary overlay)
            if self.response_screenshots and self.response_text:
                with Timer("Response analysis post-processing"):
                    log.info("Creating response slideshow with summary overlay...")

                    # Create slideshow from screenshots
                    slideshow_file = os.path.join(self.temp_dir, "response_slideshow.mp4")
                    if self.post.create_screenshot_slideshow(
                        screenshot_paths=self.response_screenshots,
                        output_file=slideshow_file,
                        duration_per_image=2.5,
                        crossfade_duration=0.5,
                    ):
                        # Extract key points for summary
                        key_points = self.post.extract_key_points(
                            response_text=self.response_text,
                            max_points=5
                        )

                        # Add summary overlay
                        if key_points:
                            slideshow_with_summary = os.path.join(
                                self.temp_dir, "response_with_summary.mp4"
                            )
                            if self.post.create_summary_overlay(
                                input_file=slideshow_file,
                                output_file=slideshow_with_summary,
                                key_points=key_points,
                                title="AI Analysis Summary",
                                position="bottom_right",
                            ):
                                # Add to terminal videos for inclusion in final video
                                self.terminal_videos["response_analysis"] = slideshow_with_summary
                                log.info("Response analysis video created with %d key points",
                                         len(key_points))
                            else:
                                # Fallback: use slideshow without overlay
                                self.terminal_videos["response_analysis"] = slideshow_file
                        else:
                            log.warning("No key points extracted, using slideshow without overlay")
                            self.terminal_videos["response_analysis"] = slideshow_file
                    else:
                        log.error("Failed to create response slideshow")

            with Timer("Post-processing"):
                self.post.process_scenes(
                    raw_recording=raw_recording,
                    terminal_videos=self.terminal_videos,
                    scene_markers=self.scene_markers,
                    temp_dir=self.temp_dir,
                    output_file=final_output,
                )
            if os.path.exists(final_output):
                from .utils import get_video_duration
                dur = get_video_duration(final_output)
                size = os.path.getsize(final_output) / (1024 * 1024)
                log.info("=" * 50)
                log.info("Demo video complete!")
                log.info("Output: %s", final_output)
                log.info("Duration: %.1fs (%.1f min)", dur, dur / 60)
                log.info("Size: %.1f MB", size)
                log.info("=" * 50)

    async def _run_scene(self, scene_id: str, coro):
        """Run a single scene with error handling.

        On failure: takes a screenshot for debugging, logs the error,
        and continues to the next scene instead of aborting.
        """
        try:
            self._mark(scene_id, "start")
            await coro
            self._mark(scene_id, "end")
        except Exception as e:
            log.error("Scene %s failed: %s", scene_id, e)
            await self.browser.screenshot(f"error_{scene_id}")
            # Still mark end so post-processor can handle partial recordings
            self._mark(scene_id, "end")

    async def _execute_scenes(self):
        """Execute all scenes in order.

        NEW Flow (show normal state first):
          1. Stop all troubles (ensure clean state)
          2. Browser: login → normal dashboard (blue lines)
          3. Trouble start → inject chaos (synthetic terminal video)
          4. Browser: dashboard again (trouble impact - red/orange)
          5. Browser: copilot → query → response
          6. Trouble stop → recover (synthetic terminal video)
        """

        # PRE-SCENE: Comprehensive cleanup - stop ALL scenarios + wait for stabilization
        if not self.skip_trouble:
            log.info("PRE-FLIGHT: Running comprehensive cleanup...")
            await self.cleanup.full_cleanup(wait_minutes=10)

        # Browser scenes with Playwright video recording
        video_dir = os.path.join(self.temp_dir, "pw_video")
        screenshot_dir = os.path.join(self.temp_dir, "screenshots")

        # Start browser and keep it open throughout
        await self.browser.launch(
            video_dir=video_dir,
            screenshot_dir=screenshot_dir,
        )
        self.recording_start_time = time.monotonic()
        await asyncio.sleep(1)

        with Timer("Browser recording (full session)"):
            # Scene 1: Login
            with Timer("Scene: login"):
                log.info("Scene 1: Logging in")
                await self._run_scene("login", self.browser.login())

            # Scene 2: Normal Dashboard (BEFORE trouble)
            with Timer("Scene: normal_dashboard"):
                log.info("Scene 2: Normal dashboard - showing baseline (blue lines)")
                await self._run_scene("normal_dashboard", self.browser.goto_apm_dashboard())

            # NOW inject chaos while browser waits
            if not self.skip_trouble:
                # Scene 3: Trouble start (synthetic terminal) - inject during wait
                with Timer("Scene: trouble_start"):
                    log.info("Scene 3: Injecting trouble scenario (browser waiting)...")
                    # Mark scene for synthetic video
                    self._mark("trouble_start", "start")

                    success, output = await self.trouble.start()
                    # Track epoch timestamp for hitmap start time
                    self._mark_epoch("trouble_injected")

                    trouble_video = os.path.join(self.temp_dir, "trouble_start.mp4")
                    scenario = self.config["trouble"]["scenario"]
                    port = self.config["trouble"]["port"]
                    params = " ".join(self.config["trouble"].get("params", []))
                    render_terminal_video(
                        command=f"./start.sh {port} {params}",
                        output_text=output or self.trouble.get_output_text(),
                        output_path=trouble_video,
                        title=f"Chaos: {scenario}",
                        hold_secs=2.0,
                    )
                    self.terminal_videos["trouble_start"] = trouble_video
                    self._mark("trouble_start", "end")

                log.info("Waiting for trouble to propagate and show on dashboard (20s)...")
                await asyncio.sleep(20)

            # Scene 4: Dashboard with Trouble Impact (refresh/navigate again)
            with Timer("Scene: trouble_dashboard"):
                log.info("Scene 4: Dashboard - showing trouble impact (red/orange spikes)")
                await self._run_scene("trouble_dashboard", self.browser.goto_apm_dashboard())

            # Scene 5: Navigate to Copilot
            with Timer("Scene: navigate_copilot"):
                log.info("Scene 5: Navigating to Copilot")
                await self._run_scene("navigate_copilot", self.browser.navigate_copilot())

            # Scene 6: New Chat
            with Timer("Scene: new_chat"):
                log.info("Scene 6: Starting new chat")
                await self._run_scene("new_chat", self.browser.start_new_chat())

            # Scene 7: Type Query
            with Timer("Scene: type_query"):
                log.info("Scene 7: Typing query")
                await self._run_scene("type_query", self.browser.type_query())

            # Scene 8: Wait for Response
            with Timer("Scene: wait_response"):
                log.info("Scene 8: Waiting for AI response")
                await self._run_scene("wait_response", self.browser.wait_for_response())

            # Capture response analysis data (screenshots + text for summary overlay)
            if not self.skip_postprocess:
                with Timer("Capture response analysis"):
                    log.info("Capturing response screenshots and text for summary overlay...")
                    self.response_text = await self.browser.extract_response_text()
                    self.response_screenshots = await self.browser.capture_response_screenshots(
                        num_screenshots=4,
                        screenshot_dir=screenshot_dir
                    )
                    log.info("Captured %d screenshots and %d chars of text",
                             len(self.response_screenshots), len(self.response_text))

            # Scene 9: Show Result (hold for 5 seconds)
            with Timer("Scene: show_result"):
                log.info("Scene 9: Showing result (5s hold)")
                self._mark("show_result", "start")
                await asyncio.sleep(5)
                self._mark("show_result", "end")
                # Track epoch timestamp for hitmap end time
                self._mark_epoch("analysis_complete")

            # NEW: Hitmap verification workflow
            if not self.skip_trouble and "trouble_injected" in self.epoch_timestamps:
                # Calculate time range for hitmap
                stime_ms = self.epoch_timestamps.get("trouble_injected", 0)
                etime_ms = self.epoch_timestamps.get("analysis_complete", 0)

                if stime_ms and etime_ms:
                    # Scene 10: Navigate to Hitmap
                    with Timer("Scene: navigate_hitmap"):
                        log.info("Scene 10: Navigating to hitmap for validation")
                        await self._run_scene(
                            "navigate_hitmap",
                            self.browser.navigate_hitmap(stime_ms, etime_ms)
                        )

                    # Scene 11: Execute Hitmap Search
                    with Timer("Scene: hitmap_search"):
                        log.info("Scene 11: Executing hitmap search")
                        await self._run_scene(
                            "hitmap_search",
                            self.browser.execute_hitmap_search()
                        )

                    # Scene 12: Select Transactions
                    with Timer("Scene: select_transactions"):
                        log.info("Scene 12: Selecting high-response-time transactions")
                        await self._run_scene(
                            "select_transactions",
                            self.browser.select_hitmap_transactions()
                        )

                    # Scene 13: Show Transactions (validation complete)
                    with Timer("Scene: show_transactions"):
                        log.info("Scene 13: Showing transactions (validation)")
                        self._mark("show_transactions", "start")
                        await self.browser.show_hitmap_transactions(hold_seconds=8)
                        self._mark("show_transactions", "end")
                else:
                    log.warning("Skipping hitmap workflow - missing timestamps")

            # Close browser and get video path
            self.browser_video_path = await self.browser.close()

            # CRITICAL FIX: Wait for Playwright to finalize video encoding
            # Race condition: browser.close() returns path before encoding completes
            # This causes truncated video when copied immediately
            if self.browser_video_path and os.path.exists(self.browser_video_path):
                log.info("Waiting for video encoding to finalize...")
                await asyncio.sleep(3)  # Initial 3-second delay

                # Verify file is stable (size not changing)
                initial_size = os.path.getsize(self.browser_video_path)
                await asyncio.sleep(2)
                final_size = os.path.getsize(self.browser_video_path)

                if initial_size != final_size:
                    log.warning(
                        "Video file still growing (%d -> %d bytes), waiting additional 5s...",
                        initial_size,
                        final_size,
                    )
                    await asyncio.sleep(5)
                    log.info("Video encoding finalization complete")
                else:
                    log.info("Video encoding stable (%d bytes)", final_size)

        # Scene 14: Trouble stop (synthetic terminal)
        if not self.skip_trouble:
            with Timer("Scene: trouble_stop"):
                log.info("Scene 14: Stopping trouble scenario")
                success, output = await self.trouble.stop()

                trouble_stop_video = os.path.join(self.temp_dir, "trouble_stop.mp4")
                scenario = self.config["trouble"]["scenario"]
                port = self.config["trouble"]["port"]
                render_terminal_video(
                    command=f"./stop.sh {port}",
                    output_text=output or "Trouble scenario stopped successfully.",
                    output_path=trouble_stop_video,
                    title=f"Chaos: {scenario} (Recovery)",
                    hold_secs=2.0,
                )
                self.terminal_videos["trouble_stop"] = trouble_stop_video

    async def _cleanup(self):
        """Ensure all subprocesses are stopped."""
        log.info("Cleaning up...")
        try:
            if self.browser.page:
                video_path = await self.browser.close()
                if video_path and not self.browser_video_path:
                    self.browser_video_path = video_path
        except Exception:
            log.debug("Browser close error (may already be closed)")

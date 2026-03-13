"""Playwright browser automation for AIOps demo.

Uses Playwright's built-in video recording (record_video) instead of
x11grab, which doesn't work on Wayland+XWayland.
"""

import asyncio
import logging
import os

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

log = logging.getLogger(__name__)


class BrowserAutomation:
    def __init__(self, config: dict):
        self.config = config  # Store full config for access to all sections
        bc = config["browser"]
        self.base_url = bc["base_url"]
        self.zoom_level = bc.get("zoom_level", 1.0)
        self.login_cfg = bc["login"]
        self.dashboard_cfg = bc["apm_dashboard"]
        self.copilot_cfg = bc["copilot"]
        self.query = bc["query"]
        self.typing_delay = bc.get("typing_delay_ms", 100)
        self.copilot_timeout = self.copilot_cfg.get("response_timeout", 120)
        self.copilot_stability = self.copilot_cfg.get("stability_threshold", 5.0)
        self.copilot_min_wait = self.copilot_cfg.get("minimum_wait_time", 15.0)

        rec = config.get("recording", {})
        self.width = rec.get("width", 1920)
        self.height = rec.get("height", 1080)

        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self._video_dir: str | None = None
        self._screenshot_dir: str | None = None

    async def launch(self, video_dir: str, screenshot_dir: str | None = None):
        """Launch browser with built-in video recording.

        Playwright's record_video captures page content directly from the
        rendering engine — works on any display server (Wayland, X11, headless).
        """
        self._video_dir = video_dir
        self._screenshot_dir = screenshot_dir or video_dir
        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(self._screenshot_dir, exist_ok=True)

        log.info("Launching Chromium with video recording (%dx%d)", self.width, self.height)
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=False,
            args=[
                "--disable-infobars",
                "--disable-extensions",
                "--no-first-run",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": self.width, "height": self.height},
            record_video_dir=video_dir,
            record_video_size={"width": self.width, "height": self.height},
        )
        self.page = await self._context.new_page()

        # Apply zoom level to fit more content on screen
        if self.zoom_level != 1.0:
            await self.page.evaluate(f"document.body.style.zoom = '{self.zoom_level}'")
            log.info("Browser zoom set to %.0f%%", self.zoom_level * 100)

        await asyncio.sleep(1)

    async def screenshot(self, name: str) -> str | None:
        """Take a screenshot for debugging. Returns path or None."""
        if not self.page or not self._screenshot_dir:
            return None
        path = os.path.join(self._screenshot_dir, f"{name}.png")
        try:
            await self.page.screenshot(path=path)
            log.info("Screenshot saved: %s", path)
            return path
        except Exception as e:
            log.warning("Screenshot failed: %s", e)
            return None

    async def login(self):
        url = self.base_url + self.login_cfg["url"]
        log.info("Logging in at %s", url)
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)

        email_el = self.page.locator(f"xpath={self.login_cfg['email_selector']}")
        await email_el.click()
        await email_el.fill("")
        await email_el.type(self.login_cfg["email"], delay=50)

        password_el = self.page.locator(f"xpath={self.login_cfg['password_selector']}")
        await password_el.click()
        await password_el.fill("")
        await password_el.type(self.login_cfg["password"], delay=50)

        await self.page.keyboard.press("Enter")
        await self.page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)
        log.info("Login complete")

    async def goto_apm_dashboard(self):
        url = self.base_url + self.dashboard_cfg["url"]
        log.info("Navigating to APM dashboard: %s", url)
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        wait_sec = self.dashboard_cfg.get("wait_sec", 8)
        log.info("Observing dashboard for %ds", wait_sec)
        await asyncio.sleep(wait_sec)

    async def navigate_copilot(self):
        url = self.base_url + self.copilot_cfg["url"]
        log.info("Navigating to Copilot: %s", url)
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        log.info("Copilot page loaded")

    async def start_new_chat(self):
        """Start a new chat with fallback selector strategies."""
        log.info("Starting new chat")

        # Strategy 1: configured XPath
        xpath = self.copilot_cfg["new_chat_xpath"]
        btn = self.page.locator(f"xpath={xpath}")
        try:
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()
            await asyncio.sleep(1)
            log.info("New chat started (xpath)")
            return
        except Exception:
            log.debug("XPath selector failed, trying fallbacks")

        # Strategy 2: button containing "new" or "새" text
        for text_pattern in ["New", "new chat", "New Chat", "새 대화", "새 채팅"]:
            try:
                fallback = self.page.get_by_role("button", name=text_pattern)
                if await fallback.count() > 0:
                    await fallback.first.click()
                    await asyncio.sleep(1)
                    log.info("New chat started (button text: %s)", text_pattern)
                    return
            except Exception:
                continue

        # Strategy 3: first button with a "+" or pencil icon in the header area
        try:
            header_btns = self.page.locator("button").filter(has=self.page.locator("svg, span"))
            count = await header_btns.count()
            if count > 0:
                await header_btns.first.click()
                await asyncio.sleep(1)
                log.info("New chat started (first header button)")
                return
        except Exception:
            pass

        # Strategy 4: if already on a fresh chat page, just skip
        log.warning("Could not find new chat button — assuming already on fresh chat")
        await self.screenshot("new_chat_fallback")

    async def type_query(self, text: str | None = None):
        """Type query with fallback selector strategies."""
        query = text or self.query
        log.info("Typing query: %s", query)

        # Strategy 1: configured XPath
        xpath = self.copilot_cfg["textarea_xpath"]
        textarea = self.page.locator(f"xpath={xpath}")
        try:
            await textarea.wait_for(state="visible", timeout=5000)
            await textarea.click()
            await textarea.type(query, delay=self.typing_delay)
            await asyncio.sleep(0.5)
            await self.page.keyboard.press("Enter")
            log.info("Query submitted (xpath)")
            return
        except Exception:
            log.debug("XPath textarea failed, trying fallbacks")

        # Strategy 2: any visible textarea or input[type=text] on the page
        for selector in ["textarea", "form textarea", "input[type='text']", "[contenteditable='true']"]:
            try:
                el = self.page.locator(selector).last
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    await el.type(query, delay=self.typing_delay)
                    await asyncio.sleep(0.5)
                    await self.page.keyboard.press("Enter")
                    log.info("Query submitted (fallback: %s)", selector)
                    return
            except Exception:
                continue

        # Strategy 3: get_by_role
        try:
            el = self.page.get_by_role("textbox").last
            await el.click()
            await el.type(query, delay=self.typing_delay)
            await asyncio.sleep(0.5)
            await self.page.keyboard.press("Enter")
            log.info("Query submitted (role textbox)")
            return
        except Exception:
            pass

        log.error("Could not find text input for query")
        await self.screenshot("type_query_failed")

    async def wait_for_response(self, timeout: int | None = None, stable_secs: float | None = None):
        """Wait for SSE streaming response to complete by polling DOM content.

        Two-phase strategy:
        1. Phase 1: Wait minimum_wait_time before checking stability (AI needs time to start)
        2. Phase 2: Monitor for content stability (no changes for stable_secs)

        This prevents premature detection when AI is still generating response.
        """
        timeout = timeout or self.copilot_timeout
        stable_secs = stable_secs or self.copilot_stability
        min_wait = self.copilot_min_wait

        log.info(
            "Waiting for AI response (timeout=%ds, min_wait=%.1fs, stable=%.1fs)",
            timeout, min_wait, stable_secs
        )

        poll_interval = 0.5
        elapsed = 0.0
        last_text = ""
        stable_time = 0.0
        content_length = 0

        # Phase 1: Minimum wait - don't check stability yet, just let AI start responding
        log.info("Phase 1: Minimum wait (%.1fs) - allowing AI time to generate response", min_wait)
        while elapsed < min_wait and elapsed < timeout:
            try:
                content = await self.page.evaluate("""
                    () => {
                        const msgs = document.querySelectorAll(
                            '[class*="message"], [class*="chat"], [class*="response"], ' +
                            '[class*="answer"], [class*="markdown"], [class*="content"]'
                        );
                        return Array.from(msgs).map(el => el.textContent).join('\\n');
                    }
                """)
                content_length = len(content)

                # Log progress every 5 seconds during minimum wait
                if int(elapsed) % 5 == 0 and elapsed > 0:
                    log.debug("  Min wait: %.1fs elapsed, content length: %d chars", elapsed, content_length)
            except Exception:
                content = ""

            last_text = content
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        log.info("Phase 1 complete. Content length: %d chars", content_length)
        log.info("Phase 2: Monitoring for stability (%.1fs of no changes)", stable_secs)

        # Phase 2: Monitor for stability - response is complete when content stops changing
        while elapsed < timeout:
            try:
                content = await self.page.evaluate("""
                    () => {
                        const msgs = document.querySelectorAll(
                            '[class*="message"], [class*="chat"], [class*="response"], ' +
                            '[class*="answer"], [class*="markdown"], [class*="content"]'
                        );
                        return Array.from(msgs).map(el => el.textContent).join('\\n');
                    }
                """)
            except Exception:
                content = ""

            # Check if content is stable (not changing)
            if content and content == last_text and len(content) > len(self.query):
                stable_time += poll_interval

                # Log stability progress every 2 seconds
                if int(stable_time * 2) % 2 == 0 and stable_time > 0:
                    log.debug("  Stability: %.1fs/%.1fs, content: %d chars", stable_time, stable_secs, len(content))

                if stable_time >= stable_secs:
                    log.info("✓ Response stable for %.1fs - considering complete", stable_secs)
                    log.info("Final content length: %d chars", len(content))
                    return True
            else:
                # Content changed - reset stability timer
                if stable_time > 0:
                    log.debug("  Content changed (was stable for %.1fs), resetting timer", stable_time)
                stable_time = 0.0

            last_text = content
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        log.warning("Response wait timed out after %.1fs", elapsed)
        log.warning("Last content length: %d chars", len(last_text))
        return False

    async def extract_response_text(self) -> str:
        """Extract full text content from AI response for analysis.

        Returns:
            Full text content from the response area
        """
        try:
            content = await self.page.evaluate("""
                () => {
                    const msgs = document.querySelectorAll(
                        '[class*="message"], [class*="chat"], [class*="response"], ' +
                        '[class*="answer"], [class*="markdown"], [class*="content"]'
                    );
                    return Array.from(msgs).map(el => el.textContent).join('\\n');
                }
            """)
            log.info("Extracted response text: %d characters", len(content))
            return content
        except Exception as e:
            log.warning("Failed to extract response text: %s", e)
            return ""

    async def capture_response_screenshots(
        self,
        num_screenshots: int = 4,
        screenshot_dir: str = None,
    ) -> list[str]:
        """Scroll through response and capture screenshots at different positions.

        Args:
            num_screenshots: Number of screenshots to capture (default: 4)
            screenshot_dir: Directory to save screenshots (default: self._screenshot_dir)

        Returns:
            List of screenshot file paths
        """
        import os

        if not screenshot_dir:
            screenshot_dir = self._screenshot_dir

        screenshots = []

        try:
            # Get scroll height and viewport dimensions
            scroll_data = await self.page.evaluate("""
                () => {
                    // Find scrollable container (response area)
                    const container = document.querySelector('[class*="response"]')
                        || document.querySelector('[class*="chat"]')
                        || document.querySelector('[class*="message"]')
                        || document.body;

                    const scrollHeight = container.scrollHeight;
                    const clientHeight = container.clientHeight;
                    const viewportHeight = window.innerHeight;

                    return {
                        scrollHeight: scrollHeight,
                        clientHeight: clientHeight,
                        viewportHeight: viewportHeight
                    };
                }
            """)

            scroll_height = scroll_data.get("scrollHeight", 0)
            viewport_height = scroll_data.get("viewportHeight", 0)

            # Calculate maximum scrollable distance
            max_scroll = max(0, scroll_height - viewport_height)

            if max_scroll == 0:
                # Content fits in one screen, just capture one screenshot
                log.info("Response fits in viewport, capturing single screenshot")
                num_screenshots = 1
            else:
                log.info(
                    "Response scroll height: %dpx, viewport: %dpx, max_scroll: %dpx",
                    scroll_height,
                    viewport_height,
                    max_scroll,
                )

            # Capture screenshots at different scroll positions
            for i in range(num_screenshots):
                # Calculate scroll position
                if num_screenshots == 1:
                    scroll_pos = 0
                else:
                    # Distribute scroll positions evenly
                    scroll_pos = int((max_scroll / (num_screenshots - 1)) * i)

                # Scroll to position
                await self.page.evaluate(
                    f"""
                    () => {{
                        const container = document.querySelector('[class*="response"]')
                            || document.querySelector('[class*="chat"]')
                            || document.querySelector('[class*="message"]')
                            || window;

                        if (container.scrollTo) {{
                            container.scrollTo(0, {scroll_pos});
                        }} else {{
                            window.scrollTo(0, {scroll_pos});
                        }}
                    }}
                """
                )

                # Wait for scroll to settle
                await asyncio.sleep(1.5)

                # Capture screenshot
                path = os.path.join(screenshot_dir, f"response_scroll_{i:02d}.png")
                await self.page.screenshot(path=path)
                screenshots.append(path)
                log.info(
                    "Captured response screenshot %d/%d at scroll=%dpx",
                    i + 1,
                    num_screenshots,
                    scroll_pos,
                )

            # Scroll back to top
            await self.page.evaluate("() => window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)

            return screenshots

        except Exception as e:
            log.error("Failed to capture response screenshots: %s", e)
            return []

    async def get_video_path(self) -> str | None:
        """Get path to the recorded video. Must be called before close()."""
        if self.page and self.page.video:
            try:
                return await self.page.video.path()
            except Exception:
                return None
        return None

    async def navigate_hitmap(self, stime_ms: int, etime_ms: int):
        """Navigate to hitmap with calculated time range.

        Args:
            stime_ms: Start time in epoch milliseconds
            etime_ms: End time in epoch milliseconds
        """
        url = f"{self.base_url}/v2/project/apm/1/daily_hitmap?etime={etime_ms}&stime={stime_ms}&type=oid"
        log.info("Navigating to hitmap: stime=%d, etime=%d", stime_ms, etime_ms)
        log.info("Time range: %.1f minutes", (etime_ms - stime_ms) / 1000 / 60)

        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        log.info("Hitmap page loaded")

    async def execute_hitmap_search(self):
        """Click search button using configured selector with fallbacks."""
        log.info("Executing hitmap search")

        # Get hitmap configuration
        hitmap_cfg = self.config["browser"].get("hitmap", {})
        selector = hitmap_cfg.get("search_button_selector")
        selector_type = hitmap_cfg.get("selector_type", "css")
        fallback_text = hitmap_cfg.get("fallback_text", ["조회", "Search"])

        # Strategy 1: Configured CSS/XPath selector (most specific)
        if selector:
            try:
                if selector_type == "css":
                    search_btn = self.page.locator(selector)
                elif selector_type == "xpath":
                    search_btn = self.page.locator(f"xpath={selector}")
                else:
                    search_btn = self.page.locator(selector)

                await search_btn.wait_for(state="visible", timeout=5000)
                await search_btn.click()
                log.info("Search button clicked (%s selector)", selector_type)
                await asyncio.sleep(3)  # Wait for hitmap to render
                return
            except Exception as e:
                log.debug("Configured selector failed: %s, trying fallbacks", e)

        # Strategy 2-N: Fallback text-based selectors
        for text in fallback_text:
            try:
                search_btn = self.page.get_by_role("button", name=text)
                if await search_btn.count() > 0:
                    await search_btn.click()
                    log.info("Search button clicked (fallback: %s)", text)
                    await asyncio.sleep(3)
                    return
            except Exception:
                continue

        # Last resort: First button on page
        try:
            buttons = self.page.locator("button")
            count = await buttons.count()
            if count > 0:
                await buttons.first.click()
                log.info("Search button clicked (first button)")
                await asyncio.sleep(3)
                return
        except Exception:
            pass

        log.warning("Could not find search button - hitmap may auto-load")
        await self.screenshot("hitmap_search_fallback")
        await asyncio.sleep(3)

    async def select_hitmap_transactions(self):
        """Drag to select high-response-time area and show transactions.

        Uses heuristic approach: drag in the middle-right area of the hitmap
        where high response times typically cluster (red/orange colors).
        """
        log.info("Selecting hitmap transaction area")

        try:
            # Get hitmap container dimensions
            hitmap_container = self.page.locator("canvas, svg, [class*='hitmap'], [class*='chart']").first
            await hitmap_container.wait_for(state="visible", timeout=5000)

            box = await hitmap_container.bounding_box()
            if not box:
                log.warning("Could not get hitmap bounding box")
                await self.screenshot("hitmap_no_box")
                return

            # Calculate drag coordinates (middle-right area, upper portion)
            # Assume high response times are in the upper-right quadrant
            start_x = box["x"] + (box["width"] * 0.6)  # 60% from left
            start_y = box["y"] + (box["height"] * 0.2)  # 20% from top
            end_x = box["x"] + (box["width"] * 0.9)    # 90% from left
            end_y = box["y"] + (box["height"] * 0.5)    # 50% from top

            log.info("Dragging hitmap area: (%.0f, %.0f) → (%.0f, %.0f)",
                     start_x, start_y, end_x, end_y)

            # Perform drag selection
            await self.page.mouse.move(start_x, start_y)
            await self.page.mouse.down()
            await asyncio.sleep(0.5)
            await self.page.mouse.move(end_x, end_y)
            await asyncio.sleep(0.5)
            await self.page.mouse.up()

            log.info("Hitmap area selected")
            await asyncio.sleep(2)  # Wait for transaction list to appear

        except Exception as e:
            log.error("Failed to select hitmap transactions: %s", e)
            await self.screenshot("hitmap_select_failed")

    async def show_hitmap_transactions(self, hold_seconds: int = 8):
        """Display selected transactions for verification.

        Args:
            hold_seconds: How long to show the transaction list
        """
        log.info("Showing hitmap transactions for %ds", hold_seconds)

        # Take screenshot for validation
        await self.screenshot("hitmap_transactions")

        # Hold to show transactions
        await asyncio.sleep(hold_seconds)
        log.info("Hitmap transaction display complete")

    async def close(self) -> str | None:
        """Close browser and finalize video recording. Returns video path."""
        video_path = None
        if self.page and self.page.video:
            try:
                video_path = await self.page.video.path()
            except Exception:
                pass

        if self._context:
            log.info("Closing browser context (finalizing video)...")
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

        self._context = None
        self._browser = None
        self._pw = None
        self.page = None

        if video_path:
            log.info("Browser video saved: %s", video_path)
        return video_path

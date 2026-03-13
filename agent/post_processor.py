"""FFmpeg post-processing pipeline: captions, speed changes, intro/outro, concat.

Note: Uses Pillow to generate PNG text overlays + FFmpeg overlay filter
      as a workaround for missing drawtext filter (requires libfreetype).
"""

import logging
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import tempfile

from .utils import escape_ffmpeg_text, escape_ffmpeg_fontpath, resolve_font_for_config, run_ffmpeg_sync, get_video_duration

log = logging.getLogger(__name__)


class PostProcessor:
    def __init__(self, config: dict):
        pp = config.get("post_process", {})
        self.width = pp.get("output_width", 1920)
        self.height = pp.get("output_height", 1080)
        self.fps = pp.get("fps", 30)
        self.crf = pp.get("crf", 22)
        self.font_bold = resolve_font_for_config(pp.get("font_bold"))
        self.font_regular = resolve_font_for_config(pp.get("font_regular"))
        self.intro_cfg = pp.get("intro", {})
        self.outro_cfg = pp.get("outro", {})
        self.scenes = config.get("scenes", [])

    def _base_encode_args(self) -> list[str]:
        return [
            "-c:v", "libx264", "-preset", "fast", "-crf", str(self.crf),
            "-r", str(self.fps), "-pix_fmt", "yuv420p",
        ]

    def extract_key_points(self, response_text: str, max_points: int = 5) -> list[str]:
        """Extract key bullet points from LLM response text.

        Strategy:
        1. Find explicit bullet points (-, *, •, numbered lists)
        2. Find section headers (lines ending with :)
        3. Fallback: First sentence of each paragraph

        Args:
            response_text: Full AI response text
            max_points: Maximum number of points to extract

        Returns:
            List of key point strings (up to max_points)
        """
        import re

        points = []
        if not response_text:
            return points

        lines = response_text.split('\n')

        # Strategy 1: Bullet points and numbered lists
        for line in lines:
            line = line.strip()
            # Match bullet points: "- text", "* text", "• text"
            if re.match(r'^[-*•]\s+', line):
                clean = line.lstrip('-*• ').strip()
                if clean and len(clean) > 10:  # Ignore very short lines
                    points.append(clean)
            # Match numbered lists: "1. text", "2. text"
            elif re.match(r'^\d+\.\s+', line):
                clean = re.sub(r'^\d+\.\s+', '', line).strip()
                if clean and len(clean) > 10:
                    points.append(clean)

        # Strategy 2: Section headers (if not enough points yet)
        if len(points) < max_points:
            for line in lines:
                line = line.strip()
                if line.endswith(':') and 10 < len(line) < 100:
                    # Remove trailing colon, add as point
                    header = line.rstrip(':')
                    if header and header not in points:
                        points.append(header)

        # Strategy 3: First sentence of paragraphs (last resort)
        if len(points) < max_points:
            paragraphs = [p.strip() for p in response_text.split('\n\n') if p.strip()]
            for para in paragraphs:
                if len(points) >= max_points:
                    break
                # Get first sentence
                sentences = re.split(r'[.!?]\s+', para)
                if sentences and len(sentences[0]) > 20:
                    first_sentence = sentences[0] + '.'
                    if first_sentence not in points:
                        points.append(first_sentence)

        # Limit and truncate long points
        final_points = []
        for point in points[:max_points]:
            if len(point) > 120:
                # Truncate long points
                point = point[:117] + '...'
            final_points.append(point)

        log.info("Extracted %d key points from response (%d chars)",
                 len(final_points), len(response_text))
        return final_points

    def _generate_text_overlay_png(
        self,
        text_blocks: list[dict],
        bg_color=None,
        output_path=None
    ) -> str:
        """Generate a PNG overlay with text using Pillow.

        Args:
            text_blocks: List of dicts with keys: text, font_path, font_size, color, x, y
            bg_color: Background color (None for transparent, or "#RRGGBB" or (R,G,B,A))
            output_path: Output path (None = temp file)

        Returns:
            Path to generated PNG file
        """
        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)

        # Create image with transparency or solid background
        if bg_color is None:
            img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        elif isinstance(bg_color, str):
            # Convert hex "#1a1a2e" to RGB
            bg_color = bg_color.replace("#", "")
            r, g, b = int(bg_color[0:2], 16), int(bg_color[2:4], 16), int(bg_color[4:6], 16)
            img = Image.new("RGB", (self.width, self.height), (r, g, b))
        else:
            img = Image.new("RGBA", (self.width, self.height), bg_color)

        draw = ImageDraw.Draw(img)

        for block in text_blocks:
            text = block["text"]
            font_path = block.get("font_path", self.font_regular)
            font_size = block.get("font_size", 30)
            color = block.get("color", "white")
            x = block.get("x", 0)
            y = block.get("y", 0)
            align = block.get("align", "left")  # "left", "center", "right"

            # Load font
            try:
                font = ImageFont.truetype(font_path, font_size)
            except Exception:
                log.warning("Could not load font %s, using default", font_path)
                font = ImageFont.load_default()

            # Convert color to RGB/RGBA tuple if it's a string
            if isinstance(color, str):
                if color.startswith("0x"):
                    # Convert "0xABCDEF" to RGB
                    color_hex = color[2:]
                    if len(color_hex) == 6:
                        r = int(color_hex[0:2], 16)
                        g = int(color_hex[2:4], 16)
                        b = int(color_hex[4:6], 16)
                        color = (r, g, b)
                    elif len(color_hex) == 8:  # RGBA
                        r = int(color_hex[0:2], 16)
                        g = int(color_hex[2:4], 16)
                        b = int(color_hex[4:6], 16)
                        a = int(color_hex[6:8], 16)
                        color = (r, g, b, a)

            # Calculate text position for centering
            if align == "center":
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                x = (self.width - text_width) // 2
            elif align == "right":
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                x = self.width - text_width - x  # x becomes right margin

            draw.text((x, y), text, font=font, fill=color)

        img.save(output_path, "PNG")
        return output_path

    def create_intro(self, output_file: str) -> bool:
        """Create intro using Pillow PNG overlay (workaround for missing drawtext)."""
        cfg = self.intro_cfg
        duration = cfg.get("duration_sec", 4)
        bg = cfg.get("background_color", "#1a1a2e")
        t1 = cfg.get("text_primary", "AIOps Demo")
        t2 = cfg.get("text_secondary", "")

        # Generate text overlay PNG using Pillow
        text_blocks = [
            {
                "text": t1,
                "font_path": self.font_bold,
                "font_size": 80,
                "color": "white",
                "y": self.height // 2 - 50,
                "align": "center",
            },
            {
                "text": t2,
                "font_path": self.font_regular,
                "font_size": 48,
                "color": "#A0E8AF",
                "y": self.height // 2 + 50,
                "align": "center",
            },
        ]

        overlay_png = self._generate_text_overlay_png(text_blocks, bg_color=bg)

        try:
            # Convert PNG to video with fades
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", overlay_png,
                "-vf", f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration-0.5}:d=0.5",
                *self._base_encode_args(),
                "-t", str(duration),
                output_file,
            ]
            return run_ffmpeg_sync(cmd, "intro")
        finally:
            if os.path.exists(overlay_png):
                os.remove(overlay_png)

    def create_outro(self, output_file: str) -> bool:
        """Create outro using Pillow PNG overlay (workaround for missing drawtext)."""
        cfg = self.outro_cfg
        duration = cfg.get("duration_sec", 4)
        bg = cfg.get("background_color", "#1a1a2e")
        lines = cfg.get("lines", ["AIOps Demo"])

        positions = [
            (self.height // 2 - 100, 72, "white", self.font_bold),
            (self.height // 2 - 20, 44, "#CCCCCC", self.font_regular),
            (self.height // 2 + 40, 44, "#CCCCCC", self.font_regular),
            (self.height - 120, 36, "#888888", self.font_regular),
        ]

        text_blocks = []
        for i, line in enumerate(lines[:4]):
            y, size, color, font = positions[i]
            text_blocks.append({
                "text": line,
                "font_path": font,
                "font_size": size,
                "color": color,
                "y": y,
                "align": "center",
            })

        overlay_png = self._generate_text_overlay_png(text_blocks, bg_color=bg)

        try:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", overlay_png,
                "-vf", f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration-0.5}:d=0.5",
                *self._base_encode_args(),
                "-t", str(duration),
                output_file,
            ]
            return run_ffmpeg_sync(cmd, "outro")
        finally:
            if os.path.exists(overlay_png):
                os.remove(overlay_png)

    def add_caption_bar(
        self, input_file: str, output_file: str, caption: str, speed: float = 1.0
    ) -> bool:
        """Add bottom caption bar overlay using Pillow PNG + FFmpeg overlay filter."""
        bar_h = 60
        bar_y = self.height - bar_h

        # Create semi-transparent blue bar with caption text
        text_blocks = [{
            "text": caption,
            "font_path": self.font_bold,
            "font_size": 30,
            "color": "white",
            "y": bar_y + 15,
            "align": "center",
        }]

        if speed != 1.0:
            text_blocks.append({
                "text": f"x{speed:.1f}",
                "font_path": self.font_bold,
                "font_size": 28,
                "color": "#FFD700",
                "x": 100,  # right margin
                "y": bar_y + 16,
                "align": "right",
            })

        # Generate overlay with semi-transparent blue background bar
        overlay_png = self._generate_text_overlay_png(text_blocks, bg_color=None)

        # Add blue bar background to the PNG
        try:
            img = Image.open(overlay_png).convert("RGBA")
            draw = ImageDraw.Draw(img)
            # Semi-transparent blue bar
            draw.rectangle([(0, bar_y), (self.width, self.height)], fill=(21, 101, 192, 217))  # 0.85 alpha * 255 ≈ 217

            # Redraw text on top of bar
            for block in text_blocks:
                text = block["text"]
                font_path = block.get("font_path", self.font_regular)
                font_size = block.get("font_size", 30)
                color = block.get("color", "white")
                y = block.get("y", 0)
                align = block.get("align", "left")

                try:
                    font = ImageFont.truetype(font_path, font_size)
                except Exception:
                    font = ImageFont.load_default()

                if isinstance(color, str) and color.startswith("#"):
                    color_hex = color[1:]
                    r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
                    color = (r, g, b)

                if align == "center":
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    x = (self.width - text_width) // 2
                elif align == "right":
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    x = self.width - text_width - block.get("x", 0)
                else:
                    x = block.get("x", 0)

                draw.text((x, y), text, font=font, fill=color)

            img.save(overlay_png, "PNG")

            # Apply speed change and overlay
            filters = []
            if speed != 1.0:
                filters.append(f"[0:v]setpts={1/speed}*PTS[v]")
                input_label = "[v]"
            else:
                input_label = "[0:v]"

            overlay_filter = f"{input_label}[1:v]overlay=0:0"
            if filters:
                filters.append(overlay_filter)
                filter_str = ";".join(filters)
            else:
                filter_str = overlay_filter

            cmd = [
                "ffmpeg", "-y",
                "-i", input_file,
                "-i", overlay_png,
                "-filter_complex", filter_str,
                *self._base_encode_args(),
                "-an",
                output_file,
            ]
            return run_ffmpeg_sync(cmd, f"caption ({caption[:20]}...)")
        finally:
            if os.path.exists(overlay_png):
                os.remove(overlay_png)

    def create_scene_transition(self, caption: str, output_file: str, duration: float = 2.0) -> bool:
        """Create a scene transition card using Pillow PNG overlay."""
        bg = "#1a1a2e"

        text_blocks = [{
            "text": caption,
            "font_path": self.font_bold,
            "font_size": 56,
            "color": "white",
            "y": self.height // 2,
            "align": "center",
        }]

        overlay_png = self._generate_text_overlay_png(text_blocks, bg_color=bg)

        try:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", overlay_png,
                "-vf", f"fade=t=in:st=0:d=0.3,fade=t=out:st={duration-0.3}:d=0.3",
                *self._base_encode_args(),
                "-t", str(duration),
                output_file,
            ]
            return run_ffmpeg_sync(cmd, f"transition ({caption[:20]}...)")
        finally:
            if os.path.exists(overlay_png):
                os.remove(overlay_png)

    def concatenate(self, file_list: list[str], output_file: str) -> bool:
        """Concatenate video segments using ffmpeg concat demuxer."""
        existing = [f for f in file_list if os.path.exists(f)]
        if not existing:
            log.error("No files to concatenate")
            return False

        list_file = output_file + ".concat.txt"
        with open(list_file, "w") as f:
            for filepath in existing:
                f.write(f"file '{os.path.abspath(filepath)}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264", "-preset", "medium", "-crf", str(self.crf),
            "-r", str(self.fps), "-pix_fmt", "yuv420p",
            output_file,
        ]
        success = run_ffmpeg_sync(cmd, "concatenate")

        if os.path.exists(list_file):
            os.remove(list_file)

        if success:
            duration = get_video_duration(output_file)
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            log.info(
                "Final video: %s (%.1fs, %.1f MB)", output_file, duration, size_mb
            )
        return success

    def create_screenshot_slideshow(
        self,
        screenshot_paths: list[str],
        output_file: str,
        duration_per_image: float = 2.5,
        crossfade_duration: float = 0.5,
    ) -> bool:
        """Create video slideshow from screenshots with crossfade transitions.

        Args:
            screenshot_paths: List of image file paths
            output_file: Output video path
            duration_per_image: Seconds to show each image
            crossfade_duration: Crossfade transition duration

        Returns:
            True if successful, False otherwise
        """
        if not screenshot_paths:
            log.error("No screenshots provided for slideshow")
            return False

        # Build ffmpeg command with crossfade filter
        inputs = []
        filter_parts = []

        # Add each image as a looped input
        for path in screenshot_paths:
            if not os.path.exists(path):
                log.error("Screenshot not found: %s", path)
                return False
            inputs.extend(["-loop", "1", "-t", str(duration_per_image), "-i", path])

        if len(screenshot_paths) == 1:
            # Single image, no crossfade needed
            filter_str = f"[0:v]scale={self.width}:{self.height}[v]"
        else:
            # Multiple images with crossfade transitions
            # Each crossfade: [v0][v1]xfade=transition=fade:duration=0.5:offset=2.0[v01]

            for i in range(len(screenshot_paths) - 1):
                if i == 0:
                    input_a = f"[{i}:v]"
                else:
                    input_a = f"[v{i-1}{i}]"

                input_b = f"[{i+1}:v]"
                output = f"[v{i}{i+1}]"
                offset = duration_per_image - crossfade_duration

                filter_parts.append(
                    f"{input_a}{input_b}xfade=transition=fade:"
                    f"duration={crossfade_duration}:offset={offset}{output}"
                )

            # Final scale
            last_output = f"[v{len(screenshot_paths)-2}{len(screenshot_paths)-1}]"
            filter_parts.append(f"{last_output}scale={self.width}:{self.height}[v]")
            filter_str = ";".join(filter_parts)

        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_str,
            "-map",
            "[v]",
            *self._base_encode_args(),
            output_file,
        ]

        return run_ffmpeg_sync(cmd, f"screenshot slideshow ({len(screenshot_paths)} images)")

    def create_summary_overlay(
        self,
        input_file: str,
        output_file: str,
        key_points: list[str],
        title: str = "AI Analysis Summary",
        position: str = "bottom_right",
    ) -> bool:
        """Add summary overlay with key points to video.

        Args:
            input_file: Input video
            output_file: Output video with overlay
            key_points: List of bullet point strings
            title: Title text for summary box
            position: "bottom_right", "top_left", "center", "bottom_left"

        Returns:
            True if successful, False otherwise
        """
        if not key_points:
            log.warning("No key points for summary overlay, copying input")
            import shutil

            shutil.copy2(input_file, output_file)
            return True

        # Calculate positioning
        box_width = 700
        box_padding = 40
        line_height = 35
        title_height = 50
        box_height = title_height + len(key_points) * line_height + box_padding * 2

        if position == "bottom_right":
            box_x = self.width - box_width - 40
            box_y = self.height - box_height - 40
        elif position == "top_left":
            box_x = 40
            box_y = 40
        elif position == "bottom_left":
            box_x = 40
            box_y = self.height - box_height - 40
        else:  # center
            box_x = (self.width - box_width) // 2
            box_y = (self.height - box_height) // 2

        # Create overlay image with Pillow
        try:
            # Create transparent RGBA image
            img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Draw semi-transparent background box
            draw.rectangle(
                [box_x, box_y, box_x + box_width, box_y + box_height],
                fill=(20, 20, 30, 230),  # Almost opaque dark blue
            )

            # Load fonts
            try:
                font_title = ImageFont.truetype(self.font_bold, 32)
                font_text = ImageFont.truetype(self.font_regular, 24)
            except Exception as e:
                log.warning("Failed to load fonts, using default: %s", e)
                font_title = ImageFont.load_default()
                font_text = ImageFont.load_default()

            # Draw title
            draw.text(
                (box_x + box_padding, box_y + box_padding),
                title,
                fill=(255, 215, 0, 255),  # Gold
                font=font_title,
            )

            # Draw bullet points
            for i, point in enumerate(key_points):
                y_pos = box_y + title_height + box_padding + i * line_height
                draw.text(
                    (box_x + box_padding, y_pos),
                    f"• {point}",
                    fill=(255, 255, 255, 255),  # White
                    font=font_text,
                )

            # Save overlay as PNG
            overlay_png = tempfile.NamedTemporaryFile(
                suffix=".png", delete=False, dir=os.path.dirname(output_file)
            )
            overlay_path = overlay_png.name
            overlay_png.close()
            img.save(overlay_path, "PNG")

            # Apply overlay with FFmpeg
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                input_file,
                "-i",
                overlay_path,
                "-filter_complex",
                "[0:v][1:v]overlay=0:0",
                *self._base_encode_args(),
                output_file,
            ]

            success = run_ffmpeg_sync(cmd, "summary overlay")

            # Cleanup temp overlay
            if os.path.exists(overlay_path):
                os.remove(overlay_path)

            return success

        except Exception as e:
            log.error("Failed to create summary overlay: %s", e)
            return False

    def process_scenes(
        self,
        raw_recording: str,
        terminal_videos: dict[str, str],
        scene_markers: dict[str, float],
        temp_dir: str,
        output_file: str,
    ) -> bool:
        """Full post-processing pipeline: split, caption, speed-adjust, concat."""
        os.makedirs(temp_dir, exist_ok=True)
        segments = []
        idx = 0

        # Intro
        intro_file = os.path.join(temp_dir, "00_intro.mp4")
        if self.create_intro(intro_file):
            segments.append(intro_file)

        for scene in self.scenes:
            sid = scene["id"]
            caption = scene.get("caption", "")
            speed = scene.get("post_speed", 1.0)
            idx += 1
            prefix = f"{idx:02d}_{sid}"

            # Terminal scenes (synthetic video)
            if sid in terminal_videos:
                tv = terminal_videos[sid]
                if os.path.exists(tv):
                    captioned = os.path.join(temp_dir, f"{prefix}_captioned.mp4")
                    if self.add_caption_bar(tv, captioned, caption):
                        segments.append(captioned)
                    else:
                        segments.append(tv)
                continue

            # Browser recording scenes - extract by markers
            start_time = scene_markers.get(f"{sid}_start")
            end_time = scene_markers.get(f"{sid}_end")

            if start_time is None or end_time is None:
                log.warning("No markers for scene %s, creating transition card", sid)
                transition = os.path.join(temp_dir, f"{prefix}_transition.mp4")
                if self.create_scene_transition(caption, transition):
                    segments.append(transition)
                continue

            duration = end_time - start_time
            if duration <= 0:
                continue

            # Extract scene segment (input may be .webm from Playwright)
            extracted = os.path.join(temp_dir, f"{prefix}_raw.mp4")
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", raw_recording,
                "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                       f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "fast", "-crf", str(self.crf),
                "-r", str(self.fps), "-pix_fmt", "yuv420p",
                extracted,
            ]
            if not run_ffmpeg_sync(cmd, f"extract {sid}"):
                continue

            # Add caption and speed
            captioned = os.path.join(temp_dir, f"{prefix}_captioned.mp4")
            if self.add_caption_bar(extracted, captioned, caption, speed=speed):
                segments.append(captioned)
            else:
                segments.append(extracted)

        # Outro
        outro_file = os.path.join(temp_dir, "99_outro.mp4")
        if self.create_outro(outro_file):
            segments.append(outro_file)

        # Final concatenation
        return self.concatenate(segments, output_file)

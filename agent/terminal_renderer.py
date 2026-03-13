"""Synthetic terminal frame generation using PIL.

Renders command output as terminal-style video frames (black background,
green monospace text) and encodes them to MP4 with ffmpeg.
"""

import logging
import os
import shutil
import textwrap

from PIL import Image, ImageDraw, ImageFont

from .utils import resolve_font, run_ffmpeg_sync

log = logging.getLogger(__name__)

FONT_PATH = resolve_font(bold=False) or ""
FONT_BOLD_PATH = resolve_font(bold=True) or ""

WIDTH = 1920
HEIGHT = 1080
MARGIN = 60
LINE_HEIGHT = 28
FONT_SIZE = 22
TITLE_FONT_SIZE = 18
BG_COLOR = (18, 18, 28)
TEXT_COLOR = (0, 230, 118)       # terminal green
PROMPT_COLOR = (100, 200, 255)   # prompt blue
DIM_COLOR = (100, 100, 120)      # dim gray
TITLE_BAR_COLOR = (40, 40, 55)
TITLE_BAR_HEIGHT = 36
FPS = 30


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD_PATH if bold else FONT_PATH
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


def render_terminal_frame(
    lines: list[str],
    title: str = "Terminal",
    prompt: str = "",
    cursor: bool = False,
) -> Image.Image:
    """Render a single terminal frame as a PIL Image."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font = _load_font(FONT_SIZE)
    title_font = _load_font(TITLE_FONT_SIZE, bold=True)

    # Title bar
    draw.rectangle([0, 0, WIDTH, TITLE_BAR_HEIGHT], fill=TITLE_BAR_COLOR)
    # Window buttons (decorative)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([MARGIN + i * 24, 10, MARGIN + i * 24 + 16, 26], fill=color)
    draw.text((MARGIN + 90, 8), title, fill=(180, 180, 200), font=title_font)

    y = TITLE_BAR_HEIGHT + MARGIN // 2
    max_lines = (HEIGHT - y - MARGIN) // LINE_HEIGHT

    # Render output lines
    visible = lines[-max_lines:] if len(lines) > max_lines else lines
    for line in visible:
        clean = _strip_ansi(line)
        # Wrap long lines
        if len(clean) > 120:
            wrapped = textwrap.wrap(clean, width=120)
            for wl in wrapped:
                if y + LINE_HEIGHT > HEIGHT - MARGIN:
                    break
                draw.text((MARGIN, y), wl, fill=TEXT_COLOR, font=font)
                y += LINE_HEIGHT
        else:
            draw.text((MARGIN, y), clean, fill=TEXT_COLOR, font=font)
            y += LINE_HEIGHT

        if y + LINE_HEIGHT > HEIGHT - MARGIN:
            break

    # Prompt line with cursor
    if prompt:
        if y + LINE_HEIGHT <= HEIGHT - MARGIN:
            draw.text((MARGIN, y), prompt, fill=PROMPT_COLOR, font=font)
            if cursor:
                pw = draw.textlength(prompt, font=font)
                draw.rectangle(
                    [MARGIN + pw + 2, y, MARGIN + pw + 12, y + LINE_HEIGHT - 4],
                    fill=TEXT_COLOR,
                )

    return img


def render_terminal_video(
    command: str,
    output_text: str,
    output_path: str,
    title: str = "Terminal",
    caption: str = "",
    hold_secs: float = 2.0,
    typing_fps: int = 3,
) -> bool:
    """Generate a terminal-style video showing command execution and output.

    1. Empty terminal with prompt (0.5s)
    2. Command typing animation
    3. Output lines appearing one by one
    4. Hold final frame
    """
    frames_dir = output_path + "_frames"
    os.makedirs(frames_dir, exist_ok=True)

    frame_idx = 0
    prompt_base = "$ "
    output_lines = output_text.strip().splitlines() if output_text.strip() else ["(no output)"]

    def save_frame(img: Image.Image, count: int = 1):
        nonlocal frame_idx
        for _ in range(count):
            img.save(os.path.join(frames_dir, f"frame_{frame_idx:05d}.png"))
            frame_idx += 1

    # Phase 1: Empty prompt (0.5s)
    img = render_terminal_frame([], title=title, prompt=prompt_base, cursor=True)
    save_frame(img, count=int(FPS * 0.5))

    # Phase 2: Typing command
    for i in range(1, len(command) + 1):
        partial = command[:i]
        img = render_terminal_frame(
            [], title=title, prompt=f"{prompt_base}{partial}", cursor=True
        )
        frames_per_char = max(1, FPS // typing_fps // 3)
        save_frame(img, count=frames_per_char)

    # Brief pause after typing (0.3s)
    img = render_terminal_frame(
        [], title=title, prompt=f"{prompt_base}{command}", cursor=True
    )
    save_frame(img, count=int(FPS * 0.3))

    # Phase 3: Output lines appearing
    shown_lines = []
    lines_per_frame = max(1, len(output_lines) // (FPS * 3))  # ~3s for all output

    for i, line in enumerate(output_lines):
        shown_lines.append(line)
        # Show each line for a few frames
        img = render_terminal_frame(shown_lines, title=title)
        frames = max(1, FPS // max(1, len(output_lines) // 3))
        frames = min(frames, FPS // 2)  # cap at 0.5s per line
        save_frame(img, count=frames)

    # Phase 4: Hold final frame
    img = render_terminal_frame(shown_lines, title=title, prompt=prompt_base, cursor=True)
    save_frame(img, count=int(FPS * hold_secs))

    # Encode frames to video
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(frames_dir, "frame_%05d.png"),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        output_path,
    ]
    success = run_ffmpeg_sync(cmd, f"terminal video ({title})")

    # Cleanup frames
    shutil.rmtree(frames_dir, ignore_errors=True)

    if success:
        log.info("Terminal video created: %s (%d frames)", output_path, frame_idx)
    return success

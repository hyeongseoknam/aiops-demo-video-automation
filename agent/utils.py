"""Shared utilities: logging, config loading, ffmpeg helpers, font resolution."""

import asyncio
import logging
import platform
import subprocess
import time
from pathlib import Path

import yaml


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def escape_ffmpeg_text(text: str) -> str:
    """Escape special chars for ffmpeg drawtext filter."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\''")
    text = text.replace(":", "\\:")
    text = text.replace("%", "\\%")
    return text


def escape_ffmpeg_fontpath(path: str) -> str:
    r"""Escape font file path for ffmpeg drawtext filter.

    FFmpeg drawtext has specific requirements:
    - Colons must be escaped as \\:
    - Backslashes must be escaped as \\\\
    - Do NOT wrap in quotes (path is already in filter string)
    """
    if not path:
        return ""
    # Escape backslashes first (Windows paths)
    path = path.replace("\\", "\\\\")
    # Escape colons (macOS/Linux paths)
    path = path.replace(":", "\\:")
    return path


def run_ffmpeg_sync(cmd: list[str], desc: str = "") -> bool:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.getLogger("ffmpeg").warning(
            "%s failed: %s", desc, (result.stderr or "")[:300]
        )
    return result.returncode == 0


async def run_ffmpeg_async(cmd: list[str], desc: str = "") -> bool:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logging.getLogger("ffmpeg").warning(
            "%s failed: %s", desc, (stderr.decode() if stderr else "")[:300]
        )
    return proc.returncode == 0


def get_video_duration(filepath: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath,
        ],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip()) if result.stdout.strip() else 0.0


def _find_font(candidates: list[str]) -> str | None:
    """Return the first candidate path that exists, or None."""
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def resolve_font(bold: bool = False) -> str | None:
    """Find a CJK-capable font for the current OS.

    Returns the first existing path from a prioritized list per platform.
    Used as fallback when config doesn't specify fonts or the specified path
    doesn't exist on the target OS.
    """
    system = platform.system()

    if bold:
        candidates = {
            "Linux": [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
            ],
            "Darwin": [
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                str(Path.home() / "Library/Fonts/NotoSansCJK-Bold.ttc"),
                "/opt/homebrew/share/fonts/NotoSansCJK-Bold.ttc",
            ],
        }
    else:
        candidates = {
            "Linux": [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
            ],
            "Darwin": [
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                str(Path.home() / "Library/Fonts/NotoSansCJK-Regular.ttc"),
                "/opt/homebrew/share/fonts/NotoSansCJK-Regular.ttc",
            ],
        }

    return _find_font(candidates.get(system, candidates["Linux"]))


def resolve_font_for_config(config_path: str | None) -> str:
    """Return config_path if it exists, otherwise auto-detect a suitable font."""
    if config_path and Path(config_path).exists():
        return config_path
    bold = config_path and "Bold" in config_path if config_path else False
    resolved = resolve_font(bold=bold)
    if resolved:
        logging.getLogger("fonts").info(
            "Font auto-resolved: %s -> %s", config_path, resolved
        )
        return resolved
    logging.getLogger("fonts").warning(
        "No CJK font found (config: %s). Text rendering may use fallback.", config_path
    )
    return config_path or ""


class Timer:
    """Simple context-manager timer for logging scene durations."""

    def __init__(self, label: str):
        self.label = label
        self.start = 0.0
        self.elapsed = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *args):
        self.elapsed = time.monotonic() - self.start
        logging.getLogger("timer").info(
            "%s completed in %.1fs", self.label, self.elapsed
        )

# AIOps Demo Video Agent — Environment Transfer Guide

> **📚 Documentation Index:**
> - **PROJECT.md** - Complete project overview, architecture, status, and known issues
> - **DEVELOPMENT.md** - Setup instructions, troubleshooting, and development workflow
> - **TRANSFER.md** (this file) - Platform migration and deployment guide

---

## Overview

This agent records demo videos of the AIOps system by orchestrating:
- Chaos trouble injection (`start.sh` / `stop.sh`)
- Browser automation (Playwright Chromium)
- Synthetic terminal rendering (PIL → ffmpeg)
- Post-processing (ffmpeg caption, speed, concat)

**For new sessions:** Start with `PROJECT.md` for current status and architecture details.

## Architecture (OS-agnostic)

```
demo_movie/
├── setup.sh                        # Cross-platform setup (Linux/macOS)
├── run.py                          # CLI entry point
├── requirements.txt                # Python deps (playwright, Pillow, PyYAML)
├── config/
│   ├── scenario.yaml               # Active config (Linux)
│   └── scenario_osx.yaml           # macOS template
├── agent/
│   ├── orchestrator.py             # Scene orchestrator
│   ├── browser_auto.py             # Playwright automation + record_video
│   ├── trouble_runner.py           # Chaos start/stop via shell scripts
│   ├── terminal_renderer.py        # Synthetic terminal frames (PIL)
│   ├── post_processor.py           # ffmpeg post-processing
│   ├── recorder.py                 # (legacy x11grab — unused)
│   ├── k6_runner.py                # (unused — user runs k6 externally)
│   └── utils.py                    # Config, fonts, ffmpeg helpers
└── output/                         # Generated videos
```

## Prerequisites by OS

| Dependency       | Linux (Ubuntu 24.04)                          | macOS                                         |
|------------------|-----------------------------------------------|-----------------------------------------------|
| Python 3.12+     | `sudo apt install python3 python3-venv`       | `brew install python@3.12`                    |
| ffmpeg           | `sudo apt install ffmpeg`                     | `brew install ffmpeg`                         |
| CJK Fonts        | `sudo apt install fonts-noto-cjk`             | Built-in (`AppleSDGothicNeo`) or `brew install --cask font-noto-sans-cjk` |
| Playwright       | Installed by `setup.sh`                       | Installed by `setup.sh`                       |
| Docker (AIOps)   | Already running                               | `brew install --cask docker` + start services |

## Transfer Steps (Linux → macOS)

### 1. Copy project files

```bash
# On macOS
git clone <repo> ~/demo_movie    # or scp/rsync from Linux
cd ~/demo_movie
```

Files to transfer (exclude `.venv/` and `output/`):
```
agent/          config/         requirements.txt
run.py          setup.sh        TRANSFER.md
```

### 2. Set up the AIOps system

The AIOps docker-compose stack must be running on macOS with:
- Web UI accessible at `http://localhost:8080`
- Chaos trouble scripts available locally

```bash
# Clone or copy the app repo that contains:
#   app/chaos/trouble/01_cpu_spike/start.sh
#   app/chaos/trouble/01_cpu_spike/stop.sh
#   ...
#   app/chaos/trouble/12_mysql_column_error/start.sh

# Start the docker-compose AIOps stack
cd ~/app
docker-compose up -d
```

### 3. Configure paths

```bash
cd ~/demo_movie
cp config/scenario_osx.yaml config/scenario.yaml
```

Edit `config/scenario.yaml` — update these paths:

```yaml
trouble:
  base_dir: /Users/YOUR_USER/app/chaos/trouble   # ← update

browser:
  base_url: "http://localhost:8080"               # ← verify port
```

Font paths are **auto-detected** — no need to configure unless you want a specific font.

### 4. Run setup

```bash
chmod +x setup.sh
./setup.sh
```

This creates `.venv`, installs Python deps, and downloads Chromium.

### 5. Start K6 externally

K6 load generation must be started by the user before running the agent:
```bash
# In a separate terminal
cd ~/app/chaos/load
./k6 run scripts/normal_traffic.js --duration 10m --vus 10
```

### 6. Run the agent

```bash
source .venv/bin/activate
python run.py --dry-run              # pre-flight checks only
python run.py                        # full pipeline
python run.py --skip-trouble         # browser automation only
python run.py --force                # ignore pre-flight failures
```

## What's Cross-Platform

| Component             | Strategy                                    |
|-----------------------|---------------------------------------------|
| Screen recording      | Playwright `record_video` (no display dependency) |
| Terminal rendering    | PIL image generation → ffmpeg encode        |
| Font resolution       | Auto-detect per OS in `agent/utils.py`      |
| Post-processing       | ffmpeg CLI (same on both platforms)          |
| Browser automation    | Playwright Chromium (same API)              |
| Trouble scripts       | `bash start.sh` / `bash stop.sh` (portable) |

## What Needs Manual Adjustment

| Item                  | Why                                                      |
|-----------------------|----------------------------------------------------------|
| `trouble.base_dir`    | Absolute path to chaos scripts differs per machine       |
| `browser.base_url`    | Port may differ if docker-compose maps differently       |
| Browser XPath selectors | May need updating if the web UI version changes        |
| K6 binary path        | Not managed by agent — user runs k6 externally           |

## Known Issues

1. **Copilot XPath selectors** may need updating — the `new_chat_xpath` and
   `textarea_xpath` depend on the exact DOM structure of the Copilot UI.
   The agent has fallback strategies but may still fail. Use `--verbose` to
   see debug logs, and check `output/temp/screenshots/` for failure captures.

2. **Playwright video format** is `.webm` (VP8). Post-processing re-encodes
   to H.264 MP4. This is handled automatically.

3. **CJK font rendering** — if Korean text appears as boxes, install a CJK font:
   - macOS: `brew install --cask font-noto-sans-cjk`
   - Linux: `sudo apt install fonts-noto-cjk`

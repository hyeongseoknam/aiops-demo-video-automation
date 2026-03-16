# AIOps Demo Video Automation Agent

> Automated demonstration video creation for AIOps monitoring systems with AI Copilot integration

**Status:** ✅ Fully Functional | **Last Run:** 2026-03-16 | **Output:** 128.9s demo video (all 14 scenes!)

---

## 🎬 What This Does

Creates professional demonstration videos showing:
1. Login to monitoring system
2. Baseline dashboard (normal state)
3. Chaos injection (downstream delay)
4. Performance impact visualization
5. AI Copilot navigation
6. Natural language query submission
7. AI-generated performance analysis (streaming)
8. Response summary overlay with key points
9. Hitmap transaction validation
10. Trouble recovery

**Output:** YouTube-ready Full HD (1920x1080) MP4 videos with English captions and branding

---

## 🚀 Quick Start

### First Time Setup
```bash
# 1. Install dependencies
./setup.sh

# 2. Configure for your environment
cp config/scenario_osx.yaml config/scenario.yaml
# Edit scenario.yaml with your server URL

# 3. Run pre-flight checks
source .venv/bin/activate
python run.py --dry-run

# 4. Generate demo video (full pipeline!)
python run.py
```

**Output:** `output/aiops_demo_05_downstream_delay.mp4` (~129 seconds, 3.0 MB)

---

## 📚 Documentation Guide

**Choose your path:**

### 🆕 New to This Project?
→ Start with **[PROJECT.md](PROJECT.md)**
- Project overview and architecture
- Current implementation status
- Known issues and limitations
- Component breakdown

### 💻 Setting Up Development?
→ Read **[DEVELOPMENT.md](DEVELOPMENT.md)**
- Environment setup instructions
- Configuration guide
- Troubleshooting common issues
- Development workflow

### 🔄 Deploying to Another Machine?
→ Check **[TRANSFER.md](TRANSFER.md)**
- Platform-specific requirements
- Linux ↔ macOS migration
- Docker setup notes
- Path configuration

### 🔍 Want Quick Status?
→ See **[STATUS.md](STATUS.md)**
- Current project state
- Last run results
- Active issues
- TODO list

### 🤖 Starting a New Claude Session?
→ Read files in this order:
1. **STATUS.md** - Get oriented (5 min read)
2. **PROJECT.md** - Understand architecture (10 min read)
3. **DEVELOPMENT.md** - Review workflows (reference)

---

## ⚡ Common Commands

```bash
# Activate environment
source .venv/bin/activate

# Pre-flight check (safe, no recording)
python run.py --dry-run

# Generate demo (RECOMMENDED - full pipeline)
python run.py

# Debug mode
python run.py --verbose

# Browser automation only (if SSH not configured)
python run.py --skip-trouble --force

# Raw recording only (fast test)
python run.py --skip-postprocess
```

---

## 📦 Requirements

- **Python:** 3.12+ (uses `str | None` syntax)
- **ffmpeg:** 8.0+ (video processing with xfade, overlay)
- **System Fonts:** Auto-detected per OS (AppleSDGothicNeo on macOS, NotoSansCJK on Linux)
- **Playwright:** Chromium browser (~200 MB download)
- **Pillow:** For overlay image generation

**macOS Install:**
```bash
brew install python@3.12 ffmpeg
./setup.sh
```

**Linux Install:**
```bash
sudo apt install python3 python3-venv ffmpeg fonts-noto-cjk
./setup.sh
```

---

## 🎯 Current Status

| Feature | Status |
|---------|--------|
| Browser Automation | ✅ Working |
| Video Recording | ✅ Working |
| Scene Orchestration | ✅ Working (14 scenes) |
| Video Post-processing | ✅ Working |
| SSH Trouble Injection | ✅ Working |
| Response Analysis | ✅ Working (AI summary overlay) |
| Hitmap Validation | ✅ Working (XPath-based selection) |
| Caption Rendering | ✅ Working (FFmpeg overlays) |
| English Language | ✅ Working |
| YouTube Format | ✅ Working (1080p 16:9) |

**Latest Output:** 3.0 MB MP4, 128.9 seconds (ALL 14 SCENES), 1920x1080 @ 30fps

**Known Issues:** See [PROJECT.md - Known Issues](PROJECT.md#-known-issues)

---

## 🏗️ Architecture

```
run.py (CLI)
    ↓
orchestrator.py (Coordinator)
    ├── trouble_runner.py (SSH chaos injection)
    ├── browser_auto.py (Playwright automation)
    ├── terminal_renderer.py (Synthetic terminal videos)
    └── post_processor.py (FFmpeg pipeline)
```

**Recording Strategy:** Playwright's built-in `record_video` (no display server needed)

**Scenes (14 total):**
1. Login → 2. Normal Dashboard → 3. Trouble Start → 4. Trouble Dashboard → 5. Navigate Copilot → 6. New Chat → 7. Type Query → 8. Wait Response → 9. Show Result → 10. Navigate Hitmap → 11. Hitmap Search → 12. Select Transactions → 13. Show Transactions → 14. Trouble Stop

---

## 🐛 Troubleshooting

### "Host key verification failed" (RESOLVED)
```bash
# Solution: Add SSH host (already done in current setup)
ssh-keyscan -H YOUR_SERVER_IP >> ~/.ssh/known_hosts

# Verify it works
python run.py --dry-run
# Should show: [OK] trouble script (remote): .../start.sh

# Fallback: Use without trouble injection
python run.py --skip-trouble --force
```

### "TypeError: unsupported operand type"
```bash
# Wrong Python version - need 3.12+
brew install python@3.12
rm -rf .venv
./setup.sh
```

### More Issues?
→ See **[DEVELOPMENT.md - Troubleshooting](DEVELOPMENT.md#-troubleshooting)**

---

## 📂 Project Structure

```
demo_movie/
├── README.md              ← You are here
├── PROJECT.md             ← Architecture & status
├── DEVELOPMENT.md         ← Setup & workflow
├── STATUS.md              ← Quick snapshot
├── TRANSFER.md            ← Platform migration
├── run.py                 ← CLI entry point
├── setup.sh               ← Installation script
├── requirements.txt       ← Python deps
│
├── config/
│   ├── scenario.yaml      ← Active config
│   └── scenario_osx.yaml  ← macOS template
│
├── agent/                 ← Core modules
│   ├── orchestrator.py    ← Main coordinator
│   ├── browser_auto.py    ← Playwright automation
│   ├── trouble_runner.py  ← Chaos injection
│   ├── terminal_renderer.py ← Synthetic terminal
│   ├── post_processor.py  ← FFmpeg pipeline
│   └── utils.py           ← Helpers
│
└── output/
    ├── aiops_demo_final.mp4 ← Final video
    └── temp/                ← Intermediate files
```

---

## 🎥 Sample Output

**Generated Video:**
- **Duration:** ~129 seconds (2.1 minutes)
- **Resolution:** 1920x1080 (YouTube Full HD 16:9)
- **Frame Rate:** 30 fps
- **Format:** H.264 MP4
- **Size:** ~3.0 MB
- **Language:** English

**Scenes Include:**
- System login and authentication
- Baseline performance dashboard
- Chaos injection (synthetic terminal)
- Performance impact visualization
- AI Copilot navigation
- Natural language query submission
- Streaming AI response with real-time updates
- AI analysis summary overlay (5 key points)
- Hitmap transaction validation
- Slow transaction selection (XPath-based)
- Trouble recovery

---

## 🤝 Contributing

When making changes:
1. ✅ Test with `python run.py --dry-run`
2. ✅ Update relevant documentation (PROJECT.md, DEVELOPMENT.md, STATUS.md)
3. ✅ Test end-to-end with `--skip-trouble --force`
4. ✅ Document breaking changes in TRANSFER.md
5. ✅ Update STATUS.md with current state

---

## 📝 TODOs

**High Priority:**
- [x] YouTube 1080p format (16:9)
- [x] English language support
- [x] Response analysis with AI summary overlay
- [x] Hitmap validation with XPath selection
- [x] Video encoding race condition fix

**Medium Priority:**
- [ ] Support multiple scenarios in one batch run
- [ ] Add CLI flag for stabilization time
- [ ] Configuration validation
- [ ] Improve error messages

**Low Priority:**
- [ ] Remove unused code
- [ ] Add unit tests
- [ ] Generate HTML reports

---

## 📄 License

(License information here)

---

## 📧 Contact

(Contact information here)

---

**Last Updated:** 2026-03-16
**Version:** 2.0
**Status:** ✅ Production Ready (YouTube 1080p, English, AI Summary, Hitmap Validation)

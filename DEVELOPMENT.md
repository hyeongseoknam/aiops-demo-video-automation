# Development Guide - AIOps Demo Video Agent

**For:** Developers and AI assistants working on this project
**Last Updated:** 2026-03-12

---

## 🚀 Quick Start (New Session)

If you're resuming work in a new Claude session:

```bash
# 1. Navigate to project
cd /Users/whatap/git_hub/demo_movie

# 2. Read project status
cat PROJECT.md | head -50

# 3. Check current config
cat config/scenario.yaml

# 4. Activate environment
source .venv/bin/activate

# 5. Verify setup
python run.py --dry-run
```

---

## 📥 Initial Setup

### Prerequisites Check

```bash
# Check Python version (need 3.12+)
python3 --version

# Check if Homebrew available (macOS)
which brew

# Check if ffmpeg installed
ffmpeg -version

# Check available fonts (macOS)
ls /System/Library/Fonts/*.ttc
```

### One-Time Setup

```bash
# 1. Install system dependencies
brew install python@3.12 ffmpeg

# 2. Run setup script
./setup.sh

# This will:
# - Create Python 3.12 virtual environment
# - Install playwright, Pillow, PyYAML
# - Download Chromium browser (~200 MB)
```

### Manual Setup (if setup.sh fails)

```bash
# 1. Create virtual environment
/Users/whatap/git_hub/brew/bin/python3.12 -m venv .venv

# 2. Activate environment
source .venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browsers
playwright install chromium
```

---

## 🔧 Configuration

### Environment Variables

None required currently. Configuration is file-based.

### Configuration Files

#### `config/scenario.yaml` (Active)

**Current Setup:** macOS client → EC2 remote server

```yaml
trouble:
  base_dir: /home/whatap/app/chaos/trouble
  scenario: "05_downstream_delay"
  port: 8083
  params: ["5"]
  ssh_host: "ubuntu@43.203.137.253"  # ← Change for your environment

browser:
  base_url: "http://43.203.137.253:8080"  # ← Your server URL
  login:
    email: admin@whatap.io
    password: admin
  query: "Project Avg Tps 요약해줘"  # ← Customize query
```

#### `config/scenario_osx.yaml` (Template)

Template for localhost development:
```yaml
trouble:
  base_dir: /Users/${USER}/app/chaos/trouble
  # No ssh_host = run locally

browser:
  base_url: "http://localhost:8080"
```

### Switching Configurations

```bash
# For remote EC2 (current)
# No change needed, scenario.yaml already configured

# For local development
cp config/scenario_osx.yaml config/scenario.yaml
# Edit base_dir to match your local path

# For different scenario
# Edit scenario.yaml:
#   scenario: "01_cpu_spike"
#   params: ["80"]  # 80% CPU
```

---

## 🎮 Running the Agent

### Command Line Options

```bash
python run.py [OPTIONS]

Options:
  -c, --config PATH       Config file (default: config/scenario.yaml)
  -o, --output DIR        Output directory (default: output)
  --skip-trouble          Skip chaos injection/recovery
  --skip-postprocess      Skip video post-processing (raw only)
  --dry-run               Pre-flight checks only, no recording
  --force                 Continue even if pre-flight fails
  -v, --verbose           Enable DEBUG logging
```

### Common Use Cases

#### 1. Test Configuration (Safe)
```bash
python run.py --dry-run
```
Output:
```
[OK] ffmpeg available
[OK] Font available
[OK] Web service reachable
[FAIL] trouble script not found (if SSH issue)
```

#### 2. Browser Automation Only (Recommended)
```bash
python run.py --skip-trouble --force
```
Use when:
- SSH not configured
- Testing browser interactions
- Developing new scenes

#### 3. Full Pipeline (Requires SSH)
```bash
python run.py
```
Includes:
- Trouble injection
- Browser recording
- Trouble recovery
- Post-processing

#### 4. Debug Mode
```bash
python run.py --skip-trouble --force --verbose
```
Shows:
- Scene markers with timestamps
- Playwright debug info
- FFmpeg command details
- Error tracebacks

#### 5. Raw Recording Only
```bash
python run.py --skip-trouble --skip-postprocess --force
```
Outputs:
- `output/temp/raw_recording.webm` only
- No captions, no concatenation
- Fast (~50 seconds)

---

## 🐛 Troubleshooting

### Issue: SSH Host Key Verification Failed (RESOLVED)

**Status:** ✅ RESOLVED (2026-03-13)

**Was:**
```
[FAIL] trouble script not found (remote)
Host key verification failed
```

**Solution:** SSH access configured. Full pipeline now works!

**Verify:**
```bash
python run.py --dry-run
# Should show: [OK] trouble script (remote): .../start.sh
```

**If you encounter this on a new machine:**
```bash
# Option 1: Add host to known_hosts (Recommended)
ssh-keyscan -H YOUR_SERVER_IP >> ~/.ssh/known_hosts

# Option 2: Configure SSH config
cat >> ~/.ssh/config <<EOF
Host YOUR_SERVER_IP
    StrictHostKeyChecking accept-new
    User ubuntu
EOF
```

---

### Issue: Python Version Error

**Symptom:**
```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

**Cause:** Python < 3.10 doesn't support `str | None` syntax

**Solution:**
```bash
# Install Python 3.12
brew install python@3.12

# Recreate venv
rm -rf .venv
/Users/whatap/git_hub/brew/bin/python3.12 -m venv .venv

# Run setup
./setup.sh
```

**Verify:**
```bash
source .venv/bin/activate
python --version  # Should be 3.12+
```

---

### Issue: FFmpeg Caption Rendering Failed

**Symptom:**
```
[ffmpeg] WARNING caption (...) failed
```

**Root Cause:** Font path escaping issue

**Current Workaround:** Captions are skipped, video still generated

**Permanent Fix:** Edit `agent/post_processor.py`
```python
# Line 106 - Change from:
f"drawtext=fontfile='{self.font_bold}':text='{text}':..."

# To:
import shlex
f"drawtext=fontfile={shlex.quote(self.font_bold)}:text='{text}':..."
```

**Test fix:**
```bash
python run.py --skip-trouble --force --verbose
# Check for successful caption creation
ls -lh output/temp/*_captioned.mp4
```

---

### Issue: Web Service Unreachable

**Symptom:**
```
[FAIL] Web service unreachable: http://...
```

**Diagnosis:**
```bash
# Check if server is up
curl -I http://43.203.137.253:8080

# Check if port is open
nc -zv 43.203.137.253 8080

# Check DNS resolution
nslookup 43.203.137.253
```

**Solutions:**
1. Verify server is running: `docker-compose ps`
2. Check firewall rules
3. Update `base_url` in config if port changed

---

### Issue: Playwright Browser Launch Failed

**Symptom:**
```
Error: Browser not found
```

**Solution:**
```bash
source .venv/bin/activate
playwright install chromium
```

**Verify:**
```bash
playwright --version
# Should show: Version 1.49.0
```

---

### Issue: AI Response Timeout

**Symptom:**
```
[WARNING] Response wait timed out after 120s
```

**Causes:**
1. AI Copilot is actually slow (valid timeout)
2. Response detection logic failed
3. Network issues

**Solutions:**
```bash
# 1. Increase timeout in browser_auto.py line 207
await self.browser.wait_for_response(timeout=300)  # 5 minutes

# 2. Check screenshots for actual page state
ls output/temp/screenshots/

# 3. Test AI Copilot manually in browser
open http://43.203.137.253:8080/aiops/copilot/
```

---

### Issue: Korean Text Shows as Boxes

**Symptom:** Terminal videos show □□□ instead of Korean

**Diagnosis:**
```python
python -c "from agent.utils import resolve_font; print(resolve_font(bold=True))"
# Should show: /System/Library/Fonts/AppleSDGothicNeo.ttc
```

**Solution (macOS):**
```bash
# Install Noto Sans CJK
brew install --cask font-noto-sans-cjk

# Update config to use it
# config/scenario.yaml:
post_process:
  font_bold: "/Users/$(whoami)/Library/Fonts/NotoSansCJK-Bold.ttc"
```

**Solution (Linux):**
```bash
sudo apt install fonts-noto-cjk
```

---

## 🧪 Testing & Validation

### Pre-Flight Validation
```bash
python run.py --dry-run
```
**Expected output:**
- ✅ ffmpeg available
- ✅ Font available
- ✅ Web service reachable (HTTP 302)
- ⚠️ trouble scripts (if no SSH)

### End-to-End Test
```bash
# Full test (skip trouble to avoid SSH)
python run.py --skip-trouble --force

# Expected result:
# - output/aiops_demo_final.mp4 created
# - Size: ~1 MB
# - Duration: 40-50 seconds
# - Resolution: 1920x1080
```

### Verify Output
```bash
# Check file created
ls -lh output/aiops_demo_final.mp4

# Check video properties
ffmpeg -i output/aiops_demo_final.mp4 2>&1 | grep -E "Duration|Video:"

# Play video (macOS)
open output/aiops_demo_final.mp4

# Check all temp files
ls -lh output/temp/
```

### Component Tests

#### Test Font Resolution
```python
python -c "
from agent.utils import resolve_font
bold = resolve_font(bold=True)
regular = resolve_font(bold=False)
print(f'Bold: {bold}')
print(f'Regular: {regular}')
"
```

#### Test Config Loading
```python
python -c "
from agent.utils import load_config
cfg = load_config('config/scenario.yaml')
print(f\"Browser URL: {cfg['browser']['base_url']}\")
print(f\"Scenario: {cfg['trouble']['scenario']}\")
"
```

#### Test SSH Connectivity
```bash
ssh ubuntu@43.203.137.253 "ls /home/whatap/app/chaos/trouble/05_downstream_delay/"
# Should show: start.sh  stop.sh
```

---

## 📝 Development Workflow

### Making Changes

#### 1. Update Scene Flow
Edit `agent/orchestrator.py`:
```python
# Add new scene at line 260
with Timer("Scene: custom_action"):
    log.info("Scene X: Custom action")
    await self._run_scene("custom_action", self.browser.custom_method())
```

Update `config/scenario.yaml`:
```yaml
scenes:
  # ... existing scenes ...
  - id: custom_action
    caption: "Step X. Custom Action Description"
    post_speed: 1.0  # Optional speed multiplier
```

#### 2. Add Browser Interaction
Edit `agent/browser_auto.py`:
```python
async def custom_method(self):
    """Custom browser interaction."""
    log.info("Performing custom action")
    await self.page.goto(f"{self.base_url}/custom/path")
    await asyncio.sleep(2)
    # ... more interactions
```

#### 3. Change Trouble Scenario
Edit `config/scenario.yaml`:
```yaml
trouble:
  scenario: "01_cpu_spike"  # Change from 05_downstream_delay
  port: 8081                 # Update port if needed
  params: ["80", "60"]       # Scenario-specific params
```

#### 4. Customize Post-Processing
Edit `agent/post_processor.py`:
```python
# Change intro text (line 35)
t1 = escape_ffmpeg_text("My Custom Title")
t2 = escape_ffmpeg_text("My Custom Subtitle")

# Change outro lines (line 59)
lines = cfg.get("lines", [
    "My Company",
    "Product Demo",
    "contact@example.com"
])
```

### Testing Changes

```bash
# 1. Syntax check
source .venv/bin/activate
python -m py_compile agent/orchestrator.py

# 2. Dry run
python run.py --dry-run

# 3. Fast test (no post-processing)
python run.py --skip-trouble --skip-postprocess --force

# 4. Full test
python run.py --skip-trouble --force

# 5. Check output
ls -lh output/aiops_demo_final.mp4
```

### Code Style

- **Async/await:** All I/O operations are async
- **Logging:** Use module-level logger: `log = logging.getLogger(__name__)`
- **Error handling:** Try/except with screenshot on failure
- **Type hints:** Use Python 3.10+ union syntax (`str | None`)
- **Docstrings:** All public methods have docstrings

---

## 📂 File Locations Reference

### Source Files
```
agent/orchestrator.py:127    # Main run() entry point
agent/orchestrator.py:193    # Scene execution flow
agent/browser_auto.py:79     # Login method
agent/browser_auto.py:207    # AI response polling
agent/trouble_runner.py:41   # Trouble start
agent/post_processor.py:180  # Post-processing pipeline
```

### Configuration
```
config/scenario.yaml         # Active configuration
config/scenario_osx.yaml     # macOS template
run.py:17                    # CLI argument parser
```

### Output Locations
```
output/aiops_demo_final.mp4           # Final video
output/temp/raw_recording.webm        # Browser capture
output/temp/pw_video/*.webm           # Playwright video
output/temp/screenshots/*.png         # Error screenshots
output/temp/*_raw.mp4                 # Scene extracts
output/temp/*_captioned.mp4           # With captions (if working)
output/temp/00_intro.mp4              # Intro card
output/temp/99_outro.mp4              # Outro card
```

---

## 🔍 Debugging Tips

### Enable Maximum Verbosity
```bash
export DEBUG=pw:*  # Playwright debug
python run.py --skip-trouble --force --verbose
```

### Inspect Scene Timing
Add temporary logging:
```python
# In orchestrator.py after line 186
log.info(f"Scene {scene_id}: {self.scene_markers}")
```

### Check Playwright Video
If post-processing fails, raw video is still captured:
```bash
ls -lh output/temp/pw_video/*.webm
# Copy to mp4 manually:
ffmpeg -i output/temp/pw_video/*.webm test.mp4
open test.mp4
```

### Screenshot Debugging
```python
# In browser_auto.py, add screenshots anywhere:
await self.page.screenshot(path=f"{self._screenshot_dir}/debug.png")
```

### Slow Down Execution
```python
# In browser_auto.py after each action:
await asyncio.sleep(2)  # Give time to observe
```

---

## 📦 Deployment Checklist

Before deploying to a new machine:

- [ ] Python 3.12+ installed
- [ ] ffmpeg installed
- [ ] CJK fonts available
- [ ] Config file updated for environment
- [ ] SSH keys configured (if using remote trouble)
- [ ] Web service accessible
- [ ] Output directory writable
- [ ] Test with `--dry-run` first
- [ ] Test with `--skip-trouble --force`
- [ ] Verify final video plays correctly

---

## 🆘 Getting Help

### Check Logs
```bash
# Run with verbose mode
python run.py --skip-trouble --force --verbose 2>&1 | tee debug.log

# Check for specific errors
grep ERROR debug.log
grep WARNING debug.log
```

### Check Documentation
1. **PROJECT.md** - Architecture, status, known issues
2. **TRANSFER.md** - Platform-specific notes
3. **This file (DEVELOPMENT.md)** - Setup and workflow

### Common Log Patterns

**Success:**
```
[agent.orchestrator] INFO Demo video complete!
[agent.orchestrator] INFO Output: .../aiops_demo_final.mp4
```

**SSH Issue:**
```
[agent.orchestrator] ERROR [FAIL] trouble script not found (remote)
```
→ Use `--skip-trouble --force`

**Font Issue:**
```
[ffmpeg] WARNING caption (...) failed
```
→ Video still generated, just without captions

**Browser Issue:**
```
[agent.browser_auto] ERROR Could not find text input
Screenshot saved: error_type_query.png
```
→ Check `output/temp/screenshots/` for visual debugging

---

## 📊 Performance Tuning

### Reduce Recording Time
```yaml
# config/scenario.yaml
browser:
  apm_dashboard:
    wait_sec: 3  # Reduce from 8

scenes:
  - id: wait_response
    post_speed: 3.0  # Speed up from 2.0 (faster playback)
```

### Reduce Output Size
```yaml
# config/scenario.yaml
post_process:
  crf: 28  # Increase from 22 (lower quality, smaller file)
  fps: 24  # Reduce from 30
```

### Skip Heavy Processing
```bash
# Skip intro/outro generation
python run.py --skip-trouble --skip-postprocess --force
# Then manually process raw_recording.webm
```

---

## 🎯 Next Session Checklist

When resuming work in a new session:

1. ✅ Read `PROJECT.md` first (current status)
2. ✅ Check `config/scenario.yaml` (configuration)
3. ✅ Run `python run.py --dry-run` (verify environment)
4. ✅ Review `output/aiops_demo_final.mp4` (last output)
5. ✅ Check git status (if versioned)
6. ✅ Review TODOs in `PROJECT.md` (what to work on)

**Session handoff information:**
- **Last successful run:** 2026-03-13 08:27 (FULL PIPELINE!)
- **Current blockers:** Caption rendering only
- **Next priority:** Fix font escaping in post_processor.py
- **Environment:** macOS, Python 3.12.13, ffmpeg 8.0.1, SSH configured

---

**Happy Developing! 🚀**

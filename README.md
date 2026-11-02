# OG Studio Video

Create music-video storyboards and bring them to life with VideoExpress.

[Download OG Studio Video for Windows](https://github.com/ogchriscagle-cmd/OG-Studio-Video/releases/latest)

- `app.py` - Tkinter GUI
- `videoexpress_automation.py` - Playwright automation driving app.videoexpress.ai
- `storyboard.py`, `analyze.py` - storyboard generation/analysis helpers
- `output/`, `gemini_output/` - example storyboard data

## Setup
pip install -r requirements.txt
playwright install chromium

Not included: `.venv`, `videoexpress_auth_state.json` (your own login session, generated on first run), build artifacts.

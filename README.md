# Music Video Storyboard -> VideoExpress Automation

Windows users can extract the GitHub release ZIP and run `OG Studio.exe` without
installing Python. See [release instructions](RELEASE-NOTES.md). Developers can
build the same ZIP with `powershell -ExecutionPolicy Bypass -File "Build Windows Release.ps1"`
after installing the project requirements in `.venv`.

- `app.py` - Tkinter GUI
- `videoexpress_automation.py` - Playwright automation driving app.videoexpress.ai
- `storyboard.py`, `analyze.py` - storyboard generation/analysis helpers
- `output/`, `gemini_output/` - example storyboard data

## Setup
Use Python with Tkinter installed (included with the standard Windows Python installer).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python videoexpress_automation.py login
python studio_app.py
```

Login once before uploading or generating scenes. Batch failures appear in the
desktop app and are recorded in `videoexpress_run_log.json`. Successfully
submitted scenes may continue rendering even if other scenes fail. The command
line supports `--start-scene` and `--end-scene` to retry a specific range.

## OG Studio desktop interface

Run `Launch OG Studio.cmd` or `python studio_app.py`. The new HTML/CSS interface
runs in a local desktop window using pywebview and Microsoft's WebView2 runtime.
The original Tkinter interface remains available with `python app.py`.

Choose a track and portrait, enter a project title and character description,
pick a style, and create a storyboard. Edit and save each scene's image and
motion prompts. Export writes JSON and Markdown to a folder you choose.
Imported clips preview against the selected song; scenes without footage show
their prompt text. Preview plays song audio and mutes imported clip audio.
The app uses template-based scene prompts, not lyric transcription. Save prompt
edits before exporting or generating.

Selecting a reference photo automatically drafts clothing, hair, and accessory
details with the local Salesforce BLIP vision model. First use downloads model
weights into `.models/`; the photo is processed locally and is not uploaded for
analysis. Review the result because vision models can miss or invent details.
The draft stays editable. If you type while it is processing, your text is kept
and the new draft is offered separately. **Draft appearance again** retries the
selected photo. A draft failure keeps your photo and allows manual entry.

Analysis stays on your computer. **Upload project media** sends the chosen song
and portrait to VideoExpress only after confirmation. Generation uses your
VideoExpress account credits. Sign-in opens a separate browser window.
Bundled Chromium launch errors can fall back to installed Google Chrome.

The workspace saves automatically and reopens on the next launch, including
your form settings, prompt drafts, media references, clip assignments, scroll
position, and paused preview position. Closing captures your latest edits.
Interrupted operations do not restart automatically; check tracking before
retrying a generation.

Use **Save project** to create a named `.ogstudio.json` project file. Changes
then save to that project as well as the recovery session. **Open / import**
opens either a project file or an exported `storyboard.json` without running
audio analysis again. **Export storyboard** writes the JSON storyboard,
Markdown prompts, and clip-tracking file to a folder; it does not export a
finished video or a complete project. Save scene prompt edits before exporting.

Project files reference your original media instead of copying it. Keep those
files in their original locations; missing files are reported while the
storyboard remains available. Local files are served only on a temporary
loopback port for playback. The recovery file is `.studio-session.json`.

## Generate and assemble

Build a new storyboard before generation. Shots use whole-second durations
between 3 and 10 seconds and cover the full song. Section boundaries round to
seconds; the video may extend less than one second past the song. Audio shorter
than three seconds requires a three-second clip. Trim the tail during export.

Use **Test First Scene** before running the full storyboard. Accepted job UUIDs
are checkpointed beside `storyboard.json` in `storyboard.clips.json`. Later runs
skip submitted or matched scenes, so a full run after a test does not duplicate
scene 1. A lost submission response is marked **submission unknown** and is not
retried automatically; review that scene in VideoExpress before taking action.

Every scene card also has **Generate scene** for working one scene at a time.
It saves that card's current image and motion prompts, then submits only that
scene. Set the project title, reference image library name, and frame ratio
before using it. Identical tracked jobs are skipped; changing prompts creates
a new generation after confirmation. Other scenes are left alone.

Click **Refresh rendered clips** to read render status and match each job to its
exact media asset identity. **Assemble tracked clips** becomes available when
every scene has a unique confirmed clip. It uses storyboard order, never upload
order or newest-clip guesses. Keep one song in the project folder and start
assembly with an empty editor timeline. Manual asset IDs remain available under
advanced settings for media generated outside OG Studio.

Each scene also has **Auto-import clip ↓**. Once its VideoExpress match is ready,
click it to download the exact rendered video into `clips/` beneath your output
folder and attach it to the local scene preview. Then click **Preview** or play
the song in the director's monitor. Auto-import uses your saved VideoExpress
session and never starts another generation. **Import clip** still lets you
choose a local file manually.

**Auto-import all clips** in Bring it to life downloads and attaches all ready,
matched scenes in storyboard order. The bottom status bar shows progress.
Existing imports are skipped, including manually chosen clips, and successful
downloads are kept if another clip fails. Click again to retry remaining clips.

After assembly, **View in VideoExpress** opens the saved `<project title> - Final
Video` project in a separate browser window. Review the timeline with Play,
then use VideoExpress's Export Video button to render the final file. Studio
does not start playback or export automatically. The review window stays open
until you close it. Duplicate project names are reported instead of guessing.

The final **Export & download video** step renders the saved VideoExpress final
project as MP4 at your chosen resolution and quality, then downloads the exact
new output to a folder you select. Confirm the export after reviewing the
timeline. Rendering uses your VideoExpress account allowance. The status bar
shows rendering and download progress; **Open downloaded video** plays the MP4.
If the app closes or a download fails, click the export button again with the
same settings to resume checking/downloading the saved request. An uncertain
submission is never automatically submitted twice. A completed export followed
by another confirmed export creates a new version. Pending exports and download
locations are included in project saves and session recovery.

Prompt edits invalidate that scene's saved match. Changing the generation
folder, reference, or aspect starts a new tracking configuration. Keep the
tracking JSON with its storyboard. Export copies both files. Existing clips
generated before tracking was added require manual asset IDs.

Not included: `.venv`, `videoexpress_auth_state.json` (your own login session, generated on first run), build artifacts.

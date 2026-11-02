# OG Studio Video v1.7.1 for Windows

## v1.7.1: Sign in from either studio

Social Clip Studio now includes the same VideoExpress account card as Music
video studio. Sign in & remember, reconnect, or check the saved connection
without switching tabs. Both studios share one saved account. Missing-session
errors point to the account card.

## New: Social Clip Studio

A separate sidebar workspace creates vertical promotional clips from a finished
video or a song + prompt. Start with 30 seconds, adjust framing, add an opening
hook and a closing follow/subscribe message, then export a 1080×1920 MP4 for
YouTube Shorts, Instagram/Facebook Reels, or TikTok. Choose the segment manually.

Finished-video trimming and MP4 export run locally. Song-based scene generation
uses your VideoExpress account credits, with optional character reference,
separate scene tracking, and automatic import/assembly of ready clips. Review
the plan before generating. Social settings and media are saved with projects
and restored after reopening. Posting to your accounts is manual.

Create a music-video storyboard, keep a consistent character, generate scenes in
VideoExpress, import clips, assemble the final project, and export its MP4.

## Install

1. Download `OG-Studio-Video-v1.7.1-windows-x64.exe` from this release.
2. Open the EXE. Python and a separate `_internal` folder are not required.
3. Wait for the bundled files to unpack and the app to open. Startup can take a minute.
4. Use the VideoExpress account card to sign in once on your computer.

This release retains the single-file packaging introduced in v1.2.1. Windows
internet-zone markings on ZIP-extracted .NET DLLs could prevent the old build
from opening. The single-file EXE extracts its dependencies at launch without changing
Windows security settings. Existing project data in `%LOCALAPPDATA%\OG Studio`
is kept. You do not need to copy or unblock individual DLLs.

Windows 10/11, 64-bit, with Microsoft Edge WebView2 Runtime and Google Chrome
installed. Appearance drafting downloads its local AI model on first use;
allow additional disk space and time for that download.

Projects, recovery data, downloaded appearance models, and saved VideoExpress
sign-in are stored in `%LOCALAPPDATA%\OG Studio`. Keep your original song,
reference photo, and imported clips available when reopening saved projects.

## Included

- Dark OG Studio Video desktop interface and storyboard preview.
- Automatic appearance draft from a reference photo.
- Save/open project and recovery after restarting.
- Saved VideoExpress sign-in and connection check.
- Generate one scene or all scenes, with clip tracking and auto-import.
- Open the assembled final project in VideoExpress.
- MP4 export and download with byte progress and a progress bar.
- Resume pending exports without submitting duplicate renders.

The download contains no personal projects, songs, photos, account cookies, or
API keys. VideoExpress generation and rendering use your own account allowances.
This build is unsigned; Windows may ask you to confirm its publisher.

## Toolbar updates

Use **Check updates** in the top toolbar. If a newer Windows release is available,
the button changes to **Download v…**. Choose a folder and watch download progress
at the bottom. GitHub's SHA-256 digest and file size are verified before the EXE is
saved. Close the running app and open the new EXE yourself; existing user data is
kept. **Show downloaded update** opens the download folder.

When GitHub requires account access, the updater can reuse an existing GitHub credential
from Git Credential Manager when Git is installed, without prompting or saving a
new token. Otherwise use **GitHub releases** to sign in and download in your
browser. No GitHub account credentials are sent to the asset CDN.

## v1.3.1 HTTPS hotfix

Includes the certificate policy file required by the Python runtime used to
build the Windows EXE. Its absence caused packaged HTTPS requests to fail before
GitHub could respond, despite development-mode checks working. Updates now retry
temporary connection failures and report clearer connection errors. Publication
is gated on a live GitHub check performed by the final packaged EXE.

## Startup splash

A native OG Studio Video splash opens while the single-file EXE unpacks, before Python
starts. It shows unpacking activity, a stage-based progress bar, and elapsed
seconds. Stages cover loading studio tools, restoring the workspace, and opening
the main window. It closes when the desktop connection is ready. Startup progress
is based on files and completed stages, not an estimated time remaining. Audio
analysis libraries now load when creating a storyboard instead of at launch.

## Custom OG app icon

The Windows EXE, main window, and taskbar now use a custom dark-and-lime OG
monogram. The ICO includes sizes from 16 to 256 pixels for crisp display in
File Explorer and the taskbar. A dedicated application identity separates the
studio from other Python applications in the taskbar.

## Expanded creative direction

Shape the world now offers nine visual styles: Cinematic, Neon noir, Dreamscape,
Vintage film, Horror, Anime, Watercolor, Cyberpunk, and Live stage. Choose mood,
lighting, location, and camera movement, with a live summary of your direction.

Create a storyboard to apply the choices to every scene. Explicit mood, lighting,
and camera choices replace automatic defaults in image/motion prompts. Location
choices adapt the scene actions to your setting. Follow song preserves automatic
variation based on track energy. The controls save with projects and exported
storyboard JSON files; older projects continue to open with automatic defaults.

## OG Studio Video rebrand

The app window, splash, sidebar, launcher, and Windows EXE now use the name
**OG Studio Video**. The repository is renamed to **ogchriscagle-cmd/OG-Studio-Video**.
The updater uses the stable GitHub repository ID and supports both old and new
asset names. Existing links redirect through GitHub. Older installed versions
will offer the releases-page fallback for this one-time renamed download.

Your data remains in `%LOCALAPPDATA%\OG Studio` so existing projects, clips,
recovery state, and VideoExpress sign-in remain available.

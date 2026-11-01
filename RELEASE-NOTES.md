# OG Studio v1.3.0 for Windows

Create a music-video storyboard, keep a consistent character, generate scenes in
VideoExpress, import clips, assemble the final project, and export its MP4.

## Install

1. Download `OG-Studio-v1.3.0-windows-x64.exe` from this release.
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

- Dark OG Studio desktop interface and storyboard preview.
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

This repository is private. The updater can reuse an existing GitHub credential
from Git Credential Manager when Git is installed, without prompting or saving a
new token. Otherwise use **GitHub releases** to sign in and download in your
browser. No GitHub account credentials are sent to the asset CDN.

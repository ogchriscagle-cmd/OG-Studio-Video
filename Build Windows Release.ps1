$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements.txt first.' }
& $python -m pip install 'pyinstaller==6.22.3'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
& $python -m PyInstaller --noconfirm MusicVideoStoryboard.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
Copy-Item -LiteralPath 'RELEASE-NOTES.md' -Destination 'dist\README.md' -Force
& $python package_release.py
if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }

"""Audit the single-file release and generate its SHA-256 checksum."""
import hashlib
import ssl
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader
from app_version import VERSION, RELEASE_PREFIX

root = Path(__file__).resolve().parent
destination = root / "dist" / f"{RELEASE_PREFIX}-v{VERSION}-windows-x64.exe"
if not destination.is_file():
    raise SystemExit("Build the single-file Windows executable first.")
archive = CArchiveReader(str(destination))
if not any(record[-1] == 'l' for record in archive.toc.values()):
    raise SystemExit("The executable is missing its early startup splash resource.")
ssl_policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if ssl_policy.is_file() and 'codex-rejected-cas.pem' not in archive.toc:
    raise SystemExit("The executable is missing the Python HTTPS certificate policy file.")
blocked = {"videoexpress_auth_state.json", ".studio-session.json", "videoexpress_run_log.json"}
for name in archive.toc:
    relative = Path(name)
    if relative.name in blocked or any(part in {".models", "output", "debug", ".git"} for part in relative.parts[:2]):
        raise SystemExit(f"Private runtime data must not be packaged: {name}")
if not any(name.replace(chr(92), '/') == 'studio/index.html' for name in archive.toc):
    raise SystemExit("The executable is missing the studio interface.")
if not any(name.replace(chr(92), '/') == 'studio/social.js' for name in archive.toc):
    raise SystemExit("The executable is missing Social Clip Studio.")
if not any('imageio_ffmpeg/binaries/ffmpeg' in name.replace(chr(92), '/') and name.endswith('.exe') for name in archive.toc):
    raise SystemExit("The executable is missing the local social-video encoder.")
with destination.open("rb") as content:
    digest = hashlib.file_digest(content, "sha256").hexdigest()
destination.with_suffix(".exe.sha256").write_text(f"{digest}  {destination.name}" + chr(10), encoding="utf-8")
print(f"Audited {destination.name} ({destination.stat().st_size / 1024**2:.1f} MB)")

"""Package only the clean PyInstaller distribution, never workspace data."""
import hashlib
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
distribution = root / "dist" / "OG Studio"
destination = root / "dist" / "OG-Studio-v1.2-windows-x64.zip"
if not (distribution / "OG Studio.exe").is_file():
    raise SystemExit("Build OG Studio.exe first.")
blocked = {"videoexpress_auth_state.json", ".studio-session.json", "videoexpress_run_log.json"}
files = sorted(path for path in distribution.rglob("*") if path.is_file())
for path in files:
    relative = path.relative_to(distribution)
    if path.name in blocked or any(part in {".models", "output", "debug", ".git"} for part in relative.parts[:2]):
        raise SystemExit(f"Private runtime data must not be packaged: {relative}")
with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in files:
        archive.write(path, path.relative_to(distribution.parent))
digest = hashlib.file_digest(destination.open("rb"), "sha256").hexdigest()
destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
print(f"Created {destination.name} ({destination.stat().st_size / 1024**2:.1f} MB)")

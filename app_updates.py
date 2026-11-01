"""Read GitHub releases and download verified updates without replacing a running EXE."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse, urljoin

import requests
from app_version import VERSION

RELEASES_URL = "https://github.com/ogchriscagle-cmd/video/releases"
API = "https://api.github.com/repos/ogchriscagle-cmd/video"


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not match:
        raise ValueError("Unsupported release version.")
    return tuple(int(v or 0) for v in match.groups())


def github_token():
    """Use existing Git credentials only; never prompt, save, or expose a token."""
    git = shutil.which("git")
    if not git:
        return None
    try:
        result = subprocess.run([git, "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
            text=True, capture_output=True, timeout=15,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        return values.get("password") if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def api_headers(token=None, binary=False):
    headers = {"Accept": "application/octet-stream" if binary else "application/vnd.github+json",
               "User-Agent": "OG-Studio-Updater/" + VERSION}
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def check_update():
    try:
        with requests.Session() as session:
            response = session.get(API + "/releases/latest", headers=api_headers(), timeout=(10, 30))
            if response.status_code in (401, 403, 404):
                token = github_token()
                if token:
                    response = session.get(API + "/releases/latest", headers=api_headers(token), timeout=(10, 30))
                if response.status_code in (401, 403, 404):
                    return dict(status="needs_access", current=VERSION)
            response.raise_for_status()
            release = response.json()
            version = release["tag_name"]
            if release.get("draft") or release.get("prerelease"):
                raise ValueError("No stable release available.")
            if version_tuple(version) <= version_tuple(VERSION):
                return dict(status="current", current=VERSION, latest=version)
            name = f"OG-Studio-{version if version.startswith('v') else 'v'+version}-windows-x64.exe"
            assets = {a["name"]: a for a in release.get("assets", []) if a.get("state") == "uploaded"}
            asset = assets.get(name)
            if not asset or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", asset.get("digest") or ""):
                return dict(status="manual", current=VERSION, latest=version)
            if asset.get("url") != API + "/releases/assets/" + str(asset["id"]):
                raise ValueError("Unexpected update asset URL.")
            return dict(status="available", current=VERSION, latest=version, name=name,
                        asset_id=int(asset["id"]), sha256=asset["digest"][7:].lower(), size=int(asset["size"]))
    except (requests.RequestException, ValueError, KeyError, TypeError):
        raise RuntimeError("Could not check GitHub releases. Try again later or use Open releases.") from None


def download_update(info, folder, progress):
    if info.get("status") != "available":
        raise RuntimeError("Check for updates before downloading.")
    version_tuple(info['latest'])
    expected_name = f"OG-Studio-v{info['latest'].removeprefix('v')}-windows-x64.exe"
    if info["name"] != expected_name or not re.fullmatch(r"[0-9a-f]{64}", info["sha256"]):
        raise RuntimeError("Invalid update metadata. Check for updates again.")
    path = Path(folder) / info["name"]
    partial = path.with_suffix(".exe.part")
    token = github_token()
    url = API + "/releases/assets/" + str(int(info["asset_id"]))
    allowed = {"api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
    try:
        with requests.Session() as session:
            for _ in range(6):
                host = urlparse(url)
                if host.scheme != "https" or host.hostname not in allowed or host.username or host.password:
                    raise RuntimeError("GitHub returned an unrecognized download address.")
                # Send account credentials only to the GitHub API, never to its CDN.
                response = session.get(url, headers=api_headers(token if host.hostname == "api.github.com" else None, True),
                                       stream=True, allow_redirects=False, timeout=(15, 60))
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers.get("location", ""))
                    response.close()
                    continue
                break
            else:
                raise RuntimeError("The GitHub download redirected too many times.")
            with response:
                response.raise_for_status()
                received = 0
                digest = hashlib.sha256()
                magic = b""
                progress(0, info["size"])
                with partial.open("wb") as content:
                    for chunk in response.iter_content(256 * 1024):
                        if not chunk:
                            continue
                        magic = (magic + chunk)[:2]
                        content.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        progress(received, info["size"])
                if received != info["size"] or digest.hexdigest() != info["sha256"] or magic != b"MZ":
                    raise RuntimeError("The update failed its integrity check. Download it again.")
                partial.replace(path)
                return str(path.resolve())
    except requests.RequestException:
        raise RuntimeError("The GitHub download was interrupted or needs account access. Retry or use Open releases.") from None
    finally:
        partial.unlink(missing_ok=True)

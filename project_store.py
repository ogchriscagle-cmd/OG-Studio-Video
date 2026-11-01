"""Plain JSON project files with atomic writes and explicit media references."""
import json
import math
import os
from pathlib import Path
import tempfile
import time


def write_project(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
    temporary = None
    try:
        # Each writer owns its file; a second app instance cannot truncate it.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                # Windows scanners and readers can briefly deny replacement.
                time.sleep(0.04 * 2 ** attempt)
    finally:
        if temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def read_project(path):
    path = Path(path)
    if path.stat().st_size > 30 * 1024 * 1024:
        raise ValueError("This project file is too large.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Choose an OG Studio project or an exported storyboard JSON file.")
    if data.get("format") == "og-studio-project":
        if data.get("version") != 1 or not isinstance(data.get("state"), dict):
            raise ValueError("This OG Studio project version is not supported.")
        board = data["state"].get("storyboard")
    else:
        board = data
        data = dict(format="storyboard-import", state=dict(storyboard=board), ui={})
    if board is not None:
        if not isinstance(board, dict) or not isinstance(board.get("scenes"), list) or not board["scenes"]:
            raise ValueError("The storyboard must contain scenes.")
        previous = 0
        for n, scene in enumerate(board["scenes"], 1):
            if not isinstance(scene, dict) or scene.get("scene_number") != n:
                raise ValueError("Scene numbers must run in order from 1.")
            for field in ("start", "end", "duration"):
                value = scene.get(field)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError("Scene timing must contain valid positive numbers.")
            if scene["start"] < previous or scene["end"] <= scene["start"] or scene["duration"] <= 0:
                raise ValueError("Scene timing must run forward without overlaps.")
            previous = scene["end"]
            if not isinstance(scene.get("video_prompt"), str):
                raise ValueError("Each scene needs a video prompt.")
            scene.setdefault("image_prompt", scene["video_prompt"])
            scene.setdefault("video_audio_prompt", scene["video_prompt"])
            scene.setdefault("section_label", "verse")
        board["scene_count"] = len(board["scenes"])
        board.setdefault("song_title", path.stem)
        board.setdefault("artist", "")
        board.setdefault("total_duration", previous)
        board.setdefault("tempo_bpm", 0)
        board.setdefault("key", "Unknown")
        for field in ("total_duration", "tempo_bpm"):
            if not isinstance(board[field], (int, float)) or not math.isfinite(board[field]) or board[field] < 0:
                raise ValueError("Song duration and tempo must be valid numbers.")
    return data

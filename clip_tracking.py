"""Durable scene-to-generation mappings. Never infer identity from clip order."""
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def scene_key(scene):
    return digest({k: scene.get(k) for k in (
        "scene_number", "start", "end", "duration", "image_prompt", "video_audio_prompt")})


def tracking_path(storyboard_path):
    path = Path(storyboard_path)
    return path.with_name(path.stem + ".clips.json")


def load_tracking(storyboard_path, board, config=None):
    identity = digest({k: board.get(k) for k in ("song_title", "artist", "total_duration", "scene_count", "source_audio", "source_audio_version")})
    path = tracking_path(storyboard_path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if data.get("project") != identity or (config is not None and data.get("config") != config):
        data = dict(version=1, project=identity, config=config or {}, scenes={})
    valid = {str(s["scene_number"]): scene_key(s) for s in board["scenes"]}
    data["scenes"] = {n: item for n, item in data.get("scenes", {}).items()
                      if n in valid and item.get("scene_key") == valid[n]}
    return data


def save_tracking(storyboard_path, data):
    path = tracking_path(storyboard_path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(path)


def ordered_asset_ids(board, data):
    ids = []
    for scene in board["scenes"]:
        item = data["scenes"].get(str(scene["scene_number"]), {})
        if item.get("scene_key") != scene_key(scene) or item.get("status") != "ready" or not str(item.get("asset_id", "")).isascii() or not str(item.get("asset_id", "")).isdecimal():
            raise ValueError(f"Scene {scene['scene_number']} has no confirmed rendered clip. Refresh clip tracking first.")
        ids.append(str(item["asset_id"]))
    if len(ids) != len(set(ids)):
        raise ValueError("Two scenes map to the same clip. Review the saved tracking file.")
    return ids


def match_asset(item, assets, completed_url=None):
    """Match an explicit generation UUID or an exact URL from its status response."""
    uuid = item.get("uuid")
    matches = []
    for asset in assets:
        if asset.get("type") != "video" or asset.get("isPending"):
            continue
        metadata = asset.get("data") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except ValueError:
                metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        uuid_match = uuid and uuid in (asset.get("uuid"), metadata.get("uuid"), metadata.get("videoUuid"))
        url_match = completed_url and completed_url in (asset.get("mediaPath"), asset.get("originalUrl"), asset.get("videoUrl"))
        if uuid_match or url_match:
            matches.append(asset)
    if len(matches) != 1:
        return None
    ident = str(matches[0].get("id", ""))
    return ident if ident.isascii() and ident.isdecimal() else None

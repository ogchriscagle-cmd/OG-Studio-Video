"""Social Clip Studio bridge methods; music-video projects stay independent."""
import copy
import os
from pathlib import Path
import re
import uuid

import webview

from clip_tracking import load_tracking, save_tracking
from storyboard import write_outputs
from runtime_paths import DATA_ROOT
from social_video import probe, clip_settings, trim_song, build_social_board, render_video, assemble_social
from videoexpress_automation import setup_project_folder, run_batch, refresh_clip_tracking, download_tracked_clip


class SocialStudio:
    def _social_directory(self, social=None):
        social = social if social is not None else self._state.get("social", {})
        ident = social.get("id", "")
        if not re.fullmatch(r"[0-9a-f]{32}", str(ident)):
            raise ValueError("Choose social media to start a clip first.")
        return DATA_ROOT / "output" / "social" / ident

    def _restore_social(self, saved, restore_media, references=None):
        social = copy.deepcopy(saved) if isinstance(saved, dict) else {}
        references = references or {}
        if not re.fullmatch(r"[0-9a-f]{32}", str(social.get("id", ""))):
            social["id"] = uuid.uuid4().hex
        for kind in ("video", "song", "photo", "generated", "export"):
            social[kind] = restore_media(social.get(kind) or references.get("social:"+kind), "social:" + kind)
        clips = {k.removeprefix("social:clip:"):v for k,v in references.items() if k.startswith("social:clip:")}
        clips.update(social.get("clips") or {})
        social["clips"] = {str(n): item for n, clip in clips.items()
                           if (item := restore_media(clip, "social:clip:" + str(n)))}
        if isinstance(social.get("board"), dict):
            directory = self._social_directory(social)
            # Paths are reconstructed inside the app workspace, not trusted from JSON.
            audio = directory / "song-excerpt.wav"
            social["board"]["source_audio"] = str(audio)
            directory.mkdir(parents=True, exist_ok=True)
            write_outputs(social["board"], str(directory))
            if isinstance(social.get("tracking"), dict):
                save_tracking(directory / "storyboard.json", social["tracking"])
        return social

    def choose_social_media(self, kind):
        if self.get_state()["busy"]:
            return {"error": "Wait for the current operation to finish."}
        filters = {"video": "Videos (*.mp4;*.mov;*.webm;*.mkv)",
                   "song": "Audio (*.mp3;*.wav;*.flac;*.m4a)", "photo": "Images (*.png;*.jpg;*.jpeg)"}
        if kind not in filters:
            return {"error": "Choose video, song, or reference photo."}
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=(filters[kind],))
        if not paths:
            return self.get_state()
        return self._select_social_file(kind, paths[0])

    def use_final_video_for_social(self):
        final = self.get_state().get("final_export") or {}
        if final.get("status") != "completed" or not Path(final.get("path", "")).is_file():
            return {"error": "Download your finished music video first, or choose a video file."}
        return self._select_social_file("video", final["path"])

    def _select_social_file(self, kind, path):
        path = str(Path(path).resolve())
        def work():
            info = {} if kind == "photo" else probe(path, video=kind == "video")
            with self._lock:
                social = self._state.setdefault("social", {})
                social.setdefault("id", uuid.uuid4().hex)
                item = dict(path=path, name=Path(path).name, url=self._register(path), **info)
                social[kind] = item
                if kind == "song":
                    # A new source needs a new prompt plan; old generated work stays on disk.
                    social.update(board=None, clips={}, generated=None, tracking=None)
                self._state["missing_media"] = [m for m in self._state["missing_media"] if m.get("role") != "social:"+kind]
            return f"Social Clip Studio · {Path(path).name} selected."
        return self._job("Opening social clip media…", work)

    def create_social_plan(self, settings, prompt, style="Cinematic"):
        social = copy.deepcopy(self.get_state().get("social") or {})
        song = social.get("song")
        if not song:
            return {"error": "Choose a song for your social clip first."}
        try:
            config = clip_settings(settings, probe(song["path"])["duration"])
            # Whole seconds match the generation duration controls.
            if config["duration"] != int(config["duration"]):
                raise ValueError("Use a whole number of seconds for song-generated clips.")
            board = build_social_board(song["path"], config["duration"], prompt, "Social clip", style)
        except (ValueError, OSError) as error:
            return {"error": str(error)}
        def work():
            social["id"] = uuid.uuid4().hex
            directory = self._social_directory(social)
            excerpt = trim_song(song["path"], directory / "song-excerpt.wav", config)
            board["source_audio"] = excerpt
            board["song_title"] = "OG Social " + social["id"][:10]
            write_outputs(board, str(directory))
            social.update(board=board, clips={}, generated=None, export=None, tracking=None, uploaded=False,
                          plan=dict(start=config["start"], duration=config["duration"], prompt=str(prompt), style=style,
                                    reference_path=(social.get("photo") or {}).get("path")))
            with self._lock:
                self._state["social"] = social
            return f"Social plan ready · {board['scene_count']} vertical scenes. Review prompts, then generate."
        return self._job("Preparing your song excerpt and vertical scene prompts…", work)

    def generate_social_scenes(self):
        social = copy.deepcopy(self.get_state().get("social") or {})
        board = social.get("board")
        if not board:
            return {"error": "Create a social prompt plan first."}
        if (social.get("photo") or {}).get("path") != social.get("plan", {}).get("reference_path"):
            return {"error": "Your character reference changed. Create a new social plan before generating."}
        directory = self._social_directory(social)
        if not Path(board["source_audio"]).is_file():
            return {"error": "The song excerpt is missing. Create a new social prompt plan."}
        def work():
            photo = social.get("photo") or {}
            if not social.get("uploaded"):
                setup_project_folder(board["song_title"], photo.get("path"), board["source_audio"])
                with self._lock:
                    self._state["social"]["uploaded"] = True
                    self._checkpoint()
            reference = Path(photo["path"]).stem if photo else ""
            run_batch(directory / "storyboard.json", reference, "9:16", folder_name=board["song_title"])
            return "Social scenes submitted. Refresh & import when VideoExpress finishes rendering. Tracked scenes are skipped on retries."
        return self._job("Generating vertical social scenes in VideoExpress…", work)

    def refresh_social_clips(self):
        social = copy.deepcopy(self.get_state().get("social") or {})
        board = social.get("board")
        if not board:
            return {"error": "Create a social prompt plan first."}
        directory = self._social_directory(social)
        def work():
            tracking = refresh_clip_tracking(directory / "storyboard.json")
            for scene in board["scenes"]:
                n = str(scene["scene_number"])
                entry = tracking["scenes"].get(n, {})
                if entry.get("status") != "ready":
                    continue
                current = social["clips"].get(n) or {}
                if current.get("asset_id") == str(entry["asset_id"]) and Path(current.get("path", "")).is_file():
                    continue
                with self._lock:
                    self._state["status"] = f"Downloading social scene {n} of {board['scene_count']}…"
                path = download_tracked_clip(entry["asset_id"], directory / "clips" / f"scene-{n}-{entry['asset_id']}")
                with self._lock:
                    social["clips"][n] = dict(path=path, name=Path(path).name, url=self._register(path), asset_id=str(entry["asset_id"]))
                    self._state["social"] = copy.deepcopy(social)
                    self._checkpoint()
            count = len(social["clips"])
            if count == board["scene_count"]:
                source = directory / "social-source.mp4"
                if not (social.get("generated") and source.is_file()):
                    def progress(percent):
                        with self._lock:
                            self._state.update(status=f"Combining social scenes with your song · {percent:.0f}%…", download_percent=percent)
                    assemble_social(social["clips"], board, source, progress)
                    with self._lock:
                        social["generated"] = dict(path=str(source), name=source.name, url=self._register(source),
                                                   duration=board["total_duration"], width=1080, height=1920)
                        self._state["social"] = social
                return "Social video ready. Preview it, add your hook and follow message, then export MP4."
            return f"{count} / {board['scene_count']} social clips imported. Refresh again when the remaining renders are ready."
        return self._job("Checking and importing your social scene renders…", work)

    def export_social_video(self, settings):
        if self.get_state()["busy"]:
            return {"error": "Wait for the current operation to finish."}
        social = copy.deepcopy(self.get_state().get("social") or {})
        settings = dict(settings)
        source = social.get("generated" if settings.get("mode") == "song" else "video")
        if not source:
            return {"error": "Choose a finished video or finish generating your social scenes first."}
        if settings.get("mode") == "song":
            settings.update(start=0, duration=social["board"]["total_duration"])
        try:
            config = clip_settings(settings, probe(source["path"])["duration"])
        except (ValueError, OSError) as error:
            return {"error": str(error)}
        name = re.sub(r"[^\w -]", "", Path(source["name"]).stem)[:70] or "Social clip"
        paths = self._window.create_file_dialog(webview.FileDialog.SAVE,
            save_filename=f"{name} - {config['platform']}.mp4", file_types=("MP4 video (*.mp4)",))
        if not paths:
            return self.get_state()
        target = Path(paths if isinstance(paths, str) else paths[0]).with_suffix(".mp4")
        def work():
            def progress(percent):
                with self._lock:
                    self._state.update(status=f"Exporting {config['platform']} clip · {percent:.0f}%…", download_percent=percent)
            path = render_video(source["path"], target, config, progress)
            with self._lock:
                self._state["social"]["export"] = dict(path=path, name=Path(path).name, url=self._register(path),
                                                        platform=config["platform"], duration=config["duration"])
            return f"Social clip saved · {path}"
        return self._job("Rendering your vertical social clip locally…", work)

    def open_social_export(self):
        item = (self.get_state().get("social") or {}).get("export") or {}
        path = Path(item.get("path", ""))
        if not path.is_file() or path.suffix.lower() != ".mp4":
            return {"error": "Export a social MP4 first."}
        os.startfile(str(path.resolve()))
        return self.get_state()

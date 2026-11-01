"""OG Studio desktop shell. Python work runs outside the UI thread."""
import copy
import json
import mimetypes
import os
import re
from pathlib import Path
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import webview

from analyze import analyze_song
from storyboard import build_storyboard, write_outputs
from videoexpress_automation import do_login, setup_project_folder, run_batch, assemble_final_video, refresh_clip_tracking, download_tracked_clip, view_final_project
from clip_tracking import load_tracking, ordered_asset_ids, tracking_path, save_tracking
from appearance import describe_appearance
from project_store import read_project, write_project
from final_export import export_and_download
from videoexpress_automation import AUTH_STATE_PATH, check_saved_session
from runtime_paths import ASSET_ROOT, DATA_ROOT

ROOT = DATA_ROOT


def safe_error(error):
    """Playwright call logs can contain authenticated request headers."""
    message = str(error).split("Call log:", 1)[0].strip()
    return re.sub(r"(?im)^.*(?:cookie|authorization)\s*:.*$", "[Sensitive request header removed]", message)


STYLES = {
    "Cinematic": "cinematic realism, rich natural lighting, subtle film grain",
    "Neon noir": "neon noir, rain-slick streets, electric lime and violet lighting",
    "Dreamscape": "surreal dreamscape, soft diffused light, ethereal atmosphere",
}


class StudioAPI:
    def __init__(self, session_path=None):
        self._window = None
        self._lock = threading.RLock()
        self._media = {}
        self._out_dir = ROOT / "output"
        self._session_path = Path(session_path) if session_path else None
        self._project_path = None
        self._project_id = uuid.uuid4().hex
        self._closing = False
        self._allow_close = False
        self._state = dict(busy=False, status="Ready. Bring your track.", error=None,
                          audio=None, photo=None, storyboard=None, clips={}, analysis=None, options={}, appearance_draft=None, appearance_error=None,
                          ui={}, workspace_revision=uuid.uuid4().hex, missing_media=[], save_error=None, final_export=None)
        if self._session_path and self._session_path.exists():
            try:
                self._restore(self._session_path, recovery=True)
            except Exception as error:
                self._state.update(error=f"Could not restore the previous session: {error}", status="Previous session could not be restored. Open a saved project to recover it.")

    def _snapshot(self):
        state = self.get_state()
        for media in [state.get("audio"), state.get("photo"), *state.get("clips", {}).values()]:
            if media:
                media.pop("url", None)
        return dict(format="og-studio-project", version=1, project_id=self._project_id,
                    project_path=str(self._project_path) if self._project_path else None,
                    state=state, ui=state.get("ui", {}))

    def _checkpoint(self):
        if not self._session_path and not self._project_path:
            return
        with self._lock:
            data = self._snapshot()
            try:
                if self._session_path:
                    write_project(self._session_path, data)
                if self._project_path:
                    write_project(self._project_path, data)
                self._state["save_error"] = None
            except Exception as error:
                self._state["save_error"] = f"Latest changes could not be saved. Autosave will retry. {error}"
                raise

    def update_workspace(self, ui):
        if not isinstance(ui, dict):
            return {"error": "Invalid workspace settings."}
        with self._lock:
            self._state["ui"] = copy.deepcopy(ui)
            try:
                self._checkpoint()
            except Exception as error:
                return {"error": safe_error(error)}
        return {"saved": True}

    def save_project(self):
        paths = self._window.create_file_dialog(webview.FileDialog.SAVE,
            save_filename="My project.ogstudio.json", file_types=("OG Studio project (*.ogstudio.json)",))
        if not paths:
            return self.get_state()
        path = Path(paths if isinstance(paths, str) else paths[0])
        if not path.name.endswith(".ogstudio.json"):
            path = path.with_name(path.name + ".ogstudio.json")
        with self._lock:
            self._project_path = path.resolve()
            try:
                self._checkpoint()
            except Exception as error:
                return {"error": safe_error(error)}
            self._state["status"] = f"Project saved · {path.name}. Changes will be saved automatically."
        return self.get_state()

    def open_project(self):
        with self._lock:
            if self._state["busy"]:
                return {"error": "Wait for the current operation to finish before opening a project."}
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN,
            file_types=("OG Studio projects and storyboards (*.json)",))
        if not paths:
            return self.get_state()
        try:
            with self._lock:
                self._checkpoint()
                self._restore(Path(paths[0]))
                self._checkpoint()
        except Exception as error:
            return {"error": f"Could not open the project: {error}"}
        return self.get_state()

    def _restore(self, path, recovery=False):
        data = read_project(path)
        saved = data["state"]
        board = saved.get("storyboard")
        media_map, missing = {}, []
        def media(item, role):
            if not isinstance(item, dict) or not item.get("path"):
                return None
            local = Path(item["path"])
            if not local.is_absolute():
                local = path.parent / local
            local = local.resolve()
            if not local.is_file():
                missing.append(dict(role=role, path=str(local)))
                return None
            token = uuid.uuid4().hex
            media_map[token] = local
            restored = dict(path=str(local), name=local.name, url=f"/media/{token}")
            if item.get("asset_id"):
                restored["asset_id"] = str(item["asset_id"])
            return restored
        references = {m["role"]: dict(path=m["path"]) for m in saved.get("missing_media", []) if isinstance(m, dict) and "role" in m and "path" in m}
        audio = media(saved.get("audio") or references.get("audio") or (dict(path=board["source_audio"]) if board and board.get("source_audio") else None), "audio")
        photo = media(saved.get("photo") or references.get("photo"), "photo")
        clips = {}
        for n in ({**{k.removeprefix("clip:"):v for k,v in references.items() if k.startswith("clip:")}, **saved.get("clips", {})}):
            item = media(saved.get("clips", {}).get(n) or references.get(f"clip:{n}"), f"clip:{n}")
            if item:
                clips[n] = item
        project_id = data.get("project_id", "")
        if not isinstance(project_id, str) or len(project_id) != 32 or any(c not in "0123456789abcdef" for c in project_id):
            project_id = uuid.uuid4().hex
        work_dir = ROOT / "output" / "projects" / project_id
        if board:
            tracking = load_tracking(path, board) if data["format"] == "storyboard-import" else {"scenes": saved.get("tracking", {})}
            if data["format"] != "storyboard-import":
                tracking = {**load_tracking(work_dir / "storyboard.json", board), "scenes": saved.get("tracking", {})}
                tracking["config"] = data.get("tracking_config", saved.get("tracking_config", {}))
            work_dir.mkdir(parents=True, exist_ok=True)
            write_outputs(board, str(work_dir))
            save_tracking(work_dir / "storyboard.json", tracking)
        ui = data.get("ui") or saved.get("ui") or saved.get("options") or {}
        if not isinstance(ui, dict):
            raise ValueError("The project's workspace settings are invalid.")
        if board:
            ui.setdefault("title", board["song_title"])
            ui.setdefault("artist", board["artist"])
        status = "Previous workspace restored." if recovery else f"Opened {path.name}."
        if saved.get("busy"):
            status += " The previous operation was interrupted; check clip tracking before retrying."
        error = "Some media files are missing. Reselect them at their new locations:\n" + "\n".join(m["path"] for m in missing) if missing else None
        self._media, self._out_dir, self._project_id = media_map, work_dir, project_id
        self._project_path = Path(data["project_path"]) if recovery and data.get("project_path") else path if data["format"] == "og-studio-project" and not recovery else None
        self._state.update(busy=False, status=status, error=error, audio=audio, photo=photo, clips=clips,
                           storyboard=board, analysis=saved.get("analysis") or (dict(duration=board["total_duration"], tempo=board["tempo_bpm"]) if board else None),
                           options=saved.get("options", {}), ui=ui, workspace_revision=uuid.uuid4().hex,
                           appearance_draft=None, appearance_error=None, missing_media=missing, save_error=None,
                           final_export=saved.get("final_export") if isinstance(saved.get("final_export"), dict) else None)

    def _on_closing(self):
        if self._allow_close:
            return True
        if not self._closing:
            self._closing = True
            def finish():
                try:
                    result = self.update_workspace(self._window.evaluate_js("captureWorkspace()"))
                    if result.get("error"):
                        raise RuntimeError(result["error"])
                    self._checkpoint()
                except Exception as error:
                    with self._lock:
                        self._state.update(error=f"Could not save before closing: {error}", status="The app stayed open so your work is not lost.")
                        self._closing = False
                else:
                    self._allow_close = True
                    self._window.destroy()
            threading.Thread(target=finish, daemon=True).start()
        return False

    def get_state(self):
        with self._lock:
            state = copy.deepcopy(self._state)
            state["account"] = self._state.get("account", "saved" if AUTH_STATE_PATH.exists() else "missing")
            state["tracking"] = {}
            if state["storyboard"]:
                path = self._out_dir / "storyboard.json"
                tracking = load_tracking(path, state["storyboard"])
                state["tracking"] = tracking["scenes"]
                state["tracking_config"] = tracking["config"]
            return state

    def _register(self, path):
        ident = uuid.uuid4().hex
        self._media[ident] = Path(path)
        return f"/media/{ident}"

    def choose_media(self, kind, scene_number=None):
        with self._lock:
            if self._state["busy"]:
                return {"error": "Wait for the current operation to finish."}
        filters = {"audio": "Audio (*.mp3;*.wav;*.flac;*.m4a)",
                   "photo": "Images (*.png;*.jpg;*.jpeg)",
                   "clip": "Video (*.mp4;*.webm;*.mov)"}
        if kind not in filters:
            return {"error": "Unknown media type."}
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=(filters[kind],))
        if not paths:
            return self.get_state()
        path = str(Path(paths[0]).resolve())
        item = dict(path=path, name=Path(path).name, url=self._register(path))
        with self._lock:
            if kind == "clip":
                if not self._state["storyboard"] or not any(s["scene_number"] == scene_number for s in self._state["storyboard"]["scenes"]):
                    return {"error": "Choose an existing scene."}
                self._state["clips"][str(scene_number)] = item
            else:
                self._state[kind] = item
                if kind == "audio":
                    if not any(m.get("role") == "audio" for m in self._state["missing_media"]):
                        self._state.update(storyboard=None, analysis=None, clips={})
                        self._state["ui"].pop("scene_drafts", None)
                self._state["missing_media"] = [m for m in self._state["missing_media"] if m.get("role") != kind]
            self._state["error"] = None
            if kind == "photo":
                self._state["appearance_draft"] = None
            self._checkpoint()
        if kind == "photo":
            return self.draft_appearance()
        return self.get_state()

    def draft_appearance(self):
        with self._lock:
            if self._state["busy"]:
                return {"error": "Wait for the current operation to finish."}
            self._state["appearance_draft"] = None
            self._state["appearance_error"] = None
        photo = self.get_state()["photo"]
        if not photo:
            return {"error": "Choose a character reference image first."}
        def work():
            try:
                text = describe_appearance(photo["path"])
            except Exception as error:
                with self._lock:
                    self._state["appearance_error"] = safe_error(error)
                raise
            with self._lock:
                if self._state["photo"]["url"] == photo["url"]:
                    self._state["appearance_draft"] = dict(photo_url=photo["url"], text=text)
            return "Appearance drafted from your photo. Review and correct it before building scenes."
        return self._job("Drafting appearance locally… First use downloads the vision model; this may take several minutes.", work)

    def _job(self, label, function):
        with self._lock:
            if self._state["busy"]:
                return {"error": "An operation is already running."}
            self._state.update(busy=True, status=label, error=None)
            try:
                self._checkpoint()
            except Exception as error:
                self._state["busy"] = False
                self._state["status"] = "Operation not started because the workspace could not be saved."
                return {"error": safe_error(error)}
        def worker():
            try:
                result = function()
                with self._lock:
                    self._state["status"] = result or "Done."
            except Exception as error:
                with self._lock:
                    self._state.update(error=safe_error(error), status="Operation failed. Review the message below.")
            finally:
                with self._lock:
                    self._state["busy"] = False
                    try:
                        self._checkpoint()
                    except Exception:
                        pass  # Keep the save warning visible; the next autosave retries.
        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()
        return self.get_state()

    def analyze(self, options):
        options = dict(options)
        audio = self.get_state()["audio"]
        if not audio:
            return {"error": "Choose a song first."}
        def work():
            analysis = analyze_song(audio["path"])
            board = build_storyboard(analysis, options.get("artist"), options.get("title"))
            style = STYLES.get(options.get("style"), STYLES["Cinematic"])
            character = options.get("character", "").strip()
            appearance = options.get("appearance", "").strip()
            concept = options.get("concept", "").strip()
            direction = ", ".join(filter(None, [style, character, appearance, concept]))
            for scene in board["scenes"]:
                scene["image_prompt"] += ", " + direction
                scene["video_prompt"] += ", " + direction
            with self._lock:
                self._state.update(analysis=analysis, storyboard=board, clips={}, options=options)
                self._state["ui"].pop("scene_drafts", None)
            self._save()
            return f"Storyboard ready · {board['scene_count']} scenes. Review prompts before generating."
        return self._job("Listening to your track and planning scenes…", work)

    def _save(self):
        board = self.get_state()["storyboard"]
        if not board:
            raise ValueError("Build a storyboard first.")
        paths = write_outputs(board, str(self._out_dir))
        self._checkpoint()
        return paths

    def edit_scene(self, number, image_prompt, motion_prompt):
        with self._lock:
            if self._state["busy"]:
                return {"error": "Wait for the current operation to finish."}
            board = self._state["storyboard"]
            if not board:
                return {"error": "Build a storyboard first."}
            scene = next(s for s in board["scenes"] if s["scene_number"] == number)
            scene.update(image_prompt=image_prompt, video_audio_prompt=motion_prompt,
                         video_prompt=f"{image_prompt}, {motion_prompt}")
            self._save()
        return self.get_state()

    def export(self):
        paths = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not paths:
            return self.get_state()
        with self._lock:
            if self._state["busy"]:
                return {"error": "Wait for the current operation to finish."}
            try:
                old_tracking = tracking_path(self._out_dir / "storyboard.json")
                saved_tracking = old_tracking.read_text(encoding="utf-8") if old_tracking.exists() else None
                self._out_dir = Path(paths[0])
                self._save()
                if saved_tracking:
                    tracking_path(self._out_dir / "storyboard.json").write_text(saved_tracking, encoding="utf-8")
                self._state["status"] = f"Storyboard exported to {self._out_dir}"
            except Exception as error:
                return {"error": safe_error(error)}
        return self.get_state()

    def login(self):
        def work():
            do_login()
            with self._lock:
                self._state["account"] = "connected"
            return "VideoExpress sign-in saved on this computer. Future actions reuse it automatically."
        return self._job("Sign in to VideoExpress in the browser window…", work)

    def check_videoexpress_login(self):
        def work():
            status = check_saved_session()
            with self._lock:
                self._state["account"] = status
            return {"connected": "VideoExpress is connected. Your saved sign-in is ready.",
                    "missing": "Sign in once using the VideoExpress account card.",
                    "expired": "Your VideoExpress session expired. Sign in again using the account card.",
                    "unavailable": "Could not reach VideoExpress. Your saved sign-in has been kept; try checking again later."}[status]
        return self._job("Checking your saved VideoExpress sign-in…", work)

    def upload(self, title):
        state = self.get_state()
        if not title.strip() or not state["audio"] or not state["photo"]:
            return {"error": "Enter a project title and choose both your song and reference photo."}
        return self._job("Uploading project media to VideoExpress…", lambda: (
            setup_project_folder(title.strip(), state["photo"]["path"], state["audio"]["path"]), "Project media uploaded.")[1])

    def generate(self, title, reference_name, aspect, first_only):
        if not title.strip() or not reference_name.strip():
            return {"error": "Enter the project title and reference photo's library name."}
        if aspect not in ("16:9", "9:16"):
            return {"error": "Choose a supported aspect ratio."}
        def work():
            path, _ = self._save()
            run_batch(path, reference_name.strip(), aspect, folder_name=title.strip(),
                      end_scene=1 if first_only else None)
            return "Jobs saved to clip tracking. Refresh rendered clips when ready. Previously tracked scenes are skipped."
        return self._job("Submitting scenes to VideoExpress…", work)

    def refresh_tracking(self):
        def work():
            path, _ = self._save()
            tracking = refresh_clip_tracking(path)
            ready = sum(e.get("status") == "ready" for e in tracking["scenes"].values())
            return f"{ready} rendered clips matched. Assembly is available once every scene has a confirmed clip."
        return self._job("Checking VideoExpress renders and matching clip identities…", work)

    def generate_scene(self, scene_number, title, reference_name, aspect, image_prompt, motion_prompt):
        with self._lock:
            board = self._state["storyboard"]
            if self._state["busy"]:
                return {"error": "Wait for the current operation to finish."}
            if not board or type(scene_number) is not int or not any(s["scene_number"] == scene_number for s in board["scenes"]):
                return {"error": "Choose an existing storyboard scene."}
            if not title.strip() or not reference_name.strip() or aspect not in ("16:9", "9:16"):
                return {"error": "Enter the project title, reference photo library name, and a supported frame ratio."}
            if not image_prompt.strip() or not motion_prompt.strip():
                return {"error": "Enter both image direction and motion before generating this scene."}
            self.edit_scene(scene_number, image_prompt.strip(), motion_prompt.strip())
            config = dict(folder=title.strip(), reference=reference_name.strip(), aspect=aspect)
            tracking = load_tracking(self._out_dir / "storyboard.json", board, config)
            previous = tracking["scenes"].get(str(scene_number), {})
            if previous.get("status") in ("submitted", "ready", "submission_unknown"):
                self._state["status"] = f"Scene {scene_number} is already tracked ({previous['status']}). Refresh rendered clips; no duplicate was submitted."
                return self.get_state()
        def work():
            path, _ = self._save()
            run_batch(path, reference_name.strip(), aspect, folder_name=title.strip(),
                      start_scene=scene_number, end_scene=scene_number)
            return f"Scene {scene_number} submitted. Refresh rendered clips when it finishes, then auto-import it."
        return self._job(f"Generating scene {scene_number} only…", work)

    def auto_import_clip(self, scene_number):
        state = self.get_state()
        board = state["storyboard"]
        if not board or not any(s["scene_number"] == scene_number for s in board["scenes"]):
            return {"error": "Choose an existing storyboard scene."}
        path = self._out_dir / "storyboard.json"
        tracking = load_tracking(path, board)
        entry = tracking["scenes"].get(str(scene_number), {})
        if entry.get("status") != "ready" or not entry.get("asset_id"):
            return {"error": "Refresh rendered clips first. This scene needs a confirmed VideoExpress match."}
        def work():
            imported = self._import_tracked_scene(scene_number, entry, tracking["project"])
            return f"Scene {scene_number} downloaded and added to the preview." if imported else f"Scene {scene_number} is already imported."
        return self._job(f"Downloading scene {scene_number} from VideoExpress…", work)

    def _import_tracked_scene(self, number, entry, project, keep_manual=False):
        with self._lock:
            current = self._state["clips"].get(str(number))
            if current and Path(current["path"]).is_file() and (
                str(current.get("asset_id")) == str(entry["asset_id"]) or (keep_manual and not current.get("asset_id"))
            ):
                return False
        destination = self._out_dir / "clips" / project[:16] / f"scene-{number:03d}-{entry['asset_id']}"
        local = download_tracked_clip(entry["asset_id"], destination)
        with self._lock:
            self._state["clips"][str(number)] = dict(path=local, name=Path(local).name,
                url=self._register(local), asset_id=str(entry["asset_id"]))
            try:
                self._checkpoint()
            except Exception:
                pass  # The clip stays attached; the save warning remains visible.
        return True

    def auto_import_all_clips(self):
        state = self.get_state()
        board = state["storyboard"]
        if not board:
            return {"error": "Build or open a storyboard first."}
        tracking = load_tracking(self._out_dir / "storyboard.json", board)
        candidates = [(s["scene_number"], tracking["scenes"].get(str(s["scene_number"]), {})) for s in board["scenes"]]
        candidates = [(n,e) for n,e in candidates if e.get("status") == "ready" and e.get("asset_id")]
        if not candidates:
            return {"error": "No matched clips are ready. Refresh rendered clips first."}
        def work():
            imported, skipped, failures = 0, 0, []
            for i, (number, entry) in enumerate(candidates, 1):
                with self._lock:
                    self._state["status"] = f"Importing clip {i} of {len(candidates)} · scene {number} · {imported} downloaded, {skipped} skipped…"
                try:
                    if self._import_tracked_scene(number, entry, tracking["project"], keep_manual=True):
                        imported += 1
                    else:
                        skipped += 1
                except Exception as error:
                    failures.append(f"Scene {number}: {error}")
            summary = f"{imported} clips imported, {skipped} already imported."
            if failures:
                raise RuntimeError(summary + " Retry Auto-import all clips for the remaining failures:\n" + "\n".join(failures))
            pending = board["scene_count"] - len(candidates)
            return summary + (f" {pending} scenes are not ready yet; refresh tracking and import again later." if pending else " Ready to preview with your song.")
        return self._job("Importing all ready VideoExpress clips…", work)

    def assemble(self, title, ids=""):
        state = self.get_state()
        board = state["storyboard"]
        if not ids.strip():
            try:
                tracking = load_tracking(self._out_dir / "storyboard.json", board)
                if tracking.get("config", {}).get("folder") != title.strip():
                    raise ValueError("Use the project title recorded during scene generation.")
                idents = ordered_asset_ids(board, tracking)
            except (ValueError, TypeError) as error:
                return {"error": safe_error(error)}
        else:
            idents = [i.strip() for i in ids.split(",")]
        if not title.strip() or not board or len(idents) != board["scene_count"] or any(not i.isascii() or not i.isdecimal() for i in idents):
            return {"error": "Enter the title and one numeric asset ID per scene, in storyboard order."}
        return self._job("Assembling your VideoExpress timeline…", lambda: (
            assemble_final_video(title.strip(), video_idents=idents), "Assembly complete. Review the saved VideoExpress project before exporting.")[1])

    def view_videoexpress_project(self, title):
        if not title.strip():
            return {"error": "Enter the same project title you used for assembly."}
        def work():
            project = view_final_project(title.strip())
            return f"Opened {project['title']} in VideoExpress. Press Play to review, then Export Video when ready."
        return self._job("Opening your saved final project in VideoExpress…", work)

    def export_final_video(self, title, size="1080", quality="high"):
        title = title.strip()
        if not title or size not in ("720", "1080") or quality not in ("low", "medium", "high"):
            return {"error": "Enter the saved project title and supported export settings."}
        with self._lock:
            if self._state["busy"]:
                return {"error": "Wait for the current operation to finish."}
        folders = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not folders:
            return self.get_state()
        previous = self.get_state().get("final_export") or {}
        same = previous.get("title") == title and previous.get("size") == size and previous.get("quality") == quality
        resumable = same and previous.get("status") in ("preparing", "submitted", "submission_unknown", "download_pending") and re.fullmatch(r"og-studio-[0-9a-f]{32}", str(previous.get("name", "")))
        journal = copy.deepcopy(previous) if resumable else dict(title=title, size=size, quality=quality,
                    name="og-studio-" + uuid.uuid4().hex, status="preparing")
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:90] or "Final video"
        journal["destination"] = str(Path(folders[0]) / f"{filename} - Final Video - {journal['name'][-8:]}.mp4")
        with self._lock:
            self._state["final_export"] = journal
        def checkpoint(**values):
            with self._lock:
                journal.update(values)
                self._state["final_export"] = copy.deepcopy(journal)
                self._checkpoint()
        def progress(message, percent=None):
            with self._lock:
                self._state["status"] = message
                self._state["download_percent"] = percent
        def work():
            path = export_and_download(journal, checkpoint, progress)
            return f"Final video downloaded · {path}"
        return self._job("Preparing final video export…", work)

    def open_downloaded_video(self):
        export = self.get_state().get("final_export") or {}
        path = Path(export.get("path", ""))
        if export.get("status") != "completed" or path.suffix.lower() != ".mp4" or not path.is_file():
            return {"error": "Export and download a final MP4 first."}
        os.startfile(str(path.resolve()))
        return self.get_state()


def serve(api):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = self.path.split("?", 1)[0]
            if route.startswith("/media/"):
                path = api._media.get(route.removeprefix("/media/"))
            else:
                path = {"/": ASSET_ROOT / "studio/index.html", "/studio.css": ASSET_ROOT / "studio/studio.css",
                        "/studio.js": ASSET_ROOT / "studio/studio.js"}.get(route)
            if not path or not path.is_file():
                self.send_error(404)
                return
            size = path.stat().st_size
            start, end = 0, size - 1
            partial = self.headers.get("Range")
            if partial:
                try:
                    unit, interval = partial.split("=", 1)
                    left, right = interval.split("-", 1)
                    if unit != "bytes" or not left:
                        raise ValueError()
                    start, end = int(left), min(int(right), size - 1) if right else size - 1
                    if not 0 <= start <= end < size:
                        raise ValueError()
                except ValueError:
                    self.send_error(416)
                    return
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with path.open("rb") as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        try:
            from transformers import BlipProcessor, BlipForQuestionAnswering
            import torch
            import librosa
            import numpy as np
            from webview.platforms import edgechromium
            features = librosa.feature.mfcc(y=np.sin(np.arange(44100) * 0.03), sr=22050)
            report = dict(ok=True, assets=(ASSET_ROOT / "studio/index.html").is_file(),
                          data_directory=str(DATA_ROOT), torch=torch.__version__, librosa=librosa.__version__,
                          audio_features=list(features.shape))
        except Exception:
            import traceback
            report = dict(ok=False, error=traceback.format_exc())
        Path(sys.argv[2]).write_text(json.dumps(report), encoding="utf-8")
        sys.exit(0 if report["ok"] and report.get("assets") else 1)
    api = StudioAPI(ROOT / ".studio-session.json")
    server = serve(api)
    api._window = webview.create_window("OG Studio · Music to motion", f"http://127.0.0.1:{server.server_port}",
                                       js_api=api, width=1380, height=900, min_size=(1000, 700), background_color="#101113")
    api._window.events.closing += api._on_closing
    try:
        webview.start(gui="edgechromium")
    finally:
        server.shutdown()

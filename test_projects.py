import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from studio_app import StudioAPI
from clip_tracking import load_tracking, save_tracking, scene_key


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = self.root / "session.json"
        self.patch_root = patch("studio_app.ROOT", self.root)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)
        self.api = StudioAPI(self.session)
        self.api._window = MagicMock()
        self.board = dict(song_title="Song", artist="Artist", total_duration=5, tempo_bpm=120, key="C major", scene_count=1,
            scenes=[dict(scene_number=1,start=0,end=5,duration=5,section_label="verse",image_prompt="Image",video_audio_prompt="Motion",video_prompt="Image, Motion")])
        self.api._state["storyboard"] = self.board
        for kind in ("audio", "photo"):
            path = self.root / (kind + ".dat")
            path.write_bytes(b"media")
            self.api._state[kind] = dict(path=str(path), name=path.name, url=self.api._register(path))
        clip = self.root / "clip.mp4"
        clip.write_bytes(b"video")
        self.api._state["clips"]["1"] = dict(path=str(clip),name=clip.name,url=self.api._register(clip))
        self.api._out_dir.mkdir(parents=True,exist_ok=True)
        track = load_tracking(self.api._out_dir / "storyboard.json", self.board, dict(folder="Song"))
        track["scenes"]["1"] = dict(scene_key=scene_key(self.board["scenes"][0]),status="ready",asset_id="123")
        save_tracking(self.api._out_dir / "storyboard.json", track)

    def test_autosave_restores_media_settings_drafts_and_tracking(self):
        old_url = self.api._state["audio"]["url"]
        self.api.update_workspace(dict(title="My project",appearance="Black jacket",aspect="9:16",preview_seconds=12,
            scroll_y=600,scene_drafts={"1":dict(image="Unsaved image draft",motion="Unsaved motion")}))
        restored = StudioAPI(self.session)
        state = restored.get_state()
        self.assertEqual(state["ui"]["appearance"], "Black jacket")
        self.assertEqual(state["ui"]["scene_drafts"]["1"]["image"], "Unsaved image draft")
        self.assertEqual(state["ui"]["preview_seconds"],12)
        self.assertNotEqual(state["audio"]["url"], old_url)
        self.assertEqual(restored._media[state["audio"]["url"].split("/")[-1]], self.root / "audio.dat")
        self.assertIn("1",state["clips"])
        self.assertEqual(state["tracking"]["1"]["asset_id"],"123")
        self.assertEqual(state["tracking_config"]["folder"],"Song")

    def test_named_project_can_be_reopened_and_autosaved(self):
        path = self.root / "Named.ogstudio.json"
        self.api._window.create_file_dialog.return_value = str(path)
        self.api.update_workspace(dict(title="Named"))
        self.api.save_project()
        self.api.update_workspace(dict(title="Updated name"))
        self.assertEqual(json.loads(path.read_text())["ui"]["title"],"Updated name")
        fresh = StudioAPI()
        fresh._window = MagicMock()
        fresh._window.create_file_dialog.return_value = [str(path)]
        state = fresh.open_project()
        self.assertEqual(state["ui"]["title"],"Updated name")
        self.assertEqual(state["tracking"]["1"]["asset_id"],"123")

    def test_missing_media_is_reported_without_losing_storyboard(self):
        self.api.update_workspace(dict(title="Song"))
        (self.root / "clip.mp4").unlink()
        restored = StudioAPI(self.session)
        self.assertIn("missing",restored.get_state()["error"])
        self.assertEqual(restored.get_state()["storyboard"]["scene_count"],1)
        self.assertNotIn("1",restored.get_state()["clips"])

    def test_exported_storyboard_imports_without_reanalysis(self):
        path = self.root / "storyboard.json"
        path.write_text(json.dumps(self.board))
        self.api._window.create_file_dialog.return_value = [str(path)]
        state = self.api.open_project()
        self.assertEqual(state["storyboard"]["song_title"],"Song")
        self.assertEqual(state["ui"]["title"],"Song")

    def test_invalid_import_leaves_current_project_unchanged(self):
        path = self.root / "invalid.json"
        path.write_text('{"scenes":"wrong"}')
        self.api._window.create_file_dialog.return_value = [str(path)]
        self.assertIn("error",self.api.open_project())
        self.assertEqual(self.api.get_state()["storyboard"],self.board)

    def test_recovery_does_not_restart_in_progress_job(self):
        self.api._state["busy"] = True
        self.api.update_workspace({})
        restored = StudioAPI(self.session)
        self.assertFalse(restored.get_state()["busy"])
        self.assertIn("interrupted", restored.get_state()["status"])

    def test_close_captures_last_edit_before_destroying_window(self):
        self.api._window.evaluate_js.return_value = dict(title="Last keystroke")
        self.assertFalse(self.api._on_closing())
        for thread in threading.enumerate():
            if thread.name.startswith("Thread-") and thread is not threading.current_thread():
                thread.join(2)
        self.assertEqual(json.loads(self.session.read_text())["ui"]["title"],"Last keystroke")
        self.api._window.destroy.assert_called_once()

    def test_failed_start_save_does_not_leave_job_busy(self):
        work = MagicMock()
        with patch("studio_app.write_project", side_effect=PermissionError("File locked")):
            result = self.api._job("Generating scene 2", work)
        self.assertIn("error", result)
        self.assertFalse(self.api.get_state()["busy"])
        self.assertIn("not started", self.api.get_state()["status"])
        self.assertIsNotNone(self.api.get_state()["save_error"])
        work.assert_not_called()
        self.api.update_workspace({"title":"Recovered"})
        self.assertIsNone(self.api.get_state()["save_error"])

    def test_completed_job_keeps_result_when_final_save_is_locked(self):
        with patch("studio_app.write_project", side_effect=[None, PermissionError("File locked")]):
            self.api._job("Working",lambda:"Operation completed")
            self.api._worker.join(5)
        self.assertFalse(self.api.get_state()["busy"])
        self.assertEqual(self.api.get_state()["status"],"Operation completed")
        self.assertIn("Autosave will retry", self.api.get_state()["save_error"])


if __name__ == "__main__":
    unittest.main()

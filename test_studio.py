import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from studio_app import StudioAPI, serve
from clip_tracking import load_tracking, save_tracking, scene_key


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = StudioAPI()
        self.api._out_dir = self.root
        self.api._window = MagicMock()

    def test_analysis_edit_and_export_use_real_storyboard(self):
        self.api._state["audio"] = dict(path="song.wav", name="song.wav", url="/media/test")
        analysis = dict(path="song.wav", duration=24.5, tempo=120, key="C major", sections=[
            dict(start=0, end=24.5, duration=24.5, energy=0.8, label="chorus")])
        with patch("studio_app.analyze_song", return_value=analysis):
            self.api.analyze(dict(title="Test song", style="Neon noir", character="Chris"))
            self.api._worker.join(5)
        state = self.api.get_state()
        self.assertFalse(state["busy"])
        self.assertIsNone(state["error"])
        self.assertEqual(sum(s["duration"] for s in state["storyboard"]["scenes"]), 25)
        self.assertIn("Chris", state["storyboard"]["scenes"][0]["image_prompt"])
        self.api.edit_scene(1, "Edited image", "Edited movement")
        saved = json.loads((self.root / "storyboard.json").read_text())
        self.assertEqual(saved["scenes"][0]["video_audio_prompt"], "Edited movement")

    def test_background_failure_recovers(self):
        def fail():
            raise RuntimeError("Expected failure")
        self.api._job("Testing", fail)
        self.api._worker.join(5)
        self.assertFalse(self.api.get_state()["busy"])
        self.assertEqual(self.api.get_state()["error"], "Expected failure")

    def test_selecting_photo_automatically_drafts_appearance(self):
        self.api._window.create_file_dialog.return_value = [str(self.root / "portrait.jpg")]
        with patch("studio_app.describe_appearance", return_value="Clothing: blue jacket. Hair: short.") as describe:
            self.api.choose_media("photo")
            self.api._worker.join(5)
            state = self.api.get_state()
            describe.assert_called_once_with(str((self.root / "portrait.jpg").resolve()))
            self.assertEqual(state["appearance_draft"]["photo_url"], state["photo"]["url"])
            self.assertIn("blue jacket", state["appearance_draft"]["text"])

    def test_photo_analysis_failure_keeps_photo_and_recovers(self):
        self.api._window.create_file_dialog.return_value = [str(self.root / "portrait.jpg")]
        with patch("studio_app.describe_appearance", side_effect=RuntimeError("Model could not download")):
            self.api.choose_media("photo")
            self.api._worker.join(5)
            state = self.api.get_state()
            self.assertFalse(state["busy"])
            self.assertIsNotNone(state["photo"])
            self.assertIsNone(state["appearance_draft"])
            self.assertEqual(state["error"], "Model could not download")

    def test_overlapping_operations_are_rejected(self):
        release = threading.Event()
        self.api._job("First", lambda: (release.wait(5), "Done")[1])
        try:
            self.assertIn("error", self.api._job("Second", lambda: "Should not run"))
        finally:
            release.set()
            self.api._worker.join(5)

    def test_media_ranges_and_unregistered_paths(self):
        path = self.root / "test.wav"
        path.write_bytes(b"0123456789")
        route = self.api._register(path)
        server = serve(self.api)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"
        with urlopen(Request(origin + route, headers={"Range":"bytes=2-5"})) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b"2345")
        with self.assertRaises(HTTPError) as error:
            urlopen(origin + "/studio_app.py")
        self.assertEqual(error.exception.code, 404)

    def test_first_scene_only_reaches_backend(self):
        self.api._state["storyboard"] = dict(song_title="Song", artist="", tempo_bpm=120,
            key="C major", total_duration=5, scene_count=1, scenes=[dict(scene_number=1,
            section_label="verse", start=0, end=5, duration=5, video_prompt="Test")])
        with patch("studio_app.run_batch") as run:
            self.api.generate("Song", "Portrait", "16:9", True)
            self.api._worker.join(5)
            self.assertEqual(run.call_args.kwargs["end_scene"], 1)

    def test_assembly_uses_confirmed_scene_mapping_without_manual_ids(self):
        board = dict(song_title="Song", artist="", total_duration=5, scene_count=1,
                     scenes=[dict(scene_number=1, start=0, end=5, duration=5,
                                  image_prompt="Image", video_audio_prompt="Motion")])
        self.api._state["storyboard"] = board
        data = load_tracking(self.root / "storyboard.json", board, dict(folder="Song"))
        data["scenes"]["1"] = dict(scene_key=scene_key(board["scenes"][0]), status="ready", asset_id="123")
        save_tracking(self.root / "storyboard.json", data)
        with patch("studio_app.assemble_final_video") as assemble:
            self.api.assemble("Song")
            self.api._worker.join(5)
            assemble.assert_called_once_with("Song", video_idents=["123"])

    def test_auto_import_attaches_download_to_correct_scene(self):
        board = dict(song_title="Song", artist="", total_duration=5, scene_count=1,
                     scenes=[dict(scene_number=1, start=0, end=5, duration=5,
                                  image_prompt="Image", video_audio_prompt="Motion")])
        self.api._state["storyboard"] = board
        data = load_tracking(self.root / "storyboard.json", board)
        data["scenes"]["1"] = dict(scene_key=scene_key(board["scenes"][0]), status="ready", asset_id="123")
        save_tracking(self.root / "storyboard.json", data)
        local = self.root / "downloaded.mp4"
        local.write_bytes(b"video fixture")
        with patch("studio_app.download_tracked_clip", return_value=str(local)) as download:
            self.api.auto_import_clip(1)
            self.api._worker.join(5)
            self.assertEqual(download.call_args.args[0], "123")
            clip = self.api.get_state()["clips"]["1"]
            self.assertEqual(clip["path"], str(local))
            self.assertEqual(self.api._media[clip["url"].split("/")[-1]], local)

    def test_auto_import_without_match_does_not_download(self):
        self.api._state["storyboard"] = dict(song_title="Song",scenes=[dict(scene_number=1)])
        with patch("studio_app.download_tracked_clip") as download:
            result = self.api.auto_import_clip(1)
            self.assertIn("error", result)
            download.assert_not_called()

    def test_generate_scene_saves_card_prompts_and_submits_only_selected_scene(self):
        board = dict(song_title="Song", artist="", total_duration=10, tempo_bpm=120, key="C major",scene_count=2,
            scenes=[dict(scene_number=n, start=(n-1)*5,end=n*5,duration=5,section_label="verse",
                         image_prompt="Old image",video_audio_prompt="Old motion",video_prompt="Original") for n in (1,2)])
        self.api._state["storyboard"] = board
        with patch("studio_app.run_batch") as run:
            self.api.generate_scene(2,"Song","Portrait","16:9","New image","New motion")
            self.api._worker.join(5)
            self.assertEqual(run.call_args.kwargs["start_scene"],2)
            self.assertEqual(run.call_args.kwargs["end_scene"],2)
            saved = json.loads((self.root / "storyboard.json").read_text())
            self.assertEqual(saved["scenes"][1]["image_prompt"],"New image")
            self.assertEqual(saved["scenes"][1]["video_audio_prompt"],"New motion")
            self.assertEqual(saved["scenes"][0]["video_prompt"],"Original")

    def test_generate_scene_does_not_duplicate_an_existing_tracked_job(self):
        board = dict(song_title="Song",artist="",total_duration=5,tempo_bpm=120,key="C major",scene_count=1,
            scenes=[dict(scene_number=1,start=0,end=5,duration=5,section_label="verse",
                         image_prompt="Image",video_audio_prompt="Motion",video_prompt="Image, Motion")])
        self.api._state["storyboard"] = board
        data=load_tracking(self.root / "storyboard.json",board,dict(folder="Song",reference="Portrait",aspect="16:9"))
        data["scenes"]["1"]=dict(scene_key=scene_key(board["scenes"][0]),status="submitted",uuid="job-1")
        save_tracking(self.root / "storyboard.json",data)
        with patch("studio_app.run_batch") as run:
            result=self.api.generate_scene(1,"Song","Portrait","16:9","Image","Motion")
            self.assertIn("no duplicate",result["status"])
            run.assert_not_called()

    def test_generate_nonexistent_scene_is_rejected(self):
        with patch("studio_app.run_batch") as run:
            self.assertIn("error",self.api.generate_scene(99,"Song","Portrait","16:9","Image","Motion"))
            run.assert_not_called()

    def _ready_import_board(self):
        board=dict(song_title="Song",artist="",total_duration=15,scene_count=3,
            scenes=[dict(scene_number=n,start=(n-1)*5,end=n*5,duration=5,image_prompt="Image",video_audio_prompt="Motion") for n in (1,2,3)])
        self.api._state["storyboard"]=board
        tracking=load_tracking(self.root / "storyboard.json",board)
        for scene in board["scenes"]:
            tracking["scenes"][str(scene["scene_number"])]=dict(scene_key=scene_key(scene),status="ready",asset_id=str(100+scene["scene_number"]))
        save_tracking(self.root / "storyboard.json",tracking)

    def test_batch_import_downloads_in_scene_order_and_skips_on_retry(self):
        self._ready_import_board()
        def download(ident,destination):
            path=self.root / f"{ident}.mp4"
            path.write_bytes(b"clip")
            return str(path)
        with patch("studio_app.download_tracked_clip",side_effect=download) as mocked:
            self.api.auto_import_all_clips()
            self.api._worker.join(5)
            self.assertEqual([c.args[0] for c in mocked.call_args_list],["101","102","103"])
            mocked.reset_mock()
            self.api.auto_import_all_clips()
            self.api._worker.join(5)
            mocked.assert_not_called()
            self.assertIn("3 already imported",self.api.get_state()["status"])

    def test_batch_import_preserves_manual_import_and_successes_on_failure(self):
        self._ready_import_board()
        manual=self.root / "manual.mp4"
        manual.write_bytes(b"manual clip")
        self.api._state["clips"]["2"]=dict(path=str(manual),name=manual.name,url=self.api._register(manual))
        def download(ident,destination):
            if ident=="103":
                raise RuntimeError("Download failed")
            path=self.root / f"{ident}.mp4"
            path.write_bytes(b"clip")
            return str(path)
        with patch("studio_app.download_tracked_clip",side_effect=download) as mocked:
            self.api.auto_import_all_clips()
            self.api._worker.join(5)
            state=self.api.get_state()
            self.assertEqual([c.args[0] for c in mocked.call_args_list],["101","103"])
            self.assertEqual(state["clips"]["2"]["path"],str(manual))
            self.assertIn("1",state["clips"])
            self.assertNotIn("3",state["clips"])
            self.assertIn("Scene 3",state["error"])

    def test_batch_import_needs_a_ready_match(self):
        self.api._state["storyboard"]=dict(song_title="Song",scenes=[dict(scene_number=1)])
        with patch("studio_app.download_tracked_clip") as mocked:
            self.assertIn("error",self.api.auto_import_all_clips())
            mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()

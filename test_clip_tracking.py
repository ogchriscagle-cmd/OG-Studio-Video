import json
from pathlib import Path
import tempfile
import unittest
from clip_tracking import load_tracking, save_tracking, scene_key, match_asset, ordered_asset_ids


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "storyboard.json"
        self.board = dict(song_title="Song", artist="", total_duration=10, scene_count=2,
                          scenes=[dict(scene_number=n, start=(n-1)*5, end=n*5, duration=5,
                                       image_prompt=f"Image {n}", video_audio_prompt="Move") for n in (1, 2)])

    def test_mapping_survives_restart_and_keeps_scene_order(self):
        data = load_tracking(self.path, self.board)
        for scene, ident in zip(reversed(self.board["scenes"]), (100, 200)):
            data["scenes"][str(scene["scene_number"])] = dict(scene_key=scene_key(scene), status="ready", asset_id=str(ident))
        save_tracking(self.path, data)
        restored = load_tracking(self.path, self.board)
        self.assertEqual(ordered_asset_ids(self.board, restored), ["200", "100"])
        self.board["scenes"][0]["image_prompt"] = "Changed"
        restored = load_tracking(self.path, self.board)
        self.assertNotIn("1", restored["scenes"])
        with self.assertRaises(ValueError):
            ordered_asset_ids(self.board, restored)

    def test_identity_requires_exact_unique_match(self):
        entry = dict(uuid="exact-job")
        assets = [dict(id=1, type="video", uuid="other"), dict(id=2, type="video", uuid="exact-job")]
        self.assertEqual(match_asset(entry, assets), "2")
        assets.append(dict(id=3, type="video", uuid="exact-job"))
        self.assertIsNone(match_asset(entry, assets))
        self.assertIsNone(match_asset(dict(uuid="missing"), assets))

    def test_pending_images_and_partial_urls_never_match(self):
        self.assertIsNone(match_asset(dict(uuid="job"), [dict(id=1, type="image", uuid="job")]))
        self.assertIsNone(match_asset(dict(uuid="job"), [dict(id=1, type="video", uuid="job", isPending=True)]))
        self.assertIsNone(match_asset(dict(uuid="job"), [dict(id=1,type="video",mediaPath="https://cdn/video.mp4?other")], "https://cdn/video.mp4"))

    def test_config_change_invalidates_previous_mapping(self):
        data = load_tracking(self.path, self.board, {"aspect":"16:9"})
        data["scenes"]["1"] = dict(scene_key=scene_key(self.board["scenes"][0]), status="submitted", uuid="job")
        save_tracking(self.path, data)
        self.assertFalse(load_tracking(self.path, self.board, {"aspect":"9:16"})["scenes"])


if __name__ == "__main__":
    unittest.main()

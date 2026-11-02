"""Offline checks for batch outcomes; no browser or paid generation required."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock
from clip_tracking import load_tracking, save_tracking, scene_key
from videoexpress_automation import SubmissionUncertain, SubmissionRejected


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.auth = root / "auth.json"
        self.auth.write_text("{}")
        self.story = root / "story.json"
        self.story.write_text(json.dumps({"scenes": [
            {"scene_number": n, "section_label": "verse", "duration": 5,
             "video_prompt": "test"} for n in (1, 2)
        ]}))
        self.generate = MagicMock(return_value="job-123")
        self.env = dict(
            AUTH_STATE_PATH=self.auth, DATA_ROOT=root, Path=Path, json=json, BASE_URL="https://example.invalid/",
            LOG_PATH=root / "log.json", __file__=str(root / "automation.py"),
            sync_playwright=MagicMock(), log=MagicMock(),
            launch_browser=MagicMock(),
            set_aspect_ratio=MagicMock(), open_create_video_from_prompt=MagicMock(),
            clamp_duration=lambda seconds: max(3, min(10, round(seconds))),
            fill_scene=MagicMock(), generate_image_and_video=self.generate,
            load_tracking=load_tracking, save_tracking=save_tracking, scene_key=scene_key,
            SubmissionUncertain=SubmissionUncertain,
            SubmissionRejected=SubmissionRejected,
        )
        tree = ast.parse(Path("videoexpress_automation.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_batch")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "batch", "exec"), self.env)

    def run_batch(self, **kwargs):
        return self.env["run_batch"](self.story, "photo", "16:9", **kwargs)

    def test_missing_login_raises_catchable_error_before_browser(self):
        self.auth.unlink()
        with self.assertRaisesRegex(RuntimeError, "Sign in & remember"):
            self.run_batch()
        self.env["sync_playwright"].assert_not_called()

    def test_success_returns_submitted_scenes(self):
        results = self.run_batch()
        self.assertEqual([r["status"] for r in results], ["submitted", "submitted"])

    def test_partial_failure_is_reported_and_logged(self):
        self.generate.side_effect = [RuntimeError("generation failed"), "job-2"]
        with self.assertRaisesRegex(RuntimeError, "1 of 2 scenes failed"):
            self.run_batch()
        results = json.loads(self.env["LOG_PATH"].read_text())
        self.assertEqual([r["status"] for r in results], ["failed", "submitted"])

    def test_empty_range_does_not_open_browser(self):
        with self.assertRaisesRegex(ValueError, "No scenes"):
            self.run_batch(start_scene=3)
        self.env["sync_playwright"].assert_not_called()

    def test_resume_does_not_resubmit_tracked_scenes(self):
        self.run_batch()
        self.generate.reset_mock()
        self.run_batch()
        self.generate.assert_not_called()

    def test_uncertain_submission_is_not_retried(self):
        self.generate.side_effect = SubmissionUncertain("response lost")
        with self.assertRaises(RuntimeError):
            self.run_batch()
        self.generate.reset_mock()
        with self.assertRaises(RuntimeError):
            self.run_batch()
        self.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()

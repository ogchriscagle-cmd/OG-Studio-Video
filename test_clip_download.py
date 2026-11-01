from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import videoexpress_automation as automation


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = self.root / "session.json"
        self.auth.write_text("{}")
        self.request = MagicMock()
        self.response = self.request.get.return_value
        self.response.status = 200
        self.response.headers = {"content-type":"video/mp4"}
        self.bytes = b"\x00\x00\x00\x18ftypisom" + b"test video payload"
        self.response.body.return_value = self.bytes
        self.assets = [dict(id=123, type="video", isPending=False, mediaPath="https://cdn-ny-b.videoexpress.ai/video/test.mp4")]

    def download(self):
        with patch.object(automation, "AUTH_STATE_PATH", self.auth), patch.object(automation, "library_videos", return_value=self.assets), patch.object(automation, "sync_playwright") as pw:
            pw.return_value.__enter__.return_value.request.new_context.return_value = self.request
            return automation.download_tracked_clip("123", self.root / "scene-1-123")

    def test_exact_asset_is_saved_atomically(self):
        path = Path(self.download())
        self.assertEqual(path.read_bytes(), self.bytes)
        self.assertEqual(path.suffix, ".mp4")
        self.assertFalse(list(self.root.glob("*.part")))
        self.request.dispose.assert_called_once()

    def test_login_html_is_not_saved_as_video(self):
        self.response.headers = {"content-type":"text/html"}
        with self.assertRaisesRegex(RuntimeError,"not a video"):
            self.download()
        self.assertFalse(list(self.root.glob("*.mp4")))

    def test_wrong_or_pending_asset_is_rejected(self):
        for asset in (dict(id=456,type="video"),dict(id=123,type="video",isPending=True)):
            with self.subTest(asset=asset):
                self.assets = [asset]
                with self.assertRaisesRegex(RuntimeError,"not available"):
                    self.download()
        self.request.get.assert_not_called()

    def test_untrusted_redirect_is_not_followed(self):
        self.response.status = 302
        self.response.headers = {"location":"https://example.com/video.mp4"}
        with self.assertRaisesRegex(RuntimeError,"unrecognized"):
            self.download()
        self.assertEqual(self.request.get.call_count, 1)

    def test_corrupted_file_is_not_attached(self):
        self.response.body.return_value = b"bad video"
        with self.assertRaisesRegex(RuntimeError,"unsupported"):
            self.download()
        self.assertFalse(list(self.root.glob("*.mp4")))


if __name__ == "__main__":
    unittest.main()

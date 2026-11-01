import unittest
from unittest.mock import MagicMock, patch
import videoexpress_automation as automation


class BrowserLaunchTests(unittest.TestCase):
    def test_missing_chromium_falls_back_to_installed_chrome(self):
        pw = MagicMock()
        browser = object()
        pw.chromium.launch.side_effect = [automation.PWError("Executable doesn't exist at chromium/chrome.exe"), browser]
        self.assertIs(automation.launch_browser(pw), browser)
        self.assertEqual(pw.chromium.launch.call_args.kwargs, dict(channel="chrome", headless=False))

    def test_spawn_failure_still_falls_back(self):
        pw = MagicMock()
        pw.chromium.launch.side_effect = [automation.PWError("spawn UNKNOWN"), "browser"]
        self.assertEqual(automation.launch_browser(pw), "browser")

    def test_other_browser_errors_are_preserved(self):
        pw = MagicMock()
        pw.chromium.launch.side_effect = automation.PWError("Unexpected configuration error")
        with self.assertRaisesRegex(automation.PWError, "configuration"):
            automation.launch_browser(pw)
        self.assertEqual(pw.chromium.launch.call_count, 1)

    def test_missing_both_browsers_explains_recovery(self):
        pw = MagicMock()
        pw.chromium.launch.side_effect = automation.PWError("Executable doesn't exist")
        with self.assertRaisesRegex(RuntimeError, "playwright install chromium"):
            automation.launch_browser(pw)


class SubmissionTests(unittest.TestCase):
    def page(self, payload):
        page = MagicMock()
        page.evaluate.return_value = dict(ready=1,failed=0,pending=0,total=1)
        page.locator.return_value.is_disabled.return_value = False
        response = page.expect_response.return_value.__enter__.return_value.value
        response.ok = True
        response.json.return_value = payload
        return page

    def submit(self, page, callback=None):
        with patch.object(automation, "_dismiss_disclaimer_if_present", return_value=False), patch.object(automation, "js_click"):
            return automation.generate_image_and_video(page, dict(scene_number=1), on_submitting=callback)

    def test_confirmed_uuid_is_returned_and_submission_is_checkpointed(self):
        callback = MagicMock()
        page = self.page(dict(success=True, uuid="accepted-job"))
        self.assertEqual(self.submit(page, callback), "accepted-job")
        callback.assert_called_once()
        predicate = page.expect_response.call_args.args[0]
        response = MagicMock(url="https://app.videoexpress.ai/ai/api/image2video")
        response.request.method = "POST"
        self.assertTrue(predicate(response))
        response.url = "https://example.com/ai/api/image2video"
        self.assertFalse(predicate(response))

    def test_missing_uuid_is_uncertain(self):
        with self.assertRaises(automation.SubmissionUncertain):
            self.submit(self.page(dict(success=True)))

    def test_explicit_rejection_is_not_reported_as_submission(self):
        with self.assertRaisesRegex(automation.SubmissionRejected, "Rejected"):
            self.submit(self.page(dict(success=False, message="Rejected")))

    def test_unreadable_response_requires_review(self):
        page = self.page({})
        page.expect_response.return_value.__enter__.return_value.value.json.side_effect = ValueError("bad JSON")
        with self.assertRaises(automation.SubmissionUncertain):
            self.submit(page)

    def test_one_failed_image_waits_for_second_candidate(self):
        page = self.page(dict(success=True,uuid="second-image-job"))
        page.evaluate.side_effect=[dict(ready=0,failed=1,pending=1,total=2),dict(ready=1,failed=1,pending=0,total=2)]
        with patch.object(automation.time,"sleep"):
            self.assertEqual(self.submit(page),"second-image-job")
        self.assertEqual(page.evaluate.call_count,2)

    def test_all_failed_images_never_submit_video(self):
        page = self.page({})
        page.evaluate.return_value=dict(ready=0,failed=2,pending=0,total=2)
        checkpoint=MagicMock()
        with self.assertRaisesRegex(RuntimeError,"No video was submitted"):
            self.submit(page,checkpoint)
        page.expect_response.assert_not_called()
        checkpoint.assert_not_called()


if __name__ == "__main__":
    unittest.main()

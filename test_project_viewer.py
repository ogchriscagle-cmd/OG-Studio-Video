import unittest
import threading
from unittest.mock import MagicMock, patch
import videoexpress_automation as automation


class ViewerTests(unittest.TestCase):
    def page(self, results):
        page=MagicMock()
        listing,opening=MagicMock(),MagicMock()
        listing.__enter__.return_value.value.ok=True
        listing.__enter__.return_value.value.json.return_value={"results":results}
        opening.__enter__.return_value.value.ok=True
        opening.__enter__.return_value.value.json.return_value={"id":123}
        page.expect_response.side_effect=[listing,opening]
        page.locator.return_value.count.return_value=0
        return page

    def test_opens_exact_saved_final_project_and_waits_for_timeline(self):
        page=self.page([dict(id=123,title="Song - Final Video"),dict(id=999,title="Other - Final Video")])
        with patch.object(automation,"js_click"):
            result=automation.open_final_project_page(page,"Song")
        self.assertEqual(result["id"],"123")
        pattern=page.locator.return_value.filter.call_args.kwargs["has_text"]
        self.assertTrue(pattern.search("Song - Final Video \u00a0 (11/01/2026 20:29)"))
        self.assertFalse(pattern.search("Song - Final Video Copy (11/01/2026 20:29)"))
        self.assertEqual(page.wait_for_selector.call_args.args[0],".track-row .brick")

    def test_missing_or_duplicate_name_is_not_guessed(self):
        for results in ([],[dict(id=123,title="Song - Final Video"),dict(id=456,title="Song - Final Video")]):
            with self.subTest(results=results):
                page=self.page(results)
                with patch.object(automation,"js_click"),self.assertRaises(RuntimeError):
                    automation.open_final_project_page(page,"Song")
                page.get_by_text.assert_not_called()

    def test_mismatched_open_response_is_not_reported_as_success(self):
        page=self.page([dict(id=456,title="Song - Final Video")])
        with patch.object(automation,"js_click"),self.assertRaisesRegex(RuntimeError,"confirm"):
            automation.open_final_project_page(page,"Song")

    def test_review_browser_stays_open_after_button_finishes(self):
        release,closed=threading.Event(),threading.Event()
        browser=MagicMock()
        page=browser.new_context.return_value.new_page.return_value
        page.wait_for_event.side_effect=lambda *args,**kwargs:release.wait(5)
        browser.close.side_effect=lambda:closed.set()
        with patch.object(automation,"AUTH_STATE_PATH") as auth,patch.object(automation,"sync_playwright"),patch.object(automation,"launch_browser",return_value=browser),patch.object(automation,"open_final_project_page",return_value=dict(id="123",title="Song - Final Video")):
            auth.exists.return_value=True
            try:
                result=automation.view_final_project("Song")
                self.assertEqual(result["id"],"123")
                browser.close.assert_not_called()
            finally:
                release.set()
                self.assertTrue(closed.wait(3))


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import MagicMock, patch
import final_export as export


class FinalExportTests(unittest.TestCase):
    def test_lookup_retries_connection_timeout(self):
        request = MagicMock()
        response = MagicMock(ok=True, status=200)
        response.json.return_value = dict(results=[])
        request.get.side_effect = [RuntimeError("Timeout\nCall log:\ncookie: secret"), response]
        with patch.object(export.time, "sleep"):
            self.assertIsNone(export.output_record(request, "Exact"))
        self.assertEqual(request.get.call_count, 2)

    def test_lookup_exhausted_retries_hides_headers(self):
        request = MagicMock()
        request.get.side_effect = RuntimeError("Timeout\nCall log:\ncookie: secret")
        with patch.object(export.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "three attempts") as failure:
                export.output_record(request, "Exact")
        self.assertNotIn("secret", str(failure.exception))
        self.assertEqual(request.get.call_count, 3)

    def test_ui_error_omits_authenticated_call_log(self):
        from studio_app import safe_error
        self.assertEqual(safe_error(RuntimeError("Timeout exceeded.\nCall log:\n - cookie: secret")), "Timeout exceeded.")

    def journal(self,status="submitted"):
        return dict(title="Song",name="og-studio-"+"a"*32,size="1080",quality="high",status=status,destination="final.mp4")

    def test_resume_download_does_not_submit_another_render(self):
        journal=self.journal()
        events=[]
        def checkpoint(**values):
            journal.update(values);events.append(values["status"])
        record=dict(id=123,title=journal["name"],extension="mp4",path="123/final.mp4",mediaPath="https://cdn-ny-b.videoexpress.ai/video/final.mp4")
        with patch.object(export,"AUTH_STATE_PATH") as auth,patch.object(export,"sync_playwright") as pw,patch.object(export,"output_record",side_effect=[None,record]),patch.object(export,"launch_browser") as browser,patch.object(export,"download_video_url",return_value="final.mp4") as download,patch.object(export.time,"sleep"):
            auth.exists.return_value=True
            result=export.export_and_download(journal,checkpoint,MagicMock())
            self.assertEqual(result,"final.mp4")
            browser.assert_not_called()
            self.assertEqual(events,["download_pending","completed"])
            self.assertEqual("https://cdn-ny-b.videoexpress.ai/video/final.mp4",download.call_args.args[1])
            pw.return_value.__enter__.return_value.request.new_context.return_value.dispose.assert_called_once()

    def test_download_failure_keeps_export_resumable(self):
        journal=self.journal()
        def checkpoint(**values):journal.update(values)
        record=dict(id=123,path="123/final.mp4")
        with patch.object(export,"AUTH_STATE_PATH") as auth,patch.object(export,"sync_playwright"),patch.object(export,"output_record",return_value=record),patch.object(export,"download_video_url",side_effect=RuntimeError("Connection lost")):
            auth.exists.return_value=True
            with self.assertRaisesRegex(RuntimeError,"Connection lost"):
                export.export_and_download(journal,checkpoint,MagicMock())
        self.assertEqual(journal["status"],"download_pending")

    def test_unknown_submission_is_never_resubmitted(self):
        journal=self.journal("submission_unknown")
        with patch.object(export,"AUTH_STATE_PATH") as auth,patch.object(export,"sync_playwright"),patch.object(export,"output_record",return_value=None),patch.object(export,"submit_export") as submit:
            auth.exists.return_value=True
            with self.assertRaisesRegex(RuntimeError,"not be submitted twice"):
                export.export_and_download(journal,MagicMock(),MagicMock(),timeout_sec=0)
            submit.assert_not_called()

    def test_output_lookup_uses_exact_name_and_format(self):
        request=MagicMock()
        request.get.return_value.ok=True
        request.get.return_value.json.return_value=dict(results=[dict(title="Other",extension="mp4"),dict(title="Exact",extension="mp4",id=7)])
        self.assertEqual(export.output_record(request,"Exact")["id"],7)

    def test_render_submission_is_checkpointed_before_create(self):
        page,request=MagicMock(),MagicMock()
        request.get.return_value.ok=True
        request.get.return_value.json.return_value=dict(results=[])
        page.locator.return_value.count.return_value=0
        response=page.expect_response.return_value.__enter__.return_value.value
        response.ok=True;response.json.return_value=dict(success=True)
        events=[]
        page.locator.return_value.click.side_effect=lambda:events.append("create")
        def checkpoint(**values):events.append(values["status"])
        with patch.object(export,"open_final_project_page",return_value=dict(id="42")),patch.object(export,"js_click"):
            export.submit_export(page,request,self.journal("preparing"),checkpoint)
        self.assertEqual(events,["submission_unknown","create","submitted"])


if __name__ == "__main__":
    unittest.main()

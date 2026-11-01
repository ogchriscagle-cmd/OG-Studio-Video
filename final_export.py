"""Render a saved VideoExpress project and download only its uniquely named output."""
import time
from urllib.parse import urlparse, quote
from playwright.sync_api import sync_playwright
from videoexpress_automation import BASE_URL, AUTH_STATE_PATH, launch_browser, open_final_project_page, js_click, download_video_url


def output_record(request, name):
    response = None
    for attempt in range(3):
        try:
            response = request.get(BASE_URL + "api/get_list_output", timeout=60_000)
        except Exception:
            if attempt == 2:
                raise RuntimeError("VideoExpress export lookup could not connect after three attempts. Retry Export & download to check again; an existing export will not be submitted twice.") from None
        else:
            if response.status not in (429, 500, 502, 503, 504):
                break
            if attempt == 2:
                raise RuntimeError("VideoExpress is temporarily unavailable. Retry Export & download in a few minutes.")
        time.sleep(2 * (attempt + 1))
    if not response.ok:
        raise RuntimeError("Could not read completed exports. Sign in to VideoExpress again and retry.")
    try:
        matches = [r for r in response.json().get("results", []) if r.get("title") == name and r.get("extension") == "mp4"]
    except Exception as error:
        raise RuntimeError("VideoExpress returned no export list. Please sign in again.") from error
    if len(matches) > 1:
        raise RuntimeError("More than one export has the same tracking name; no file was downloaded.")
    return matches[0] if matches else None


def submit_export(page, request, journal, checkpoint):
    queue = request.get(BASE_URL + "user_queue", timeout=30_000)
    if not queue.ok or queue.json().get("results"):
        raise RuntimeError("VideoExpress already has an active render, or its queue could not be read. Wait for it to finish, then retry.")
    project = open_final_project_page(page, journal["title"])
    js_click(page, ".button-render-project")
    form = page.locator("#formExportProject")
    form.wait_for(state="visible", timeout=30_000)
    form.locator('input[name="name"]').fill(journal["name"])
    form.locator('select[name="format"]').select_option("mp4")
    form.locator('select[name="size"]').select_option(journal["size"])
    form.locator('select[name="quality"]').select_option(journal["quality"])
    warning = page.locator(".bbm-modal--open .alerts-bottom")
    if warning.count() and warning.inner_text().strip():
        raise RuntimeError("VideoExpress export warning: " + warning.inner_text().strip() + " Review this in VideoExpress before exporting.")
    checkpoint(status="submission_unknown", project_id=project["id"])
    try:
        with page.expect_response(lambda r: urlparse(r.url).path == f"/render_project/{project['id']}" and r.request.method == "POST", timeout=60_000) as submission:
            page.locator(".bbm-modal--open .button-submit:visible").click()
        response = submission.value
        payload = response.json()
    except Exception as error:
        raise RuntimeError("The export may have been accepted. Retry this button to check for its result without submitting a duplicate render.") from error
    if isinstance(payload, dict) and payload.get("success") is False:
        checkpoint(status="rejected")
        raise RuntimeError(payload.get("msg") or payload.get("error") or "VideoExpress rejected this export.")
    if not response.ok or not isinstance(payload, dict) or not payload.get("success"):
        raise RuntimeError("VideoExpress did not confirm the export. Retry to check for its result without another submission.")
    checkpoint(status="submitted")


def export_and_download(journal, checkpoint, progress, timeout_sec=1800):
    if not AUTH_STATE_PATH.exists():
        raise RuntimeError("Sign in to VideoExpress before exporting your final video.")
    with sync_playwright() as pw:
        request = pw.request.new_context(storage_state=str(AUTH_STATE_PATH))
        browser = None
        page = None
        try:
            record = output_record(request, journal["name"])
            if not record and journal["status"] in ("preparing", "rejected"):
                progress("Opening the saved final project and preparing its export…")
                browser = launch_browser(pw)
                page = browser.new_context(storage_state=str(AUTH_STATE_PATH)).new_page()
                submit_export(page, request, journal, checkpoint)
            deadline = time.monotonic() + timeout_sec
            while not record:
                if time.monotonic() >= deadline:
                    raise RuntimeError("The export is still pending or needs attention in VideoExpress. Retry Export & download to check again; the saved request will not be submitted twice.")
                percent = ""
                if page:
                    label = page.locator(".progress-percent-b:visible")
                    if label.count():
                        percent = " · " + label.first.inner_text()
                progress("Waiting for your final VideoExpress render" + percent + "…")
                if page:
                    page.wait_for_timeout(3000)
                else:
                    time.sleep(3)
                record = output_record(request, journal["name"])
            if not record.get("mediaPath") and not record.get("path"):
                raise RuntimeError("The completed export has no download path. Retry after checking My Videos in VideoExpress.")
            checkpoint(status="download_pending", output_id=str(record["id"]))
            progress("Final render complete. Downloading your MP4…")
            # Current exports live on VideoExpress's CDN; the legacy output
            # route can return 404 even though the completed file is available.
            url = record.get("mediaPath") or BASE_URL + "userfiles/output/" + quote(str(record["path"]), safe="/")
            def download_progress(received, total):
                mb = received / (1024 * 1024)
                percent = min(100, received * 100 / total) if total else None
                detail = f"{percent:.0f}% · {mb:.1f} / {total / (1024 * 1024):.1f} MB" if total else f"{mb:.1f} MB received"
                progress("Downloading your MP4 · " + detail, percent)
            path = download_video_url(request, url, journal["destination"], progress=download_progress)
            checkpoint(status="completed", path=path)
            return path
        finally:
            if browser:
                browser.close()
            request.dispose()

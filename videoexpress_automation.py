"""
Automates VideoExpress.ai's "Create Video From Prompt" flow for every scene
in a storyboard.json produced by storyboard.py.

First-time setup (one manual login, session reused after that):
    python videoexpress_automation.py login

Run the batch:
    python videoexpress_automation.py run storyboard.json --ref-photo "Og-chris-reference-16x9" --aspect 16:9

Notes / known limits:
  - Storyboards must use whole-second scenes between 3 and 10 seconds.
    Rebuild older storyboards to cover the song without truncating scenes.
  - This drives the real site's DOM. If VideoExpress changes their UI, the
    selectors below will need updating.
"""
import argparse
import json
import sys
import time
import threading
import queue
import re
from pathlib import Path
from urllib.parse import urlparse, quote, urljoin
from clip_tracking import load_tracking, save_tracking, scene_key, match_asset
from runtime_paths import DATA_ROOT

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError

AUTH_STATE_PATH = DATA_ROOT / "videoexpress_auth_state.json"
BASE_URL = "https://app.videoexpress.ai/"
MAX_DURATION = 10
MIN_DURATION = 3

LOG_PATH = DATA_ROOT / "videoexpress_run_log.json"


def log(msg):
    print(f"[videoexpress] {msg}", flush=True)


def launch_browser(pw):
    try:
        return pw.chromium.launch(headless=False)
    except PWError as error:
        if not any(reason in str(error) for reason in ("spawn UNKNOWN", "Executable doesn't exist")):
            raise
        log("Bundled Chromium could not start; trying installed Google Chrome.")
        try:
            return pw.chromium.launch(channel="chrome", headless=False)
        except PWError as fallback_error:
            raise RuntimeError(
                "Could not start Chromium or installed Google Chrome. "
                "Install Google Chrome, or run .venv\\Scripts\\python.exe -m playwright install chromium "
                "from the project folder, then retry."
            ) from fallback_error


def js_click(page, selector):
    """Click via raw JS (document.querySelector(sel).click()), matching the
    exact approach that worked during manual testing. Avoids Playwright's
    coordinate-based click being intercepted by overlapping panel chrome."""
    found = page.evaluate(
        "(sel) => { const el = document.querySelector(sel); if (el) { el.click(); return true; } return false; }",
        selector,
    )
    if not found:
        raise RuntimeError(f"js_click: no element found for selector {selector!r}")


def do_login():
    """Open a real visible browser so the user can log in once. Session
    cookies get saved to AUTH_STATE_PATH for all future automated runs."""
    with sync_playwright() as pw:
        browser = launch_browser(pw)
        context = browser.new_context(**({"storage_state": str(AUTH_STATE_PATH)} if AUTH_STATE_PATH.exists() else {}))
        page = context.new_page()
        page.goto(BASE_URL)
        log("Log in to VideoExpress.ai in the opened browser window.")
        log("Waiting for login to complete (looking for the editor to load)...")
        try:
            page.wait_for_selector(".button-generate-video", timeout=300_000)
        except PWTimeout:
            log("Timed out waiting for login. Nothing was saved.")
            browser.close()
            raise RuntimeError("VideoExpress login timed out. Please try signing in again.")
        context.storage_state(path=str(AUTH_STATE_PATH))
        log(f"Session saved to {AUTH_STATE_PATH}. You can close the browser now.")
        browser.close()


def check_saved_session():
    """Check saved cookies without opening a browser or changing the project."""
    if not AUTH_STATE_PATH.exists():
        return "missing"
    with sync_playwright() as pw:
        request = pw.request.new_context(storage_state=str(AUTH_STATE_PATH))
        try:
            response = request.get(BASE_URL + "api/get_list_output", timeout=30_000)
            if response.status in (401, 403):
                return "expired"
            if not response.ok:
                return "unavailable"
            try:
                data = response.json()
            except Exception:
                return "expired" if "login" in response.url.lower() else "unavailable"
            return "connected" if isinstance(data, dict) and isinstance(data.get("results"), list) else "expired"
        except Exception:
            return "unavailable"
        finally:
            request.dispose()


def clamp_duration(seconds):
    d = int(round(seconds))
    return max(MIN_DURATION, min(MAX_DURATION, d))


def reset_to_clean_state(page):
    """Close any leftover modal/panel from a previous (possibly failed)
    scene before starting the next one."""
    for _ in range(4):
        closed_anything = False
        for sel in [".bbm-modal--open .button-close", ".button-close-panel"]:
            loc = page.locator(sel)
            if loc.count() > 0:
                try:
                    loc.last.click(timeout=1500, force=True)
                    closed_anything = True
                except Exception:
                    pass
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(300)
        if not closed_anything:
            break


def open_create_video_from_prompt(page):
    reset_to_clean_state(page)
    js_click(page, ".button-generate-video")
    page.wait_for_timeout(300)
    js_click(page, ".button-generate-from-prompt")
    page.wait_for_selector("textarea[name=prompt]", timeout=15_000)


def set_aspect_ratio(page, aspect):
    # aspect is "16:9" or "9:16"
    btn = page.locator(f'button[data-value="{aspect}"]').first
    if btn.count() > 0:
        try:
            btn.click(timeout=2000)
        except Exception:
            pass


def fill_scene(page, scene, ref_photo_name, aspect, folder_name="ogchris"):
    page.fill("textarea[name=prompt]", scene["image_prompt"])
    page.fill("textarea[name=video_prompt]", scene["video_audio_prompt"])

    page.select_option("select[name=select-type]", "photorealistic")

    def ensure_checked(name, checked):
        page.evaluate(
            """([name, desired]) => {
                const el = document.querySelector('input[name=' + name + ']');
                if (!el) return 'not_found';
                if (el.checked !== desired) { el.click(); }
                return el.checked;
            }""",
            [name, checked],
        )

    ensure_checked("auto_enhance_prompt", True)
    ensure_checked("use_consistent_character", bool(ref_photo_name))
    ensure_checked("shared", False)

    # Advanced mode reveals manual length controls.
    ensure_checked("advanced_mode", True)
    page.wait_for_selector("input[name=manual_video_length]", timeout=5000)
    ensure_checked("manual_video_length", True)

    duration = clamp_duration(scene["duration"])
    if scene["duration"] > MAX_DURATION:
        log(f"  scene {scene['scene_number']}: duration {scene['duration']:.1f}s "
            f"clamped to {MAX_DURATION}s (site max)")
    page.eval_on_selector(
        "input[name=video_duration]",
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); "
        "el.dispatchEvent(new Event('change', {bubbles:true})); }",
        duration,
    )

    if ref_photo_name:
        set_reference_photo(page, ref_photo_name, folder_name)


def set_reference_photo(page, ref_photo_name, folder_name="ogchris"):
    js_click(page, ".button-reference-photo2")
    page.wait_for_selector(".bbm-modal--open", timeout=20_000)
    try:
        page.wait_for_selector(".bbm-modal--open .library-folder-title", timeout=10_000)
    except Exception:
        pass

    entered_folder = False
    for attempt in range(3):
        entered_folder = page.evaluate(
            """(folderName) => {
                const modals = document.querySelectorAll('.bbm-modal--open');
                const modal = modals[modals.length - 1];
                const title = Array.from(modal.querySelectorAll('.library-folder-title'))
                    .find(e => e.textContent.trim() === folderName);
                if (title) { title.closest('.library-item').click(); return true; }
                return false;
            }""",
            folder_name,
        )
        if entered_folder:
            page.wait_for_timeout(1500)
            break
        page.wait_for_timeout(1000)

    # This picker often shows no human-readable title (just a numeric asset id),
    # so name-matching is unreliable. Each project folder is meant to hold exactly
    # one reference photo, so prefer the lone image when there is one; only fall
    # back to name matching if the folder has more than one image.
    selection = page.evaluate(
        """(name) => {
            const modals = document.querySelectorAll('.bbm-modal--open');
            const modal = modals[modals.length - 1];
            const images = Array.from(modal.querySelectorAll('.library-item[data-type="image"]'));
            if (images.length === 1) {
                images[0].click();
                return { matched: true, mode: 'only_image', count: images.length };
            }
            const byTitle = Array.from(modal.querySelectorAll('.library-item-title'))
                .find(e => e.textContent.trim() === name);
            if (byTitle) {
                byTitle.closest('.library-item').click();
                return { matched: true, mode: 'title_match', count: images.length };
            }
            const byAttr = images.find(el => (el.getAttribute('title') || '').toLowerCase().includes(name.toLowerCase()));
            if (byAttr) {
                byAttr.click();
                return { matched: true, mode: 'attr_match', count: images.length };
            }
            return { matched: false, mode: null, count: images.length };
        }""",
        ref_photo_name,
    )
    if not selection["matched"]:
        raise RuntimeError(f"reference photo '{ref_photo_name}' not found in Select Image modal "
                            f"(folder '{folder_name}', entered_folder={entered_folder}, "
                            f"images_in_folder={selection['count']})")
    page.evaluate(
        """() => {
            const modals = document.querySelectorAll('.bbm-modal--open');
            const modal = modals[modals.length - 1];
            const btn = Array.from(modal.querySelectorAll('button'))
                .find(b => b.textContent.trim() === 'Choose');
            if (btn) btn.click();
        }"""
    )


def open_media_library_modal(page):
    """Open the full-screen Media Library modal (folder grid + upload controls),
    starting from the main editor. If the modal is already open this is a
    harmless no-op."""
    already_open = page.evaluate(
        "() => !!document.querySelector('.library-folder-add')"
    )
    if already_open:
        return
    page.evaluate(
        """() => {
            const link = Array.from(document.querySelectorAll('a'))
                .find(a => a.textContent.trim() === 'Media Library');
            if (link) link.click();
        }"""
    )
    page.wait_for_timeout(800)
    expand_clicked = page.evaluate(
        """() => {
            const btn = document.querySelector('.button-expand');
            if (btn) { btn.click(); return true; }
            return false;
        }"""
    )
    if not expand_clicked:
        raise RuntimeError("open_media_library_modal: .button-expand not found")
    page.wait_for_selector(".library-folder-add", timeout=10_000)
    page.wait_for_timeout(300)


def create_folder(page, folder_name):
    """Create a Media Library folder if it doesn't already exist. Returns True
    if a new folder was created, False if one with that name already existed."""
    exists = page.evaluate(
        """(name) => {
            const titles = document.querySelectorAll('.library-folder-title');
            return Array.from(titles).some(e => e.textContent.trim() === name);
        }""",
        folder_name,
    )
    if exists:
        log(f"  folder '{folder_name}' already exists, skipping creation")
        return False

    js_click(page, ".library-folder-add")
    page.wait_for_selector("input[name='name']", timeout=5_000)
    page.wait_for_timeout(300)
    page.fill("input[name='name']", folder_name)
    page.evaluate(
        """() => {
            const btn = Array.from(document.querySelectorAll('button'))
                .find(b => b.textContent.trim() === 'Add');
            if (btn) btn.click();
        }"""
    )
    page.wait_for_timeout(1000)
    created = page.evaluate(
        """(name) => {
            const titles = document.querySelectorAll('.library-folder-title');
            return Array.from(titles).some(e => e.textContent.trim() === name);
        }""",
        folder_name,
    )
    if not created:
        raise RuntimeError(f"create_folder: '{folder_name}' not found after creation attempt")
    log(f"  created folder '{folder_name}'")
    return True


def open_folder(page, folder_name):
    """Click into a Media Library folder by its visible title."""
    entered = page.evaluate(
        """(name) => {
            const titles = document.querySelectorAll('.library-folder-title');
            const t = Array.from(titles).find(e => e.textContent.trim() === name);
            if (!t) return false;
            t.closest('.library-item').click();
            return true;
        }""",
        folder_name,
    )
    if not entered:
        raise RuntimeError(f"open_folder: folder '{folder_name}' not found")
    page.wait_for_timeout(800)


def upload_files_to_folder(page, folder_name, file_paths):
    """Upload one or more local files (image and/or audio) into the given
    Media Library folder. Assumes open_media_library_modal() has already run.
    file_paths: list of absolute/relative path strings."""
    open_folder(page, folder_name)

    clicked = page.evaluate(
        """() => {
            const btn = Array.from(document.querySelectorAll('button'))
                .find(b => b.textContent.trim() === 'Upload file');
            if (btn) { btn.click(); return true; }
            return false;
        }"""
    )
    if not clicked:
        raise RuntimeError("upload_files_to_folder: 'Upload file' button not found")
    page.wait_for_timeout(500)

    file_input = page.wait_for_selector("input.dz-hidden-input", timeout=5_000, state="attached")
    file_input.set_input_files([str(p) for p in file_paths])
    page.wait_for_timeout(1500)

    submitted = page.evaluate(
        """() => {
            const btn = Array.from(document.querySelectorAll('button'))
                .find(b => b.textContent.trim() === 'Upload files');
            if (btn) { btn.click(); return true; }
            return false;
        }"""
    )
    if not submitted:
        raise RuntimeError("upload_files_to_folder: 'Upload files' submit button not found "
                            "(staged files may not have been confirmed)")

    deadline = time.time() + 60
    while time.time() < deadline:
        page.wait_for_timeout(1000)
        still_uploading = page.evaluate(
            "() => !!document.querySelector('.dz-progress, .dz-processing')"
        )
        if not still_uploading:
            break
    log(f"  uploaded {len(file_paths)} file(s) to folder '{folder_name}'")

    close_clicked = page.evaluate(
        """() => {
            const btn = Array.from(document.querySelectorAll('button'))
                .find(b => b.textContent.trim() === 'Close');
            if (btn) { btn.click(); return true; }
            return false;
        }"""
    )
    return close_clicked


def setup_project_folder(title_name, ref_photo_path, song_path):
    """Create a Media Library folder named after the song/project title and
    upload the character reference image and the song file into it.
    Launches its own browser session (reuses the saved login state)."""
    if not AUTH_STATE_PATH.exists():
        raise RuntimeError("No saved VideoExpress session found. Run python videoexpress_automation.py login first.")

    to_upload = []
    if ref_photo_path:
        p = Path(ref_photo_path)
        if not p.is_file():
            raise FileNotFoundError(f"reference photo not found: {ref_photo_path}")
        to_upload.append(p)
    if song_path:
        p = Path(song_path)
        if not p.is_file():
            raise FileNotFoundError(f"song file not found: {song_path}")
        to_upload.append(p)
    if not to_upload:
        log("Nothing to upload (no --ref-photo or --song given); just creating the folder.")

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        context = browser.new_context(storage_state=str(AUTH_STATE_PATH))
        page = context.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector(".button-generate-video", timeout=30_000)

        open_media_library_modal(page)
        create_folder(page, title_name)
        if to_upload:
            upload_files_to_folder(page, title_name, to_upload)

        log(f"Done. Folder '{title_name}' is ready in Media Library.")
        browser.close()

def _dismiss_disclaimer_if_present(page):
    return page.evaluate(
        """() => {
            const agree = Array.from(document.querySelectorAll('button'))
                .find(b => b.textContent.trim() === 'I Agree');
            if (agree) { agree.click(); return true; }
            return false;
        }"""
    )


class SubmissionUncertain(RuntimeError):
    pass


class SubmissionRejected(RuntimeError):
    pass


GENERATED_IMAGE_STATE_JS = """() => {
    const items = Array.from(document.querySelectorAll('.swiper-slide-pair-item'));
    let ready = 0, failed = 0, pending = 0, chosen = null;
    for (const item of items) {
        const img = item.querySelector('img');
        if (!img || !img.getAttribute('src')) { pending++; continue; }
        const path = new URL(img.src, document.baseURI).pathname;
        if (path === '/img/slide-error.png') { failed++; continue; }
        if (path.includes('loading') || !img.complete) { pending++; continue; }
        if (img.naturalWidth <= 10 || path.startsWith('/img/icon-')) { failed++; continue; }
        ready++;
        if (!chosen) chosen = item;
    }
    if (chosen) chosen.click();
    return {ready, failed, pending, total: items.length};
}"""


def generate_image_and_video(page, scene, timeout_sec=120, on_submitting=None):
    js_click(page, ".button-generate-image-submit")

    log(f"  scene {scene['scene_number']}: waiting for image generation...")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _dismiss_disclaimer_if_present(page):
            log(f"  scene {scene['scene_number']}: dismissed consistent-character disclaimer")
        image_state = page.evaluate(GENERATED_IMAGE_STATE_JS)
        if image_state["ready"]:
            break
        if image_state["total"] and image_state["failed"] == image_state["total"]:
            raise RuntimeError(f"scene {scene['scene_number']}: VideoExpress image generation failed for every candidate. No video was submitted; review the image prompt or retry this scene.")
        time.sleep(3)
    else:
        raise TimeoutError(f"scene {scene['scene_number']}: image generation did not "
                            f"finish within {timeout_sec}s")

    # The readiness probe selected an actual generated image, never an error icon.
    page.wait_for_timeout(1000)

    video_btn = page.locator(".button-generate-video-submit")
    select_deadline = time.time() + 20
    while time.time() < select_deadline and video_btn.is_disabled():
        time.sleep(1)
    if video_btn.is_disabled():
        raise TimeoutError(f"scene {scene['scene_number']}: Create Video stayed disabled "
                            f"after selecting generated image")

    if on_submitting:
        on_submitting()
    try:
        with page.expect_response(
            lambda r: urlparse(r.url).netloc == urlparse(BASE_URL).netloc
            and urlparse(r.url).path == "/ai/api/image2video"
            and r.request.method == "POST", timeout=60_000
        ) as response_info:
            js_click(page, ".button-generate-video-submit")
        response = response_info.value
        payload = response.json()
    except Exception as error:
        raise SubmissionUncertain("The video request may have been accepted, but its response could not be confirmed. Do not submit this scene again automatically.") from error
    if isinstance(payload, dict) and payload.get("success") is False:
        raise SubmissionRejected(payload.get("message") or payload.get("msg") or "VideoExpress rejected the video request.")
    if not response.ok or not isinstance(payload, dict) or not payload.get("success"):
        raise SubmissionUncertain("VideoExpress returned an unexpected submission response. Review this scene before retrying.")
    if not payload.get("uuid"):
        raise SubmissionUncertain("VideoExpress accepted the request without a job UUID. Check the library before retrying.")
    log(f"  scene {scene['scene_number']}: video generation submitted "
        f"(renders async, check Media Library > My Media)")
    return str(payload["uuid"])


def run_batch(storyboard_path, ref_photo_name, aspect, start_scene=1, end_scene=None,
              image_wait_sec=120, folder_name="ogchris"):
    if not AUTH_STATE_PATH.exists():
        raise RuntimeError("No saved VideoExpress session found. Run python videoexpress_automation.py login first.")

    storyboard = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    scenes = storyboard["scenes"]
    if end_scene is None:
        end_scene = len(scenes)
    selected_scenes = [s for s in scenes if start_scene <= s["scene_number"] <= end_scene]
    if not selected_scenes:
        raise ValueError("No scenes match the requested scene range.")
    if any(s["duration"] != clamp_duration(s["duration"]) for s in selected_scenes):
        raise ValueError("Rebuild this storyboard first: scenes must be whole seconds between 3 and 10 seconds.")

    results = []
    tracking = load_tracking(storyboard_path, storyboard, dict(folder=folder_name, reference=ref_photo_name, aspect=aspect))
    def record(scene, **values):
        entry = tracking["scenes"].setdefault(str(scene["scene_number"]), {"scene_key": scene_key(scene)})
        entry.update(values)
        save_tracking(storyboard_path, tracking)
    with sync_playwright() as pw:
        browser = launch_browser(pw)
        context = browser.new_context(storage_state=str(AUTH_STATE_PATH))
        page = context.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector(".button-generate-video", timeout=30_000)
        set_aspect_ratio(page, aspect)

        for scene in selected_scenes:
            n = scene["scene_number"]
            previous = tracking["scenes"].get(str(n), {})
            if previous.get("status") in ("submitted", "ready", "submission_unknown"):
                results.append({"scene_number": n, **previous})
                log(f"Scene {n}: already tracked ({previous['status']}); skipping duplicate submission.")
                continue
            if n < start_scene or n > end_scene:
                continue
            log(f"Scene {n}/{len(scenes)} ({scene['section_label']}, "
                f"{scene['duration']:.1f}s): {scene['video_prompt'][:70]}...")
            try:
                open_create_video_from_prompt(page)
                fill_scene(page, scene, ref_photo_name, aspect, folder_name)
                uuid = generate_image_and_video(page, scene, timeout_sec=image_wait_sec,
                    on_submitting=lambda: record(scene, status="submission_unknown", uuid=None,
                                                  asset_id=None, error=None, render_status=None))
                try:
                    record(scene, status="submitted", uuid=uuid)
                except OSError as error:
                    raise SubmissionUncertain(f"Video job {uuid} was accepted, but its tracking file could not be saved. Do not resubmit it.") from error
                results.append({"scene_number": n, "status": "submitted", "uuid": uuid})
            except Exception as e:
                log(f"  scene {n} FAILED: {e}")
                debug_dir = DATA_ROOT / "debug"
                debug_dir.mkdir(exist_ok=True)
                try:
                    page.screenshot(path=str(debug_dir / f"scene{n}_failure.png"))
                    (debug_dir / f"scene{n}_failure.html").write_text(page.content(), encoding="utf-8")
                    log(f"  saved debug screenshot/html to {debug_dir}")
                except Exception as debug_e:
                    log(f"  could not save debug info: {debug_e}")
                status = "submission_unknown" if not isinstance(e, SubmissionRejected) and (isinstance(e, SubmissionUncertain) or tracking["scenes"].get(str(n), {}).get("status") == "submission_unknown") else "failed"
                record(scene, status=status, error=str(e))
                results.append({"scene_number": n, "status": status, "error": str(e)})

        LOG_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
        log(f"Done. Wrote results to {LOG_PATH}")
        any_failed = any(r["status"] in ("failed", "submission_unknown") for r in results)
        if any_failed:
            log("Some scenes failed; closing browser to avoid leaving stray processes.")
            browser.close()
            failed = [str(r["scene_number"]) for r in results if r["status"] in ("failed", "submission_unknown")]
            raise RuntimeError(
                f"{len(failed)} of {len(results)} scenes failed (scenes {', '.join(failed)}). "
                f"See {LOG_PATH} for details. Submitted scenes may still be rendering; "
                "avoid rerunning them."
            )
        else:
            log("Browser left open so you can check Media Library for render progress.")
    return results


def library_videos(request):
    """Read all generated video records using the signed-in library session."""
    def get(path, params=None):
        response = request.get(BASE_URL + path, params=params, timeout=30_000)
        if not response.ok:
            raise RuntimeError(f"VideoExpress returned HTTP {response.status}. Please sign in again if your session expired.")
        try:
            return response.json()
        except Exception as error:
            raise RuntimeError("VideoExpress returned no library data. Please sign in again.") from error
    category = next((c for c in get("library/get_categories/4").get("data", []) if c.get("title") == "My AI Videos"), None)
    if category is None:
        raise RuntimeError("My AI Videos was not found in your media library.")
    assets, start = [], 0
    while True:
        page = get("api/library/get_media/4", dict(categoryId=category["id"], start=start,
                   limit=100, page=start // 100 + 1, query="", orderBy="id", orderDir="desc", filter="video"))
        batch = page.get("results", [])
        assets.extend(batch)
        start += len(batch)
        if not batch or start >= int(page.get("total", start)):
            return assets


def download_video_url(request, url, destination, progress=None):
    """Validate and atomically save a video from the VideoExpress service."""
    if progress is not None:
        return download_streamed_video(request, url, destination, progress)
    url = urljoin(BASE_URL, url)
    for _ in range(6):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not (parsed.hostname == "videoexpress.ai" or (parsed.hostname or "").endswith(".videoexpress.ai")) or parsed.username or parsed.password:
            raise RuntimeError("VideoExpress returned an unrecognized download host.")
        response = request.get(url, timeout=120_000, max_redirects=0)
        if response.status in (301, 302, 303, 307, 308):
            url = urljoin(url, response.headers.get("location", ""))
            continue
        break
    else:
        raise RuntimeError("The clip download redirected too many times.")
    if response.status != 200:
        raise RuntimeError(f"Clip download returned HTTP {response.status}. Try signing in again.")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if not (content_type.startswith("video/") or content_type == "application/octet-stream"):
        raise RuntimeError("The download was not a video. Your VideoExpress session may have expired.")
    body = response.body()
    if len(body) >= 12 and body[4:8] == b"ftyp":
        extension = ".mp4"
    elif body[:4] == b"\x1a\x45\xdf\xa3":
        extension = ".webm"
    else:
        raise RuntimeError("VideoExpress returned an empty or unsupported video file.")
    path = Path(destination).with_suffix(extension)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    try:
        partial.write_bytes(body)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return str(path.resolve())


def download_streamed_video(request, url, destination, progress):
    import requests
    path = Path(destination).with_suffix(".mp4")
    partial = path.with_suffix(".mp4.part")
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        for cookie in request.storage_state().get("cookies", []):
            session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"],
                                path=cookie.get("path", "/"), secure=cookie.get("secure", False))
        try:
            url = urljoin(BASE_URL, url)
            for _ in range(6):
                parsed = urlparse(url)
                if parsed.scheme != "https" or not (parsed.hostname == "videoexpress.ai" or (parsed.hostname or "").endswith(".videoexpress.ai")) or parsed.username or parsed.password:
                    raise RuntimeError("VideoExpress returned an unrecognized download host.")
                response = session.get(url, stream=True, allow_redirects=False, timeout=(30, 60))
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers.get("location", ""))
                    response.close()
                    continue
                break
            else:
                raise RuntimeError("The video download redirected too many times.")
            with response:
                if response.status_code != 200:
                    raise RuntimeError(f"Video download returned HTTP {response.status_code}. Retry the download.")
                content_type = response.headers.get("content-type", "").lower()
                if not (content_type.startswith("video/") or content_type.startswith("application/octet-stream")):
                    raise RuntimeError("The download was not a video. Check your VideoExpress sign-in.")
                total = int(response.headers.get("content-length", "0"))
                received = 0
                header = b""
                progress(0, total)
                with partial.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        header = (header + chunk)[:12]
                        output.write(chunk)
                        received += len(chunk)
                        progress(received, total)
                if len(header) < 12 or header[4:8] != b"ftyp":
                    raise RuntimeError("VideoExpress returned an empty or unsupported MP4 file.")
                if total and received != total:
                    raise RuntimeError("The download was interrupted. Retry to download the completed export again.")
                partial.replace(path)
                return str(path.resolve())
        except requests.RequestException:
            raise RuntimeError("The video download connection was interrupted. Retry Export & download; no new render is needed.") from None
        finally:
            partial.unlink(missing_ok=True)


def download_tracked_clip(asset_id, destination):
    """Download one exact, rendered library asset. Never start a generation."""
    asset_id = str(asset_id)
    if not asset_id.isascii() or not asset_id.isdecimal():
        raise ValueError("A numeric matched video asset ID is required.")
    if not AUTH_STATE_PATH.exists():
        raise RuntimeError("Sign in to VideoExpress before auto-importing a clip.")
    with sync_playwright() as pw:
        request = pw.request.new_context(storage_state=str(AUTH_STATE_PATH))
        try:
            matches = [a for a in library_videos(request) if str(a.get("id")) == asset_id]
            if len(matches) != 1 or matches[0].get("type") != "video" or matches[0].get("isPending"):
                raise RuntimeError("The matched clip is not available as a rendered video. Refresh rendered clips and retry.")
            asset = matches[0]
            url = asset.get("mediaPath") or asset.get("originalUrl") or asset.get("videoUrl")
            if not url:
                filename, extension = asset.get("fileName"), asset.get("extension")
                if not filename or extension not in ("mp4", "webm", "mov"):
                    raise RuntimeError("VideoExpress did not provide a supported video download location.")
                prefix = f"userfiles/input/{quote(str(asset.get('userId')), safe='')}/" if asset.get("isPrivate") else "library/video/"
                url = prefix + quote(str(filename), safe="") + "." + extension
            return download_video_url(request, url, destination)
        finally:
            request.dispose()


def refresh_clip_tracking(storyboard_path):
    """Read job status and exact library identities without submitting new media."""
    if not AUTH_STATE_PATH.exists():
        raise RuntimeError("Sign in to VideoExpress first to refresh rendered clips.")
    board = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    tracking = load_tracking(storyboard_path, board)
    with sync_playwright() as pw:
        request = pw.request.new_context(storage_state=str(AUTH_STATE_PATH))
        def get(path, params=None):
            response = request.get(BASE_URL + path, params=params, timeout=30_000)
            if not response.ok:
                raise RuntimeError(f"VideoExpress returned HTTP {response.status}. Sign in again if your session expired.")
            try:
                return response.json()
            except Exception as error:
                raise RuntimeError("VideoExpress did not return library data. Please sign in again.") from error
        try:
            assets = library_videos(request)
            for entry in tracking["scenes"].values():
                if not entry.get("uuid") or entry.get("status") == "ready":
                    continue
                status = get("ai/api/status/" + quote(entry["uuid"], safe=""))
                entry["render_status"] = status.get("status", "UNKNOWN")
                response = status.get("response") or {}
                completed_url = response if isinstance(response, str) and response.startswith("https://") else None
                if isinstance(response, dict):
                    completed_url = response.get("videoUrl") or response.get("url")
                ident = match_asset(entry, assets, completed_url)
                if not ident and entry["render_status"] == "SUCCEEDED" and isinstance(response, dict):
                    confirmed = str(response.get("mediaId", ""))
                    matching = [a for a in assets if str(a.get("id")) == confirmed and a.get("type") == "video" and not a.get("isPending")]
                    if len(matching) == 1:
                        ident = confirmed
                if ident:
                    entry.update(asset_id=ident, status="ready")
                elif entry["render_status"] in ("FAILED", "CANCELED"):
                    entry["status"] = "render_failed"
                save_tracking(storyboard_path, tracking)
        finally:
            request.dispose()
    return tracking


def _open_project_folder(page, folder_name):
    """Enter a Media Library folder (the panel/modal must already be open)."""
    entered = page.evaluate(
        """(folderName) => {
            const t = Array.from(document.querySelectorAll('.library-folder-title'))
                .find(e => e.textContent.trim() === folderName);
            if (t) { t.closest('.library-item').click(); return true; }
            return false;
        }""",
        folder_name,
    )
    if not entered:
        back = page.locator(".button-back:visible")
        if back.count():
            back.last.click()
            page.wait_for_timeout(800)
            return bool(page.evaluate(
                """name => {
                    const t = Array.from(document.querySelectorAll('.library-folder-title'))
                        .find(e => e.textContent.trim() === name);
                    if (!t) return false;
                    t.closest('.library-item').click(); return true;
                }""", folder_name))
    return entered


def open_final_project_page(page, folder_name):
    """Open a saved final project in a fresh editor without changing its content."""
    project_name = f"{folder_name} - Final Video"
    page.goto(BASE_URL)
    page.wait_for_selector(".button-generate-video", timeout=30_000)
    with page.expect_response(lambda r: urlparse(r.url).path == "/project/get_list" and r.request.method == "GET", timeout=30_000) as listing:
        js_click(page, ".button-open-project")
    response = listing.value
    if not response.ok:
        raise RuntimeError("Could not read saved VideoExpress projects. Sign in again and retry.")
    matches = [p for p in response.json().get("results", []) if p.get("title") == project_name]
    if len(matches) != 1:
        raise RuntimeError(f"{'No saved project matches' if not matches else 'More than one saved project matches'} '{project_name}'. Open VideoExpress and choose the intended project from Open.")
    ident = str(matches[0].get("id", ""))
    if not ident.isascii() or not ident.isdecimal():
        raise RuntimeError("VideoExpress returned an invalid saved project ID.")
    saved_list = page.locator(".bbm-modal--open .list-container")
    if saved_list.count() and not saved_list.is_visible():
        page.locator(".bbm-modal--open .button-show-list").click()
    project_row = page.locator(".bbm-modal--open .list-group-item").filter(
        has_text=re.compile(r"^\s*" + re.escape(project_name) + r"\s+\("))
    project_row.click()
    with page.expect_response(lambda r: urlparse(r.url).path == f"/project/open/{ident}" and r.request.method == "GET", timeout=30_000) as opening:
        page.locator(".bbm-modal--open .button-submit:visible").click()
    opened = opening.value
    if not opened.ok or str(opened.json().get("id")) != ident:
        raise RuntimeError("VideoExpress did not confirm opening the selected project.")
    page.wait_for_selector(".track-row .brick", timeout=30_000)
    return dict(id=ident, title=project_name)


def view_final_project(folder_name):
    """Keep the review browser alive until its window closes, without blocking Studio."""
    if not AUTH_STATE_PATH.exists():
        raise RuntimeError("Sign in to VideoExpress first, then click View in VideoExpress again.")
    result = queue.Queue()
    cancel = threading.Event()
    def viewer():
        reported = False
        try:
            with sync_playwright() as pw:
                browser = launch_browser(pw)
                try:
                    context = browser.new_context(storage_state=str(AUTH_STATE_PATH))
                    page = context.new_page()
                    metadata = open_final_project_page(page, folder_name)
                    if cancel.is_set():
                        return
                    result.put((True, metadata))
                    reported = True
                    # Playwright must stay alive while the user reviews the timeline.
                    page.wait_for_event("close", timeout=0)
                finally:
                    browser.close()
        except Exception as error:
            if not reported:
                result.put((False, str(error)))
    threading.Thread(target=viewer, daemon=True).start()
    try:
        success, value = result.get(timeout=100)
    except queue.Empty:
        cancel.set()
        raise RuntimeError("Opening the final project timed out. Please check your VideoExpress login and retry.")
    if not success:
        raise RuntimeError(value)
    return value


def _drag_source_to_track(page, source_selector, track_selector, target_content_x):
    """Drag a .timeline-source-item onto a .track-row at a specific horizontal
    position in the track's internal (scrollable) coordinate space, scrolling
    the tracks-container into view first if needed. Uses real Playwright mouse
    events (mouse.move/down/up), not JS-dispatched MouseEvents -- the timeline
    is jQuery-UI draggable/droppable and only responds to trusted input."""
    page.eval_on_selector(source_selector, "el => el.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(300)

    margin = 100
    desired_scroll = max(0, target_content_x - margin)
    page.eval_on_selector("#tracks-container", "(el, v) => { el.scrollLeft = v; }", desired_scroll)
    page.wait_for_timeout(200)
    scroll_left = page.eval_on_selector("#tracks-container", "el => el.scrollLeft")

    track_box = page.eval_on_selector(
        track_selector,
        "el => { const r = el.getBoundingClientRect(); return {x:r.x, y:r.y, w:r.width, h:r.height}; }",
    )
    src_box = page.eval_on_selector(
        source_selector,
        "el => { const r = el.getBoundingClientRect(); return {x:r.x, y:r.y, w:r.width, h:r.height}; }",
    )

    start_x = src_box["x"] + src_box["w"] / 2
    start_y = src_box["y"] + src_box["h"] / 2
    end_x = track_box["x"] + (target_content_x - scroll_left) + 5
    end_y = track_box["y"] + track_box["h"] / 2

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    steps = 15
    for i in range(1, steps + 1):
        x = start_x + (end_x - start_x) * i / steps
        y = start_y + (end_y - start_y) * i / steps
        page.mouse.move(x, y)
        page.wait_for_timeout(25)
    page.wait_for_timeout(150)
    page.mouse.up()
    page.wait_for_timeout(800)


def assemble_final_video(folder_name, video_idents=None):
    """Drag the generated scene video clips onto the timeline's first track,
    in scene order, and the project's uploaded song onto the second track.
    Saves the project afterward. Does NOT trigger Export Video -- file name/
    quality/resolution are left as a manual step in the app.

    'My AI Videos' (where generated clips land) is shared across every
    project you've ever run, so auto-detecting "the 13 clips for this song"
    from folder contents alone is unreliable once you have more than one
    song's worth of clips in there. Pass video_idents (a list of Media
    Library asset ids, one per scene, in scene order) to assemble an exact,
    known set. If omitted, falls back to the old heuristic (every video in
    the named folder, sorted ascending by id) -- only safe for a folder that
    has never had more than one song's clips in it."""
    if not AUTH_STATE_PATH.exists():
        raise RuntimeError("No saved VideoExpress session found. Run python videoexpress_automation.py login first.")

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        context = browser.new_context(storage_state=str(AUTH_STATE_PATH))
        page = context.new_page()
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        page.evaluate(
            """() => {
                const sel = ['.modals-container button.close', '#modals-container .button-close',
                             '#modals-container [class*=close]', '.hrb [class*=close]'];
                for (const s of sel) {
                    const el = document.querySelector(s);
                    if (el) { el.click(); return s; }
                }
                return null;
            }"""
        )
        page.wait_for_timeout(500)

        open_media_library_modal(page)
        if not _open_project_folder(page, folder_name):
            raise RuntimeError(f"assemble_final_video: folder '{folder_name}' not found")
        page.wait_for_timeout(1500)

        items = page.evaluate(
            """() => Array.from(document.querySelectorAll('.timeline-source-item')).map(el => ({
                ident: el.getAttribute('data-ident'),
                type: el.getAttribute('data-type'),
                title: el.getAttribute('title'),
            }))"""
        )
        audios = [it for it in items if it["type"] == "audio"]
        if not audios:
            raise RuntimeError(f"assemble_final_video: no audio file found in folder '{folder_name}'")

        track_ids = page.evaluate("Array.from(document.querySelectorAll('.track-row')).map(e => e.id)")
        if len(track_ids) < 2:
            js_click(page, ".button-add-track")
            page.wait_for_timeout(500)
            track_ids = page.evaluate("Array.from(document.querySelectorAll('.track-row')).map(e => e.id)")
        video_track, audio_track = track_ids[0], track_ids[1]

        if video_idents:
            if not _open_project_folder(page, "My AI Videos"):
                raise RuntimeError("assemble_final_video: 'My AI Videos' folder not found "
                                    "(that's where generated clips land)")
            page.wait_for_timeout(1000)
            for i in range(8):
                more = page.query_selector(".button-more")
                if not more or not more.is_visible():
                    break
                more.click()
                page.wait_for_timeout(600)
            all_items = page.evaluate(
                """() => Array.from(document.querySelectorAll('.timeline-source-item')).map(el => ({
                    ident: el.getAttribute('data-ident'), type: el.getAttribute('data-type'),
                }))"""
            )
            by_ident = {it["ident"]: it for it in all_items if it["type"] == "video"}
            missing = [str(i) for i in video_idents if str(i) not in by_ident]
            if missing:
                raise RuntimeError(f"assemble_final_video: video ident(s) not found in library: {missing}")
            videos = [{"ident": str(i)} for i in video_idents]
        else:
            videos = sorted([it for it in items if it["type"] == "video"], key=lambda it: int(it["ident"]))
            if not videos:
                raise RuntimeError(
                    f"assemble_final_video: no video clips found in folder '{folder_name}' yet "
                    f"(clips render async after submission -- wait a few minutes and retry)"
                )

        log(f"Assembling {len(videos)} scene clip(s) onto track '{video_track}'...")
        cursor_x = 0
        for i, item in enumerate(videos, start=1):
            src_sel = f'.timeline-source-item[data-ident="{item["ident"]}"]'
            prev_count = page.eval_on_selector_all(f"#{video_track} .brick", "els => els.length")
            placed = False
            for attempt in range(1, 4):
                _drag_source_to_track(page, src_sel, f"#{video_track}", cursor_x)
                page.wait_for_timeout(400)
                bricks = page.evaluate(
                    "(sel) => Array.from(document.querySelectorAll(sel + ' .brick')).map(b => ({"
                    "left: parseFloat(b.style.left) || 0, width: parseFloat(b.style.width) || 0}))",
                    f"#{video_track}",
                )
                if len(bricks) > prev_count:
                    cursor_x = max(b["left"] + b["width"] for b in bricks)
                    placed = True
                    break
                log(f"  clip {i}/{len(videos)} (ident {item['ident']}): drop didn't register, retry {attempt}/3")
            if not placed:
                raise RuntimeError(
                    f"assemble_final_video: failed to drop clip {i}/{len(videos)} (ident {item['ident']}) "
                    f"onto the timeline after 3 attempts"
                )
            log(f"  clip {i}/{len(videos)} placed (ident {item['ident']}); next cursor at {cursor_x:.0f}px")

        if video_idents:
            if not _open_project_folder(page, folder_name):
                raise RuntimeError(f"assemble_final_video: folder '{folder_name}' not found (on return)")
            page.wait_for_timeout(1000)

        log(f"Adding song onto track '{audio_track}'...")
        audio_sel = f'.timeline-source-item[data-ident="{audios[0]["ident"]}"]'
        _drag_source_to_track(page, audio_sel, f"#{audio_track}", 0)

        # A brand-new project is unnamed/unsaved -- clicking the plain "Save" button
        # only works for a project that was already saved once before. Use
        # "Save Project As" (the dropdown next to Save) and fill in a name so this
        # works whether or not the project has been saved before.
        project_name = f"{folder_name} - Final Video"
        js_click(page, ".btn-group .dropdown-toggle")
        page.wait_for_timeout(500)
        js_click(page, ".button-save-project-as")
        page.wait_for_timeout(1200)
        name_field = page.query_selector("#modalFieldName")
        if name_field:
            name_field.fill(project_name)
            js_click(page, ".button-submit")
            page.wait_for_timeout(1500)
            log(f"Saved project as '{project_name}'.")
        else:
            log("Could not find the Save-As name field -- please save manually in the app.")

        log("Done. Review the timeline in VideoExpress, then click Export Video when ready.")
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="One-time manual login, saves session")

    run_p = sub.add_parser("run", help="Run the storyboard batch")
    run_p.add_argument("storyboard", help="Path to storyboard.json")
    run_p.add_argument("--ref-photo", default="Og-chris-reference-16x9",
                        help="Name of the reference photo in the Media Library")
    run_p.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"])
    run_p.add_argument("--start-scene", type=int, default=1)
    run_p.add_argument("--end-scene", type=int, default=None)
    run_p.add_argument("--image-wait-sec", type=int, default=120)
    run_p.add_argument("--folder", default="ogchris",
                        help="Media Library folder containing the reference photo "
                             "(e.g. the project title folder created by setup-project)")

    setup_p = sub.add_parser("setup-project",
                              help="Create a Media Library folder named after the project "
                                   "title and upload a character reference image and/or "
                                   "song file into it")
    setup_p.add_argument("--title", required=True,
                          help="Project/song title; used as the Media Library folder name")
    setup_p.add_argument("--ref-photo", default=None,
                          help="Local path to a character reference image to upload")
    setup_p.add_argument("--song", default=None,
                          help="Local path to the song file (mp3/wav) to upload")

    assemble_p = sub.add_parser("assemble",
                                 help="Drag all generated scene clips + the song onto the "
                                      "timeline in order and save the project")
    assemble_p.add_argument("--folder", required=True,
                             help="Media Library folder containing the generated clips and song")
    assemble_p.add_argument("--idents", default=None,
                             help="Comma-separated Media Library video asset ids, one per scene, "
                                  "in scene order (bypasses auto-detection from folder contents, "
                                  "which is unreliable once 'My AI Videos' has more than one song's "
                                  "clips in it)")

    args = parser.parse_args()
    if args.cmd == "login":
        do_login()
    elif args.cmd == "run":
        run_batch(args.storyboard, args.ref_photo, args.aspect,
                   args.start_scene, args.end_scene, args.image_wait_sec, args.folder)
    elif args.cmd == "setup-project":
        setup_project_folder(args.title, args.ref_photo, args.song)
    elif args.cmd == "assemble":
        idents = [s.strip() for s in args.idents.split(",")] if args.idents else None
        assemble_final_video(args.folder, video_idents=idents)


if __name__ == "__main__":
    main()

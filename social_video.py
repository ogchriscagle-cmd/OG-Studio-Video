"""Local vertical-video rendering and isolated, short-form prompt plans."""
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

from PIL import Image, ImageDraw, ImageFont

PLATFORMS = ("YouTube Shorts", "Instagram Reels", "Facebook Reels", "TikTok")
PRESETS = {
    "Performance teaser": "An intimate music performance, expressive close-ups, dramatic stage light, build to an energetic final shot",
    "Cinematic story": "A mysterious journey through a rain-soaked city, a striking opening image, an emotional reveal, cinematic realism",
    "Behind the song": "An artist writing and recording a song in a warmly lit studio, intimate details and authentic creative moments",
    "Dream world": "A surreal dream landscape, floating lights, impossible architecture, a memorable visual transformation",
}


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def number(value, label, low, high):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be a number.") from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}.")
    return result


def probe(path, video=False):
    path = Path(path)
    if not path.is_file():
        raise ValueError("The selected media file is missing. Choose it again.")
    result = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True,
                            text=True, errors="replace", timeout=30,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    text = result.stderr
    duration = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not duration:
        raise ValueError("Could not read this media's duration. Try an MP4 video or an MP3/WAV song.")
    seconds = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])
    if seconds <= 0:
        raise ValueError("This media file has no playable duration.")
    info = dict(duration=seconds)
    if video:
        import imageio_ffmpeg
        reader = imageio_ffmpeg.read_frames(str(path))
        try:
            meta = next(reader)
            width, height = meta["size"]
        finally:
            reader.close()
        info.update(width=width, height=height)
    return info


def clip_settings(settings, available):
    if not isinstance(settings, dict):
        raise ValueError("Choose your clip settings first.")
    start = number(settings.get("start", 0), "Start time", 0, available)
    duration = number(settings.get("duration", 30), "Clip length", 3, 60)
    if start + duration > available + .05:
        raise ValueError("The clip runs past the end. Move the start time back or shorten the clip.")
    platform = settings.get("platform", PLATFORMS[0])
    if platform not in PLATFORMS:
        raise ValueError("Choose a supported platform.")
    return dict(start=start, duration=duration, platform=platform,
                framing="fit" if settings.get("framing") == "fit" else "crop",
                x=number(settings.get("x", 50), "Horizontal framing", 0, 100),
                y=number(settings.get("y", 50), "Vertical framing", 0, 100),
                hook=str(settings.get("hook") or "").strip()[:120],
                cta=str(settings.get("cta") or "").strip()[:100])


def framing_filter(settings, width=1080, height=1920):
    if settings["framing"] == "fit":
        return f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    return (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:(iw-ow)*{settings['x']/100:.6f}:(ih-oh)*{settings['y']/100:.6f},setsar=1")


def _font(size):
    for font in (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(str(font), size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def text_overlay(path, hook, cta):
    """Render user text as pixels; never interpolate it into FFmpeg expressions."""
    image = Image.new("RGBA", (1080, 1920))
    draw = ImageDraw.Draw(image)
    for text, top, size in ((hook, 260, 58), (cta, 1510, 46)):
        if not text:
            continue
        font = _font(size)
        lines, line = [], ""
        # Wrap even long single words so overlays remain inside the safe area.
        for char in text.replace("\n", " "):
            if draw.textlength(line + char, font=font) > 810:
                lines.append(line.strip()); line = ""
            line += char
        if line:
            lines.append(line.strip())
        lines = lines[:4]
        bottom = top + len(lines) * (size + 13) + 32
        draw.rounded_rectangle((90, top - 20, 990, bottom), radius=20, fill=(10, 13, 12, 205))
        for index, line in enumerate(lines):
            draw.text((540, top + index * (size + 13)), line, font=font, fill="white", anchor="mt")
    image.save(path)


def run_render(args, duration, progress=None):
    """Read FFmpeg progress continuously and keep error logs off the UI thread."""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errors:
        process = subprocess.Popen([ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                                    *args, "-progress", "pipe:1", "-nostats"],
                                   stdout=subprocess.PIPE, stderr=errors, text=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            for line in process.stdout:
                if line.startswith("out_time_us="):
                    try:
                        percent = min(99, max(0, float(line.split("=", 1)[1]) / 1e6 / duration * 100))
                    except ValueError:
                        continue
                    if progress:
                        progress(percent)
            if process.wait() != 0:
                errors.seek(0)
                detail = errors.read()[-1800:].strip()
                raise RuntimeError("Could not render this clip. " + detail)
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
            process.stdout.close()


def render_video(source, destination, settings, progress=None):
    source, destination = Path(source), Path(destination)
    config = clip_settings(settings, probe(source)["duration"])
    if source.resolve() == destination.resolve():
        raise ValueError("Choose a different filename from the original video.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + "." + uuid.uuid4().hex + ".partial.mp4")
    try:
        with tempfile.TemporaryDirectory(prefix="og-social-") as work:
            hook, cta = Path(work) / "hook.png", Path(work) / "cta.png"
            text_overlay(hook, config["hook"], "")
            text_overlay(cta, "", config["cta"])
            graph = (f"[0:v]{framing_filter(config)}[framed];"
                     "[framed][1:v]overlay=0:0:shortest=1:enable='lt(t,3)'[intro];"
                     f"[intro][2:v]overlay=0:0:shortest=1:enable='gte(t,{max(0,config['duration']-5)})'[v]")
            args = ["-ss", str(config["start"]), "-i", str(source), "-loop", "1", "-i", str(hook), "-loop", "1", "-i", str(cta),
                    "-filter_complex", graph,
                    "-map", "[v]", "-map", "0:a:0?", "-t", str(config["duration"]),
                    "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(temporary)]
            run_render(args, config["duration"], progress)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return str(destination)


def trim_song(source, destination, settings):
    config = clip_settings(settings, probe(source)["duration"])
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_render(["-ss", str(config["start"]), "-i", str(source), "-t", str(config["duration"]),
                "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(destination)], config["duration"])
    return str(destination)


def build_social_board(audio_path, duration, prompt, title, style="Cinematic"):
    from visual_direction import STYLES
    prompt = str(prompt or "").strip()[:2000]
    if not prompt:
        raise ValueError("Choose a prompt preset or describe your short video.")
    duration = number(duration, "Clip length", 3, 60)
    # Equal whole-second scenes keep every VideoExpress submission within 3–10s.
    duration = int(round(duration))
    count = max(1, math.ceil(duration / 6))
    base, extra = divmod(duration, count)
    scenes, start = [], 0
    beats = ("A striking opening shot that immediately establishes the subject",
             "A closer view revealing a new detail", "A smooth change of viewpoint",
             "Build energy with expressive movement", "A memorable closing image")
    for i in range(count):
        length = base + (i < extra)
        image = f"{prompt}, {beats[min(i, len(beats)-1)]}, {STYLES.get(style, STYLES['Cinematic'])}, vertical 9:16 composition, subject centered, no text or logos"
        motion = "Smooth cinematic movement, maintain the same subject and setting, music-video atmosphere"
        scenes.append(dict(scene_number=i+1, section_label="teaser", start=start, end=start+length,
                           duration=length, energy=.65, image_prompt=image, video_audio_prompt=motion,
                           video_prompt=f"{image}, {motion}"))
        start += length
    return dict(source_audio=str(Path(audio_path).resolve()), song_title=title, artist="", total_duration=duration,
                tempo_bpm=0, key="Unknown", scene_count=len(scenes), scenes=scenes)


def assemble_social(clips, board, destination, progress=None):
    """Normalize generated clips, then concatenate and replace audio with the song."""
    destination = Path(destination)
    with tempfile.TemporaryDirectory(prefix="og-social-scenes-") as work:
        work = Path(work)
        parts = []
        for index, scene in enumerate(board["scenes"]):
            source = clips[str(scene["scene_number"])]["path"]
            part = work / f"part-{index:03d}.mp4"
            duration = scene["duration"]
            run_render(["-i", str(source), "-an", "-vf", framing_filter(dict(framing="crop",x=50,y=50)),
                        "-t", str(duration), "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                        "-pix_fmt", "yuv420p", str(part)], duration)
            # A short render must not silently shift all subsequent scene boundaries.
            if probe(part)["duration"] < duration - .15:
                raise ValueError(f"Scene {scene['scene_number']} is shorter than its planned duration. Import a complete clip.")
            parts.append(part)
            if progress:
                progress((index + 1) / len(board["scenes"]) * 85)
        listing = work / "parts.txt"
        listing.write_text("\n".join(f"file '{p.name}'" for p in parts), encoding="utf-8")
        temporary = work / "assembled.mp4"
        run_render(["-f", "concat", "-safe", "1", "-i", str(listing), "-i", board["source_audio"],
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", str(board["total_duration"]), "-movflags", "+faststart", str(temporary)], board["total_duration"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Destination is inside the app's social work folder, never the original media.
        import shutil
        shutil.copyfile(temporary, destination)
    return str(destination)

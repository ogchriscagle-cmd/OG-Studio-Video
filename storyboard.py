"""
Turn song analysis into a scene-by-scene storyboard with text prompts
suitable for pasting into an AI video generator (e.g. VideoExpress.ai).
"""
import json
import os
import math

MOOD_BY_LABEL_ENERGY = {
    # (label) -> list of (max_energy_threshold, mood_desc)
}

PALETTES = {
    "low": ["muted blue and grey", "soft desaturated sepia", "cool moonlit tones", "misty teal and charcoal"],
    "mid": ["warm amber and brown", "dusty rose and gold", "golden hour orange", "earthy green and tan"],
    "high": ["neon pink and electric blue", "vivid red and black", "saturated magenta and teal", "blazing orange and violet"],
}

CAMERA_LOW = ["slow static wide shot", "gentle drift forward", "slow pan across the scene", "soft handheld sway"]
CAMERA_MID = ["steady tracking shot", "medium push-in", "slow orbit around the subject", "walking POV shot"]
CAMERA_HIGH = ["fast whip pan", "rapid push-in with lens flare", "dynamic crane shot rising up", "quick cut handheld energy"]

SUBJECT_BY_LABEL = {
    "intro": ["an empty stage bathed in light", "a lone figure silhouetted against the horizon",
              "a city skyline at dawn", "an open road stretching into the distance"],
    "verse": ["a figure walking through a rain-soaked street", "hands playing an instrument in close-up",
              "a quiet room with light through the blinds", "a reflection in a window at night"],
    "chorus": ["a crowd with hands raised under stage lights", "the singer center-frame with lights exploding behind",
               "fireworks bursting over a packed arena", "dancers moving in perfect unison under strobing light"],
    "bridge": ["a slow-motion close-up of raindrops on glass", "a solitary dancer frozen mid-motion",
               "clouds breaking to reveal the sun", "a candle flame flickering in darkness"],
    "outro": ["the stage lights fading to black", "a figure walking away into the distance",
              "the sun setting over calm water", "an empty street as the city lights dim"],
}


def energy_bucket(e):
    if e < 0.33:
        return "low"
    if e < 0.66:
        return "mid"
    return "high"


def pick(lst, i):
    return lst[i % len(lst)]


def build_storyboard(analysis, artist=None, song_title=None):
    sections = plan_shots(analysis["sections"], analysis["duration"])
    tempo = analysis["tempo"]
    key = analysis["key"]
    scenes = []

    for i, sec in enumerate(sections):
        bucket = energy_bucket(sec["energy"])
        palette = pick(PALETTES[bucket], i)
        camera = pick({"low": CAMERA_LOW, "mid": CAMERA_MID, "high": CAMERA_HIGH}[bucket], i)
        subject = pick(SUBJECT_BY_LABEL.get(sec["label"], SUBJECT_BY_LABEL["verse"]), i)

        prompt = f"{subject}, {camera}, {palette} color grade, cinematic lighting, high detail, {bucket} energy mood"

        # VideoExpress.ai's "Create Video From Prompt" flow wants two
        # separate fields: a still-image prompt (subject + look) and a
        # video/audio prompt (motion + implied sound). Split accordingly.
        image_prompt = f"{subject}, {palette} color grade, cinematic lighting, high detail, {bucket}-energy atmosphere"
        video_audio_prompt = f"{camera}, {bucket} energy mood, subtle atmospheric motion and ambient sound matching the scene"

        scenes.append({
            "scene_number": i + 1,
            "section_label": sec["label"],
            "start": sec["start"],
            "end": sec["end"],
            "duration": sec["duration"],
            "energy": sec["energy"],
            "video_prompt": prompt,
            "image_prompt": image_prompt,
            "video_audio_prompt": video_audio_prompt,
        })

    storyboard = {
        "source_audio": os.path.abspath(analysis["path"]),
        "source_audio_version": (
            [os.stat(analysis["path"]).st_size, os.stat(analysis["path"]).st_mtime_ns]
            if os.path.isfile(analysis["path"]) else None
        ),
        "song_title": song_title or os.path.basename(analysis["path"]),
        "artist": artist or "",
        "tempo_bpm": tempo,
        "key": key,
        "total_duration": analysis["duration"],
        "scene_count": len(scenes),
        "scenes": scenes,
    }
    return storyboard


def plan_shots(sections, duration):
    """Cover the song using integer 3–10 second clips supported by the generator.

    Section boundaries are rounded to seconds; very short sections merge into
    their neighbor. The final video may exceed the song by less than a second
    (or be padded to three seconds for a very short input).
    """
    if not sections or not math.isfinite(duration) or duration <= 0:
        raise ValueError("A positive song duration and at least one section are required.")
    end = max(3, math.ceil(duration))
    boundaries = [0]
    for section in sections[:-1]:
        boundary = round(section["end"])
        if boundary - boundaries[-1] >= 3 and end - boundary >= 3:
            boundaries.append(boundary)
    boundaries.append(end)
    shots = []
    for start, stop in zip(boundaries, boundaries[1:]):
        length = stop - start
        count = math.ceil(length / 10)
        base, extra = divmod(length, count)
        cursor = start
        for i in range(count):
            size = base + (i < extra)
            midpoint = min(duration - 1e-9, cursor + size / 2)
            source = next((s for s in sections if s["start"] <= midpoint < s["end"]), sections[-1])
            shots.append({**source, "start": cursor, "end": cursor + size, "duration": size})
            cursor += size
    return shots


def write_outputs(storyboard, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "storyboard.json")
    md_path = os.path.join(out_dir, "storyboard.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, indent=2)

    lines = []
    lines.append(f"# Storyboard: {storyboard['song_title']}")
    if storyboard["artist"]:
        lines.append(f"**Artist:** {storyboard['artist']}")
    lines.append(f"**Tempo:** {storyboard['tempo_bpm']} BPM  |  **Key:** {storyboard['key']}  |  "
                 f"**Duration:** {storyboard['total_duration']:.1f}s  |  **Scenes:** {storyboard['scene_count']}")
    lines.append("")
    lines.append("Paste each prompt below into VideoExpress.ai's AI Prompt-to-Video tool, in order, "
                 "using the duration shown for each clip, then stitch the resulting clips in sequence.")
    lines.append("")
    for sc in storyboard["scenes"]:
        lines.append(f"## Scene {sc['scene_number']} — {sc['section_label'].title()} "
                     f"({sc['start']:.1f}s–{sc['end']:.1f}s, {sc['duration']:.1f}s long)")
        lines.append("")
        lines.append(f"> {sc['video_prompt']}")
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return json_path, md_path


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from analyze import analyze_song

    audio_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "output"

    analysis = analyze_song(audio_path)
    storyboard = build_storyboard(analysis)
    json_path, md_path = write_outputs(storyboard, out_dir)
    print(f"Wrote {json_path} and {md_path}")

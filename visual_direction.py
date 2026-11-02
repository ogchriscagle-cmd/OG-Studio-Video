"""Creative direction for image and motion prompts; no generation or network calls."""
STYLES = {
    "Cinematic": "cinematic realism, subtle film grain",
    "Neon noir": "neo-noir photography, bold cinematic contrast",
    "Dreamscape": "surreal dreamscape, ethereal atmosphere",
    "Vintage film": "vintage 35mm film aesthetic, nostalgic film grain",
    "Horror": "horror cinema aesthetic, suspenseful framing",
    "Anime": "hand-drawn 2D anime, clean cel-shaded illustration",
    "Watercolor": "painterly watercolor illustration, textured paper",
    "Cyberpunk": "futuristic cyberpunk aesthetic, intricate futuristic detail",
    "Live stage": "live concert music video, authentic stage production",
}
STYLE_LIGHTING = {
    "Cinematic": "cinematic lighting",
    "Neon noir": "contrasting neon lighting",
    "Dreamscape": "soft diffused lighting",
    "Vintage film": "soft vintage tungsten lighting",
    "Horror": "low-key dramatic lighting",
    "Anime": "stylized illustrated lighting",
    "Watercolor": "soft diffused light rendered in watercolor",
    "Cyberpunk": "luminous neon rim lighting",
    "Live stage": "concert stage lighting",
}
STYLE_PALETTES = {
    "Neon noir": "electric lime and violet", "Vintage film": "faded warm sepia",
    "Cyberpunk": "electric cyan and magenta", "Watercolor": "soft watercolor washes",
}
MOODS = {
    "Dark & moody": "dark, brooding mood", "Uplifting": "hopeful, uplifting mood",
    "High energy": "bold, high-energy mood", "Melancholic": "reflective, melancholic mood",
    "Peaceful": "calm, peaceful mood", "Mysterious": "enigmatic, mysterious mood",
    "Defiant": "fierce, defiant mood",
}
LIGHTING = {
    "Golden hour": "warm golden-hour lighting", "Soft daylight": "soft natural daylight",
    "Moonlight": "cool moonlit lighting", "Neon glow": "vivid neon lighting",
    "Stage spotlights": "focused concert spotlights", "Dramatic shadows": "dramatic chiaroscuro lighting",
    "Soft studio": "soft controlled studio lighting",
}
CAMERAS = {
    "Locked off": "locked-off camera, no camera movement",
    "Slow push-in": "slow controlled camera push-in",
    "Tracking": "smooth lateral camera tracking",
    "Slow orbit": "slow camera orbit around the subject",
    "Handheld": "subtle handheld camera movement",
    "Crane rise": "smooth upward camera crane movement",
    "Slow pan": "slow horizontal camera pan",
}
LOCATION_ACTIONS = {
    "intro": ["an establishing view of {location}", "the main character silhouetted in {location}"],
    "verse": ["the main character walking through {location}", "the main character performing in {location}"],
    "chorus": ["the main character performing center-frame in {location}", "dancers moving together in {location}"],
    "bridge": ["a solitary figure pausing in {location}", "a reflective moment in {location}"],
    "outro": ["the main character walking away through {location}", "a lingering final view of {location}"],
}
NEUTRAL_SUBJECTS = {
    "intro": ["an empty performance space", "a lone figure at the horizon", "a city skyline", "an open road"],
    "verse": ["a figure walking along a street", "hands playing an instrument", "a quiet room", "a reflection in a window"],
    "chorus": ["a crowd with hands raised", "the singer center-frame", "a packed concert venue", "dancers moving together"],
    "bridge": ["raindrops on glass", "a solitary dancer pausing", "clouds drifting across the sky", "a close-up of a candle"],
    "outro": ["a quiet performance space", "a figure walking away", "calm water", "an empty street"],
}


def direction_settings(options):
    def choice(key, choices, default=""):
        value = options.get(key)
        return value if isinstance(value, str) and value in choices else default
    return dict(style=choice("style", STYLES, "Cinematic"), mood=choice("mood", MOODS),
                lighting=choice("lighting", LIGHTING), camera=choice("camera", CAMERAS),
                location=str(options.get("location") or "").strip()[:240])


def scene_direction(subject, palette, camera, bucket, label, index, options):
    style = options.get("style") if options.get("style") in STYLES else "Cinematic"
    location = str(options.get("location") or "").strip()[:240]
    if location:
        actions = LOCATION_ACTIONS.get(label, LOCATION_ACTIONS["verse"])
        subject = actions[index % len(actions)].format(location=location)
    elif options.get("lighting") in LIGHTING or style != "Cinematic":
        # Avoid baking strobe/sunset/night lighting into a conflicting subject.
        subjects = NEUTRAL_SUBJECTS.get(label, NEUTRAL_SUBJECTS["verse"])
        subject = subjects[index % len(subjects)]
    lighting = LIGHTING.get(options.get("lighting"), STYLE_LIGHTING[style])
    palette = STYLE_PALETTES.get(style, palette)
    mood = MOODS.get(options.get("mood"))
    image = ", ".join([subject, f"{palette} color palette", lighting, "high detail",
                       mood or f"{bucket}-energy atmosphere", STYLES[style]])
    motion = ", ".join([CAMERAS.get(options.get("camera"), camera), mood or f"{bucket} energy mood",
                        "subtle atmospheric motion and ambient sound matching the scene"])
    return image, motion

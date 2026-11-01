import math
import unittest

from storyboard import build_storyboard


class CoverageTests(unittest.TestCase):
    def test_supported_clips_cover_song_without_gaps(self):
        for duration in (0.5, 3, 10, 10.1, 20, 30, 204.8):
            with self.subTest(duration=duration):
                analysis = dict(path="song.wav", duration=duration, tempo=120, key="C major",
                                sections=[dict(start=0, end=duration, duration=duration, label="verse", energy=0.5)])
                scenes = build_storyboard(analysis)["scenes"]
                self.assertEqual(scenes[0]["start"], 0)
                self.assertEqual(scenes[-1]["end"], max(3, math.ceil(duration)))
                self.assertTrue(all(3 <= s["duration"] <= 10 and int(s["duration"]) == s["duration"] for s in scenes))
                self.assertTrue(all(a["end"] == b["start"] for a, b in zip(scenes, scenes[1:])))

    def test_short_sections_and_fractional_boundaries(self):
        sections = [dict(start=a, end=b, duration=b-a, label=label, energy=0.5)
                    for a, b, label in [(0, 1, "intro"), (1, 22.6, "verse"), (22.6, 24, "outro")]]
        storyboard = build_storyboard(dict(path="song.wav", duration=24, tempo=120, key="C major", sections=sections))
        self.assertEqual(sum(s["duration"] for s in storyboard["scenes"]), 24)
        self.assertTrue(all(3 <= s["duration"] <= 10 for s in storyboard["scenes"]))


if __name__ == "__main__":
    unittest.main()

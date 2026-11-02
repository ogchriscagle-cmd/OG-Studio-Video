import json,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from storyboard import build_storyboard
from studio_app import StudioAPI
from visual_direction import STYLES,CAMERAS

class DirectionTests(unittest.TestCase):
    def analysis(self):
        return dict(path='song.wav',duration=24,tempo=120,key='C major',sections=[dict(start=0,end=24,duration=24,energy=.9,label='chorus')])

    def test_explicit_controls_replace_defaults_in_every_scene(self):
        board=build_storyboard(self.analysis(),visual=dict(style='Anime',mood='Peaceful',lighting='Moonlight',location='a desert highway',camera='Locked off'))
        self.assertEqual(sum(s['duration'] for s in board['scenes']),24)
        for scene in board['scenes']:
            image,motion=scene['image_prompt'],scene['video_audio_prompt']
            self.assertIn('2D anime',image)
            self.assertIn('moonlit',image)
            self.assertIn('a desert highway',image)
            self.assertIn('peaceful mood',image)
            self.assertIn('no camera movement',motion)
            self.assertNotIn('high energy mood',motion)
            self.assertNotIn('whip pan',motion)
            self.assertNotIn('cinematic realism',image)
            self.assertEqual(scene['video_prompt'],image+', '+motion)

    def test_all_styles_generate_and_automatic_camera_varies(self):
        for style in STYLES:
            board=build_storyboard(self.analysis(),visual=dict(style=style))
            self.assertIn(STYLES[style],board['scenes'][0]['image_prompt'])
        board=build_storyboard(self.analysis(),visual=dict(style='Cinematic'))
        self.assertNotEqual(board['scenes'][0]['video_audio_prompt'],board['scenes'][1]['video_audio_prompt'])

    def test_manual_lighting_removes_baked_strobes(self):
        board=build_storyboard(self.analysis(),visual=dict(style='Cinematic',lighting='Soft daylight'))
        for scene in board['scenes']:
            self.assertIn('soft natural daylight',scene['image_prompt'])
            self.assertNotIn('strobing',scene['image_prompt'])

    def test_legacy_storyboard_import_behavior_is_unchanged(self):
        board=build_storyboard(self.analysis())
        self.assertIn('cinematic lighting',board['scenes'][0]['image_prompt'])
        self.assertIn('fast whip pan',board['scenes'][0]['video_audio_prompt'])

    def test_storyboard_export_import_restores_creative_controls(self):
        options=dict(style='Cyberpunk',mood='Mysterious',lighting='Neon glow',location='A neon forest',camera='Tracking')
        board=build_storyboard(self.analysis(),visual=options)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            path=root/'storyboard.json';path.write_text(json.dumps(board))
            with patch('studio_app.ROOT',root):
                api=StudioAPI();api._restore(path)
            for key,value in options.items():self.assertEqual(api.get_state()['ui'][key],value)

    def test_api_preserves_cast_and_recombines_prompts(self):
        with tempfile.TemporaryDirectory() as folder:
            api=StudioAPI();api._out_dir=Path(folder)
            api._state['audio']=dict(path='song.wav',name='song.wav',url='/media/test')
            opts=dict(style='Watercolor',mood='Uplifting',lighting='Soft daylight',camera='Slow orbit',location='a forest clearing',character='OG Chris',appearance='black hoodie',concept='A journey home')
            with patch('studio_app.analyze_song',return_value=self.analysis()):
                api.analyze(opts);api._worker.join(5)
            state=api.get_state()
            self.assertIsNone(state['error'])
            scene=state['storyboard']['scenes'][0]
            for text in ['watercolor','a forest clearing','OG Chris','black hoodie','A journey home']:
                self.assertIn(text,scene['image_prompt'])
            self.assertIn('slow camera orbit',scene['video_audio_prompt'])
            self.assertEqual(scene['video_prompt'],scene['image_prompt']+', '+scene['video_audio_prompt'])
            self.assertEqual(state['options']['lighting'],'Soft daylight')

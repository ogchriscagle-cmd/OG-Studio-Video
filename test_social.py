import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from social_video import (ffmpeg, probe, clip_settings, build_social_board, render_video,
                          assemble_social, trim_song)
from studio_app import StudioAPI
from clip_tracking import load_tracking, save_tracking, scene_key
from videoexpress_automation import fill_scene


class SocialPlanTests(unittest.TestCase):
    def test_plans_cover_all_supported_lengths_with_valid_generation_durations(self):
        for duration in range(3, 61):
            board = build_social_board('song.wav', duration, 'A neon rooftop performance', 'Social')
            self.assertEqual(sum(s['duration'] for s in board['scenes']), duration)
            self.assertTrue(all(3 <= s['duration'] <= 10 for s in board['scenes']))
            self.assertIn('neon rooftop', board['scenes'][0]['image_prompt'])
            self.assertIn('9:16', board['scenes'][0]['image_prompt'])

    def test_invalid_times_are_rejected_before_export(self):
        for settings in ({'start':95,'duration':30}, {'start':float('nan')}, {'duration':61}, {'x':200}):
            with self.assertRaises(ValueError):
                clip_settings(settings, 100)

    def test_reference_is_optional_without_changing_existing_character_flow(self):
        scene = dict(image_prompt='Image', video_audio_prompt='Motion',duration=6)
        with patch('videoexpress_automation.set_reference_photo') as reference:
            page = MagicMock()
            fill_scene(page, scene, '', '9:16')
            reference.assert_not_called()
            self.assertIn(unittest.mock.call(unittest.mock.ANY, ['use_consistent_character',False]), page.evaluate.call_args_list)
            fill_scene(page, scene, 'Portrait', '9:16')
            reference.assert_called_once_with(page, 'Portrait', 'ogchris')


class SocialWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for module in ('studio_app.ROOT','social_studio.DATA_ROOT'):
            context = patch(module,self.root);context.start();self.addCleanup(context.stop)
        self.api = StudioAPI(self.root/'session.json')
        self.api._window = MagicMock()
        self.song = self.root/'song.wav';self.song.write_bytes(b'audio')
        self.api._state['social'] = dict(id='a'*32,song=dict(path=str(self.song),name=self.song.name,url=self.api._register(self.song),duration=90))
        self.music = dict(song_title='Existing music video',artist='',total_duration=6,tempo_bpm=120,key='C',scenes=[
            dict(scene_number=1,start=0,end=6,duration=6,section_label='verse',video_prompt='Original',image_prompt='Original',video_audio_prompt='Original')])
        self.api._state['storyboard']=copy.deepcopy(self.music)

    def create_plan(self):
        def trim(source,target,settings):
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'excerpt');return str(target)
        with patch('social_studio.probe',return_value={'duration':90}),patch('social_studio.trim_song',side_effect=trim):
            self.api.create_social_plan({'start':20,'duration':30},'A neon rooftop performance')
            self.api._worker.join(5)
        self.assertIsNone(self.api.get_state()['error'])

    def test_social_plan_autosaves_and_reopens_without_replacing_music(self):
        self.create_plan()
        self.api.update_workspace({'social':{'tab':'social','mode':'song','start':20,'duration':30,'hook':'Wait for it'}})
        restored = StudioAPI(self.root/'session.json')
        state = restored.get_state()
        self.assertEqual(state['storyboard']['scenes'],self.music['scenes'])
        self.assertEqual(state['social']['board']['total_duration'],30)
        self.assertEqual(state['ui']['social']['hook'],'Wait for it')
        self.assertEqual(state['social']['song']['duration'],90)
        self.assertNotEqual(state['social']['song']['url'],self.api.get_state()['social']['song']['url'])
        raw = json.loads((self.root/'session.json').read_text())
        self.assertNotIn('url',raw['state']['social']['song'])

    def test_generation_uses_own_folder_and_keeps_tracking_on_retry(self):
        self.create_plan()
        social=self.api.get_state()['social'];board=social['board']
        path=self.api._social_directory()/'storyboard.json'
        data=load_tracking(path,board)
        data['scenes']['1']=dict(status='submitted',scene_key=scene_key(board['scenes'][0]),uuid='accepted-job')
        save_tracking(path,data)
        with patch('social_studio.setup_project_folder') as upload,patch('social_studio.run_batch') as generate:
            self.api.generate_social_scenes();self.api._worker.join(5)
            self.api.generate_social_scenes();self.api._worker.join(5)
        upload.assert_called_once_with(board['song_title'],None,board['source_audio'])
        self.assertEqual(generate.call_count,2)
        generate.assert_called_with(path,'','9:16',folder_name=board['song_title'])
        self.assertEqual(load_tracking(path,board)['scenes']['1']['uuid'],'accepted-job')
        self.assertEqual(self.api.get_state()['storyboard']['scenes'],self.music['scenes'])

    def test_reference_change_requires_new_plan_instead_of_resetting_tracking(self):
        self.create_plan()
        self.api._state['social']['photo']={'path':'changed.jpg'}
        with patch('social_studio.run_batch') as generate:
            self.assertIn('changed',self.api.generate_social_scenes()['error'])
            generate.assert_not_called()

    def test_refresh_downloads_once_and_combines_with_excerpt(self):
        self.create_plan()
        social=self.api.get_state()['social'];board=social['board']
        tracking=load_tracking(self.api._social_directory()/'storyboard.json',board)
        tracking['scenes']={str(s['scene_number']):dict(status='ready',asset_id=str(100+s['scene_number']),scene_key=scene_key(s)) for s in board['scenes']}
        def download(asset,target):
            target=target.with_suffix('.mp4');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'clip');return str(target)
        def combine(clips,board,target,progress):target.write_bytes(b'combined');return str(target)
        with patch('social_studio.refresh_clip_tracking',return_value=tracking),patch('social_studio.download_tracked_clip',side_effect=download) as downloads,patch('social_studio.assemble_social',side_effect=combine) as assemble:
            for _ in range(2):
                self.api.refresh_social_clips();self.api._worker.join(5)
            self.assertEqual(downloads.call_count,board['scene_count'])
            assemble.assert_called_once()
        self.assertEqual(self.api.get_state()['social']['generated']['duration'],30)

    def test_cancelling_export_keeps_previous_result(self):
        video=self.root/'original.mp4';video.write_bytes(b'video')
        self.api._state['social']['video']={'path':str(video),'name':video.name}
        self.api._window.create_file_dialog.return_value=None
        with patch('social_studio.probe',return_value={'duration':90}),patch('social_studio.render_video') as render:
            self.api.export_social_video({'mode':'video','start':0,'duration':30})
            render.assert_not_called()


class SocialRenderTests(unittest.TestCase):
    """Real codec checks: duration, framing, overlay timing, and soundtrack."""
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.source=cls.root/'source.mp4'
        subprocess.run([ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=red:s=320x180:r=30:d=12',
                        '-f','lavfi','-i','sine=frequency=440:duration=12','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(cls.source)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def frame_pixel(self,path,second,point):
        png=self.root/f'frame-{second}.png'
        subprocess.run([ffmpeg(),'-hide_banner','-loglevel','error','-y','-ss',str(second),'-i',str(path),'-frames:v','1',str(png)],check=True,capture_output=True)
        with Image.open(png) as image:return image.convert('RGB').getpixel(point)

    def test_export_is_vertical_with_timed_text_audio_and_exact_trim(self):
        output=self.root/'social.mp4';progress=[]
        render_video(self.source,output,dict(start=1,duration=10,hook='Wait: 100% "new" [song]',cta='Follow for more'),progress.append)
        info=probe(output,video=True)
        self.assertEqual((info['width'],info['height']),(1080,1920))
        self.assertAlmostEqual(info['duration'],10,delta=.15)
        self.assertTrue(progress)
        early=self.frame_pixel(output,.5,(100,270));middle=self.frame_pixel(output,4,(100,270));late=self.frame_pixel(output,8,(100,1530))
        self.assertLess(early[0],middle[0]/2)
        self.assertGreater(middle[0],200)
        self.assertLess(late[0],100)
        result=subprocess.run([ffmpeg(),'-hide_banner','-i',str(output)],capture_output=True,text=True)
        self.assertIn('Audio: aac',result.stderr)
        with self.assertRaises(ValueError):render_video(self.source,self.source,{'start':0,'duration':3})

    def test_song_assembly_uses_selected_excerpt_and_removes_generated_audio(self):
        excerpt=self.root/'song.wav';trim_song(self.source,excerpt,{'start':3,'duration':6})
        board=build_social_board(excerpt,6,'A stage performance','Test')
        target=self.root/'assembled.mp4'
        assemble_social({'1':{'path':str(self.source)}},board,target)
        self.assertAlmostEqual(probe(target)['duration'],6,delta=.15)
        self.assertEqual(probe(excerpt)['duration'],6)


if __name__=='__main__':unittest.main()

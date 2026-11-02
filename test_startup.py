import os
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
import startup_progress

class StartupTests(unittest.TestCase):
    def test_stage_and_close(self):
        transport=MagicMock()
        with patch.object(startup_progress,'pyi_splash',transport):
            startup_progress.startup_stage(82,'Loading studio tools...')
            transport.update_text.assert_called_once_with('OGSTART|82|Loading studio tools...')
            startup_progress.close_startup()
            transport.close.assert_called_once()

    def test_source_and_suppressed_splash_are_safe(self):
        with patch.object(startup_progress,'pyi_splash',None):
            startup_progress.startup_stage(10,'Starting')
            startup_progress.close_startup()
        transport=MagicMock()
        transport.is_alive.return_value=False
        with patch.object(startup_progress,'pyi_splash',transport):
            startup_progress.startup_stage(10,'Starting')
            startup_progress.close_startup()
        transport.update_text.assert_not_called()
        transport.close.assert_not_called()

    @unittest.skipUnless(os.name=='nt' and importlib.util.find_spec('PyInstaller'),'Windows build test')
    def test_native_canvas_shows_stage_and_extraction_progress(self):
        import tkinter as tk
        from build_splash import StudioSplash,splash_image
        with tempfile.TemporaryDirectory() as folder:
            splash=object.__new__(StudioSplash)
            for key,value in dict(text_pos=(36,215),text_size=12,text_font='TkDefaultFont',text_color='#d9e6cf',text_default='Starting',always_on_top=False,minify_script=False,script_name=str(Path(folder)/'splash.tcl'),archive_files=100).items():
                setattr(splash,key,value)
            image=splash_image(Path(folder)/'splash.png')
            script=splash.generate_script().replace('raise .','wm withdraw .')
            root=tk.Tk();root.withdraw()
            try:
                root.tk.setvar('_image_data',Path(image).read_bytes())
                root.tk.eval(script)
                root.tk.setvar('status_text','OGSTART|82|Loading studio tools...')
                self.assertEqual(root.tk.call('.root.canvas','itemcget','vartext','-text'),'Loading studio tools...')
                coords=root.tk.call('.root.canvas','coords','startup_bar')
                self.assertAlmostEqual(float(coords[2]),36+568*.82)
                root.tk.setvar('status_text','lib/example.dll')
                self.assertEqual(root.tk.call('.root.canvas','itemcget','vartext','-text'),'Unpacking app files... file 1')
            finally:
                for event in root.tk.call('after','info'):root.tk.call('after','cancel',event)
                root.tk.call('close',root.tk.getvar('server_socket'))
                root.destroy()

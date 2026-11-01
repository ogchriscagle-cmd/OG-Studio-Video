import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from videoexpress_automation import download_streamed_video

class StreamingTests(unittest.TestCase):
    def test_progress_and_atomic_file(self):
        data=b'\x00\x00\x00\x18ftypisom'+b'video payload'
        with tempfile.TemporaryDirectory() as folder, patch('requests.Session') as session:
            response=session.return_value.__enter__.return_value.get.return_value
            response.status_code=200
            response.headers={'content-type':'video/mp4','content-length':str(len(data))}
            response.iter_content.return_value=[data[:12],data[12:]]
            request=MagicMock()
            request.storage_state.return_value={'cookies':[]}
            progress=MagicMock()
            path=download_streamed_video(request,'https://cdn-ny-b.videoexpress.ai/video/test.mp4',Path(folder)/'video.mp4',progress)
            self.assertEqual(Path(path).read_bytes(),data)
            self.assertEqual(progress.call_args.args,(len(data),len(data)))
            self.assertEqual(progress.call_count,3)
            self.assertFalse(Path(path+'.part').exists())

    def test_truncated_download_is_not_published(self):
        with tempfile.TemporaryDirectory() as folder, patch('requests.Session') as session:
            response=session.return_value.__enter__.return_value.get.return_value
            response.status_code=200
            response.headers={'content-type':'video/mp4','content-length':'100'}
            response.iter_content.return_value=[b'\x00\x00\x00\x18ftypisom']
            request=MagicMock()
            request.storage_state.return_value={'cookies':[]}
            path=Path(folder)/'video.mp4'
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                download_streamed_video(request,'https://cdn-ny-b.videoexpress.ai/video/test.mp4',path,MagicMock())
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix('.mp4.part').exists())
